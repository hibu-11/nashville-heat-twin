"""
【中文】城市气温场适配器（kind: air_field，方法见 pipeline/twin/airfield.py 与 PIPELINE_SPEC M-6）。输出：
    1) 标准栅格 data/standard/air_field/<id>.tif：3 个波段 = 早 / 午 / 晚气温距平（°C，相对该次走航平均）
    2) 模型说明 data/standard/air_field/<id>_model.json：系数、交叉验证误差、BNA 处的距平、候选走航日期
    3) 网页图层：午后气温相对机场站的差值（复用 raster 适配器的网页输出）
级联模型（pipeline/cascade.py）读取 1) 和 2)，给每个变电站和供电分区算逐小时气温。

Urban air-temperature field adapter. Writes a 3-band anomaly COG, a model report and a web layer
of the afternoon difference from the airport station.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from ..schema import STORE_CRS
from ..twin import airfield
from .base import AdapterResult, DatasetAdapter, write_json
from .raster import RasterAdapter

PERIODS = ("morning", "afternoon", "evening")


class AirFieldAdapter(DatasetAdapter):
    kind = "air_field"
    code_modules = (airfield,)

    def input_files(self):
        c = self.cfg
        files = [self.ctx.raw_dir / c["traverse"][p] for p in PERIODS]
        files += [self.ctx.raw_dir / c["grids"][k] for k in ("dem", "impervious", "landcover")]
        if c.get("asos_file"):
            files.append(self.ctx.raw_dir / c["asos_file"])
        return files

    def outputs(self):
        return [self.standard_path("air_field", ".tif"), self.standard_path("air_field", "_model.json"),
                self.site_path("raster", ".png")]

    def extract(self):
        c = self.cfg
        parts = []
        for p in PERIODS:
            g = gpd.read_file(self.ctx.raw_dir / c["traverse"][p]).to_crs(STORE_CRS)
            t = airfield.F_TO_C(g["Temperature"])
            parts.append(pd.DataFrame({"period": p, "t_c": t, "x": g.geometry.x, "y": g.geometry.y}))
        return pd.concat(parts, ignore_index=True)

    def transform(self, pts: pd.DataFrame) -> AdapterResult:
        c = self.cfg
        tif, model_f, _ = self.outputs()
        raw = self.ctx.raw_dir
        grids, tr, crs = airfield.predictor_grids(raw / c["grids"]["dem"], raw / c["grids"]["impervious"],
                                                  raw / c["grids"]["landcover"])
        pts = pd.concat([pts.reset_index(drop=True), airfield.sample(grids, tr, pts["x"], pts["y"])], axis=1)
        pts = pts.dropna(subset=airfield.PREDICTORS + ["t_c"])
        ref = gpd.GeoSeries(gpd.points_from_xy([c["reference"]["lon"]], [c["reference"]["lat"]]), crs=4326).to_crs(STORE_CRS)
        ref_z = airfield.sample(grids, tr, ref.x, ref.y)

        models, fields, ref_anom, means = {}, [], [], {}
        for p in PERIODS:
            sub = pts[pts["period"] == p].copy()
            means[p] = float(sub["t_c"].mean())
            sub["anom_c"] = sub["t_c"] - means[p]
            cells = airfield.aggregate_points(sub, float(c.get("cell_m", 100)))
            m = airfield.fit_period(cells, block_m=float(c.get("block_m", 1000)))
            models[p] = m
            fields.append(airfield.predict(m, grids))
            ref_anom.append(float(airfield.predict(m, {k: ref_z[k].to_numpy()[None, :] for k in airfield.PREDICTORS})[0, 0]))
            print(f"    {self.id}: {p}: {len(sub):,} points → {m['n_cells']:,} cells, CV RMSE {m['cv_rmse_c']} °C "
                  f"(null {m['null_rmse_c']}), CV R² {m['cv_r2']}; BNA anomaly {ref_anom[-1]:+.2f} °C")

        stack = np.stack(fields).astype("float32")
        h, w = stack.shape[1:]
        with rasterio.open(tif, "w", driver="COG", width=w, height=h, count=3, dtype="float32", crs=crs, transform=tr,
                           nodata=np.nan, compress="deflate", predictor=3) as dst:
            dst.write(stack)
            for i, p in enumerate(PERIODS, start=1):
                dst.set_band_description(i, f"{p} anomaly (degC, relative to traverse mean)")
            dst.update_tags(units="degC", reference_station=c["reference"]["station_id"],
                            reference_anomaly=",".join(f"{v:.4f}" for v in ref_anom))

        # 【中文】候选走航日期：BNA 的早 / 午 / 晚气温与走航平均最接近的日子 / candidate traverse dates
        dates = []
        if c.get("asos_file"):
            a = pd.read_csv(raw / c["asos_file"], usecols=["valid", "tmpf"], na_values="M")
            a.index = pd.to_datetime(a["valid"], utc=True).dt.tz_convert(self.ctx.project.get("timezone", "UTC"))
            a = pd.Series(airfield.F_TO_C(a["tmpf"]), index=a.index).dropna()
            a = a[~a.index.duplicated()]
            dates = airfield.match_dates(a, [means[p] for p in PERIODS], [int(x) for x in c["anchors_local"]])

        write_json(model_f, {
            "id": self.id, "method": "PIPELINE_SPEC M-6", "predictors": airfield.PREDICTORS,
            "anchors_local_hour": c["anchors_local"], "reference": c["reference"],
            "reference_anomaly_c": dict(zip(PERIODS, ref_anom)), "traverse_mean_c": means,
            "models": models, "candidate_traverse_dates": dates,
            "grid": {"crs": crs, "res_m": abs(tr.a), "width": w, "height": h},
        })

        # 【中文】网页图层：午后气温相对机场站的差值 / web layer: afternoon difference from BNA
        rel = self.standard_path("air_field", "_afternoon_vs_bna.tif")
        with rasterio.open(rel, "w", driver="GTiff", width=w, height=h, count=1, dtype="float32", crs=crs, transform=tr,
                           nodata=np.nan) as dst:
            dst.write((stack[1] - ref_anom[1]).astype("float32"), 1)
        web = RasterAdapter({**c, "kind": "raster", "file": str(rel), "band": 1, "kelvin": False,
                             "stretch": c.get("stretch", [1, 99]), "colormap": c.get("colormap", "RdBu_r"),
                             "units": "°C"}, self.ctx).run()
        return AdapterResult(layer=web.layer)
