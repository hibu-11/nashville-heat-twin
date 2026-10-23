"""
【中文】事件适配器：历史失效 / 异常记录（如 hubNashville 311）→
    1) 标准表 events（EPSG:32616）。按空间距离把事件匹配到上游资产的 asset_id（实体匹配），
       匹配不上的 asset_id 留空（设计方案第 3 节：events 的 asset_id 允许为空）
    2) 网页只发布聚合统计：规则网格内的事件数（热浪期 vs 对照期）+ 每日计数。
       单条记录不进网站，符合 311 数据“公开发布时只发布聚合统计”的条款

Events adapter: historical failure / anomaly records (e.g. hubNashville 311) →
    1) the standard events table (EPSG:32616), spatially matched to upstream
       asset ids where possible (asset_id stays empty otherwise)
    2) aggregated web outputs only: grid-cell counts (heat window vs baseline)
       and daily counts. Individual records never reach the site.
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from ..schema import STORE_CRS
from .base import AdapterResult, DatasetAdapter, ramp_stops, write_json


class EventsAdapter(DatasetAdapter):
    kind = "events"

    def upstream(self):
        m = self.cfg.get("match")
        return [m["source"]] if m else []

    def outputs(self):
        return [self.site_path("events", "_grid.geojson"), self.site_path("events", "_daily.json")]

    def extract(self):
        p = self.raw_path
        if p.suffix == ".parquet":
            return gpd.read_parquet(p)
        if p.suffix == ".csv":
            df = pd.read_csv(p)
            f = self.cfg["fields"]
            return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[f["lon"]], df[f["lat"]]), crs=4326)
        return gpd.read_file(p)

    def transform(self, raw: gpd.GeoDataFrame) -> AdapterResult:
        c, f = self.cfg, self.cfg["fields"]
        grid_f, daily_f = self.outputs()
        tz = self.ctx.project.get("timezone", "UTC")

        gdf = raw if raw.crs else raw.set_crs(4326)
        gdf = gdf[~gdf.geometry.is_empty]          # 【中文】先去掉空几何再判缺失，避免 geopandas 警告
        gdf = gdf[gdf.geometry.notna()].to_crs(4326)
        gdf = gdf[gdf.intersects(box(*self.ctx.aoi))]
        types = c.get("event_types")
        if types:
            gdf = gdf[gdf[f["type"]].isin(types)]
        if gdf.empty:
            raise ValueError("no events inside the AOI")

        attr_cols = [a for a in c.get("attribute_fields", []) if a in gdf]
        ev = gpd.GeoDataFrame({
            "event_id": gdf[f["id"]].astype(str),
            "event_type": gdf[f["type"]].astype(str),
            "start_time": pd.to_datetime(gdf[f["start"]], utc=True),
            "end_time": pd.to_datetime(gdf[f["end"]], utc=True) if f.get("end") in gdf else pd.NaT,
            "severity": pd.to_numeric(gdf[f["severity"]], errors="coerce") if f.get("severity") in gdf else np.nan,
            "attributes": gdf[attr_cols].apply(lambda r: json.dumps(r.dropna().to_dict(), ensure_ascii=False, default=str), axis=1)
            if attr_cols else None,
            "source_id": self.id,
        }, geometry=gdf.geometry, crs=4326).to_crs(STORE_CRS)
        ev["event_id"] = f"{self.id}:" + ev["event_id"]

        # 【中文】实体匹配：在 max_dist_m 内找最近的资产 / match to the nearest asset within max_dist_m
        ev["asset_id"] = pd.Series(pd.NA, index=ev.index, dtype="string")
        m = c.get("match")
        if m:
            assets = self.ctx.load_assets(m["source"])[["asset_id", "geometry"]].to_crs(STORE_CRS)
            cand = ev[ev["event_type"].isin(m.get("event_types", ev["event_type"].unique()))]
            hit = gpd.sjoin_nearest(cand[["geometry"]], assets, how="left",
                                    max_distance=float(m.get("max_dist_m", 30)), distance_col="_d")
            hit = hit[~hit.index.duplicated()]   # 【中文】等距时取第一个 / ties: keep the first
            ev.loc[hit.index, "asset_id"] = hit["asset_id"].astype("string")
            n_cand, n_hit = len(cand), int(hit["asset_id"].notna().sum())
            print(f"    {self.id}: matched {n_hit}/{n_cand} {', '.join(m.get('event_types', []))} events "
                  f"to {m['source']} within {m.get('max_dist_m', 30)} m")

        # 【中文】聚合输出 / aggregated web outputs
        local = ev["start_time"].dt.tz_convert(tz).dt.date
        heat, base = self.ctx.project.get("heatwave"), self.ctx.project.get("baseline")
        daily = (pd.DataFrame({"date": local.astype(str), "type": ev["event_type"]})
                 .groupby(["date", "type"]).size().unstack(fill_value=0).sort_index())
        write_json(daily_f, {"types": list(daily.columns), "type_labels": c.get("type_labels", {}),
                             "dates": list(daily.index),
                             "counts": daily.to_numpy().tolist(), "timezone": tz,
                             "heatwave": heat, "baseline": base})

        cell = float(c.get("grid_m", 500))
        xy = ev.geometry.get_coordinates()
        gx, gy = np.floor(xy["x"] / cell).astype(int), np.floor(xy["y"] / cell).astype(int)
        period = pd.Series("other", index=ev.index)
        n_days = {}
        for name, win in (("heatwave", heat), ("baseline", base)):
            if win:
                d0, d1 = pd.Timestamp(win["start"]).date(), pd.Timestamp(win["end"]).date()
                period[(local >= d0) & (local <= d1)] = name
                n_days[name] = (d1 - d0).days + 1
        tab = (pd.DataFrame({"gx": gx, "gy": gy, "period": period})
               .groupby(["gx", "gy", "period"]).size().unstack(fill_value=0))
        for name in ("heatwave", "baseline"):
            if name not in tab:
                tab[name] = 0
        tab = tab[(tab["heatwave"] + tab["baseline"]) > 0].reset_index()
        cells = gpd.GeoDataFrame({
            "events_heatwave": tab["heatwave"].astype(int),
            "events_baseline": tab["baseline"].astype(int),
            "per_day_heatwave": (tab["heatwave"] / n_days.get("heatwave", 1)).round(2),
            "per_day_baseline": (tab["baseline"] / n_days.get("baseline", 1)).round(2),
        }, geometry=[box(x * cell, y * cell, (x + 1) * cell, (y + 1) * cell) for x, y in zip(tab["gx"], tab["gy"])],
            crs=STORE_CRS).to_crs(4326)
        grid_f.write_text(cells.to_json(drop_id=True), encoding="utf-8")

        vmax = float(np.percentile(cells["per_day_heatwave"], 98)) if len(cells) else 1.0
        cmap = c.get("colormap", "YlOrRd")
        layer = self.base_layer() | {
            "kind": "vector", "role": "events", "data": f"events/{self.id}_grid.geojson", "geometry": "fill",
            "popup_fields": ["events_heatwave", "events_baseline", "per_day_heatwave", "per_day_baseline"],
            "field_labels": {"events_heatwave": "Events, heat window", "events_baseline": "Events, baseline",
                             "per_day_heatwave": "Per day, heat window", "per_day_baseline": "Per day, baseline"},
            "count": int(len(cells)), "count_label": f"{int(cell)} m cells",
            "color": {"field": "per_day_heatwave", "label": "Events per day (heat window)",
                      "vmin": 0, "vmax": round(max(vmax, 0.1), 2), "stops": ramp_stops(cmap, 5), "units": "/day"},
            "daily": f"events/{self.id}_daily.json", "aggregated": True,
        }
        return AdapterResult(layer=layer, tables={"events": ev})
