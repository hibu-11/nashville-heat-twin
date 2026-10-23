"""
【中文】矢量适配器：Shapefile / GeoJSON →
    1) 标准表 assets（EPSG:32616，未简化几何），可选 exposures（合成期的 LST 字段）
    2) 网页 GeoJSON（EPSG:4326，裁剪到 AOI、简化、保留弹窗字段）
Vector adapter: Shapefile / GeoJSON → standard assets (EPSG:32616, full geometry)
plus optional composite exposures, and a clipped, simplified GeoJSON for the site.
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box

from ..schema import STORE_CRS
from .base import AdapterResult, DatasetAdapter, ramp_stops

GEOM_KIND = {"LineString": "line", "MultiLineString": "line",
             "Polygon": "fill", "MultiPolygon": "fill",
             "Point": "circle", "MultiPoint": "circle"}


class VectorAdapter(DatasetAdapter):
    kind = "vector"

    def extract(self):
        return gpd.read_file(self.raw_path)

    def outputs(self):
        return [self.site_path("vector", ".geojson")]

    def transform(self, gdf: gpd.GeoDataFrame) -> AdapterResult:
        c = self.cfg
        (web_f,) = self.outputs()

        if gdf.crs is None:
            print(f"    {self.id}: no CRS, assuming EPSG:4326")
            gdf = gdf.set_crs(4326)
        gdf = gdf.to_crs(4326)
        gdf = gpd.clip(gdf, box(*self.ctx.aoi))
        gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
        if gdf.empty:
            raise ValueError("no features inside the AOI")

        # 【中文】全局唯一 asset_id / globally unique asset_id
        idf = c.get("id_field")
        base = gdf[idf].astype(str) if idf and idf in gdf else pd.Series(range(len(gdf)), index=gdf.index).astype(str)
        dup = base.groupby(base).cumcount()
        gdf["asset_id"] = f"{self.id}:" + base + np.where(dup > 0, "-" + dup.astype(str), "")

        # 【中文】"英文 / 中文" 这类双语值只保留分隔符前面的部分 / keep the part before a separator
        for col, sep in c.get("split_fields", {}).items():
            if col in gdf:
                gdf[col] = gdf[col].astype("string").str.split(sep, regex=False).str[0].str.strip()

        attr_cols = [col for col in gdf.columns if col not in ("geometry", "asset_id")]
        for col in attr_cols:  # 【中文】日期等转成字符串 / make JSON-safe
            if not (pd.api.types.is_numeric_dtype(gdf[col]) or pd.api.types.is_string_dtype(gdf[col])):
                gdf[col] = gdf[col].astype(str)

        # 1) standard assets table (EPSG:32616) / 标准 assets 表
        assets = gpd.GeoDataFrame({
            "asset_id": gdf["asset_id"],
            "system": c.get("system", "unknown"),
            "asset_type": c.get("asset_type", "feature"),
            "attributes": gdf[attr_cols].apply(lambda r: json.dumps(r.dropna().to_dict(), ensure_ascii=False, default=str), axis=1),
            "valid_from": c.get("valid_from"),
            "valid_to": c.get("valid_to"),
            "source_id": self.id,
        }, geometry=gdf.geometry, crs=4326).to_crs(STORE_CRS)
        tables = {"assets": assets}

        # 2) optional composite exposures / 可选合成期热暴露
        exp = c.get("exposure")
        if exp:
            start, end = exp["period"]
            e = pd.DataFrame({"asset_id": gdf["asset_id"].values,
                              "timestamp": pd.Timestamp(start, tz="UTC"),
                              "time_end": pd.Timestamp(end, tz="UTC") + pd.Timedelta(hours=23, minutes=59),
                              "lst_source": exp.get("lst_source"), "source_id": self.id})
            for out_name, in_name in exp.get("fields", {}).items():
                if in_name in gdf:
                    e[out_name] = pd.to_numeric(gdf[in_name], errors="coerce").values
            e["quality_flag"] = np.where(e["lst_mean"].notna(), "ok", "no_data")
            tables["exposures"] = e

        # 3) web GeoJSON (simplified) / 网页文件（简化几何）
        tol = float(c.get("simplify_m", 0)) / 111_320   # 【中文】米 → 近似度 / metres → approx. degrees
        if tol > 0:
            gdf["geometry"] = gdf.geometry.simplify(tol, preserve_topology=True)
        gdf["geometry"] = shapely.set_precision(gdf.geometry.values, 1e-6)
        gdf = gdf[~gdf.geometry.is_empty]

        popup = c.get("popup_fields") or attr_cols
        keep = [f for f in dict.fromkeys(popup + [c.get("color_field")]) if f and f in gdf]
        web = gdf[keep + ["asset_id", "geometry"]].copy()
        for f in keep:
            if pd.api.types.is_float_dtype(web[f]):
                web[f] = web[f].round(3)
        web_f.write_text(web.to_json(drop_id=True, ensure_ascii=False), encoding="utf-8")

        # 4) layer entry / 图层配置
        gtype = gdf.geometry.iloc[0].geom_type
        layer = self.base_layer() | {
            "data": f"vector/{self.id}.geojson",
            "geometry": GEOM_KIND.get(gtype, "fill"),
            "popup_fields": keep,
            "field_labels": c.get("field_labels", {}),
            "count": int(len(web)),
        }
        cf = c.get("color_field")
        if cf and cf in gdf:
            vals = pd.to_numeric(gdf[cf], errors="coerce").dropna()
            lo, hi = np.percentile(vals, [2, 98]) if len(vals) else (0, 1)
            cmap = c.get("colormap", "inferno")
            layer["color"] = {"field": cf, "label": c.get("color_label", cf),
                              "vmin": round(float(lo), 2), "vmax": round(float(hi), 2),
                              "stops": ramp_stops(cmap, 5), "units": c.get("units", "")}
        else:
            layer["fill_color"] = c.get("fill_color", "#7FA7B8")
        return AdapterResult(layer=layer, tables=tables)
