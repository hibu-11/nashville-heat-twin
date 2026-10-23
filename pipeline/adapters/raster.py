"""
【中文】栅格适配器：把 GeoTIFF 转成
    1) 标准栅格 COG（data/standard/raster/）
    2) 网页叠加图 PNG（Web Mercator，透明 nodata）
    3) 数值网格 .bin（int16，×100），网页点击时查询温度
    4) 元数据 .json（四角坐标、色带、统计）
不依赖 GEE 临时瓦片链接，发布后不会过期。

Raster adapters: GeoTIFF → standard COG, web PNG overlay (Web Mercator),
an int16 value grid for click queries, and a metadata JSON.
No expiring GEE tile URLs are involved.
"""
from __future__ import annotations

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from rasterio.windows import Window, from_bounds as window_from_bounds

from ..schema import STORE_CRS
from .base import AdapterResult, DatasetAdapter, ramp_stops, write_json

WEB = "EPSG:3857"
LL = "EPSG:4326"
NODATA_I16 = -32768
VALUE_SCALE = 100  # 【中文】值 × 100 存为 int16，精度 0.01 / stored as value × 100


def _target_grid(src, aoi, max_px):
    """【中文】AOI 与影像范围求交，生成 Web Mercator 目标网格 / target grid in EPSG:3857."""
    a = transform_bounds(LL, WEB, *aoi)
    s = transform_bounds(src.crs, WEB, *src.bounds)
    w, so, e, n = max(a[0], s[0]), max(a[1], s[1]), min(a[2], s[2]), min(a[3], s[3])
    if w >= e or so >= n:
        raise ValueError("raster does not intersect the AOI")
    # 【中文】不超过原始分辨率（墨卡托在 36°N 约放大 1.24 倍）/ never finer than native
    native = abs(src.res[0])
    if src.crs.is_geographic:
        native *= 111_320
    native *= 1.24
    px = max(native, max(e - w, n - so) / max_px)
    width, height = max(1, round((e - w) / px)), max(1, round((n - so) / px))
    return (w, so, e, n), width, height


def _warp(src, band, bounds, width, height, resampling=Resampling.bilinear):
    dst = np.full((height, width), np.nan, dtype="float32")
    reproject(
        source=rasterio.band(src, band),
        destination=dst,
        src_nodata=src.nodata,
        dst_transform=from_bounds(*bounds, width, height),
        dst_crs=WEB,
        dst_nodata=np.nan,
        resampling=resampling,
    )
    return dst


def store_window(src, aoi):
    """【中文】标准存储网格：AOI 范围、EPSG:32616、原始分辨率。源数据已是 32616 时直接按窗口读取，
    不重采样；否则重投影。返回 (window 或 None, transform, width, height)。

    Storage grid: the AOI in EPSG:32616 at native resolution. Sources already in
    EPSG:32616 are read by window (no resampling); others are reprojected."""
    b = transform_bounds(LL, f"EPSG:{STORE_CRS}", *aoi)
    if src.crs and src.crs.to_epsg() == STORE_CRS:
        full = Window(0, 0, src.width, src.height)
        win = window_from_bounds(*b, transform=src.transform).round_offsets().round_lengths().intersection(full)
        return win, src.window_transform(win), int(win.width), int(win.height)
    transform, width, height = calculate_default_transform(
        src.crs, f"EPSG:{STORE_CRS}", src.width, src.height, *src.bounds, dst_bounds=b)
    return None, transform, width, height


def read_store(src, band, grid):
    """【中文】按标准网格读取一个波段为 float32（nodata → NaN）/ read a band on the storage grid."""
    win, transform, width, height = grid
    if win is not None:
        a = src.read(band, window=win).astype("float32")
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        return a
    dst = np.full((height, width), np.nan, dtype="float32")
    reproject(source=rasterio.band(src, band), destination=dst, src_nodata=src.nodata,
              dst_transform=transform, dst_crs=f"EPSG:{STORE_CRS}", dst_nodata=np.nan,
              resampling=Resampling.bilinear)
    return dst


def to_web(data, transform, bounds, width, height, resampling=Resampling.bilinear):
    """【中文】标准网格数组 → Web Mercator 目标网格 / storage-grid array → Web Mercator grid."""
    dst = np.full((height, width), np.nan, dtype="float32")
    reproject(source=data, destination=dst, src_transform=transform, src_crs=f"EPSG:{STORE_CRS}",
              src_nodata=np.nan, dst_transform=from_bounds(*bounds, width, height), dst_crs=WEB,
              dst_nodata=np.nan, resampling=resampling)
    return dst


def is_kelvin(cfg, data) -> bool:
    """【中文】kelvin: auto 时中位数 > 200 视为开尔文 / auto: median above 200 means Kelvin."""
    kel = cfg.get("kelvin", "auto")
    finite = data[np.isfinite(data)]
    return kel is True or (kel == "auto" and finite.size > 0 and float(np.median(finite)) > 200)


def _corners(bounds):
    """【中文】MapLibre image source 需要的四角经纬度（左上起顺时针）/ TL, TR, BR, BL."""
    w, s, e, n = transform_bounds(WEB, LL, *bounds)
    return [[w, n], [e, n], [e, s], [w, s]]


def _save_png(rgba: np.ndarray, path):
    Image.fromarray(rgba, mode="RGBA").save(path, optimize=True)


class RasterAdapter(DatasetAdapter):
    """【中文】单波段数值栅格（如 LST）/ single-band value raster such as LST."""
    kind = "raster"

    def extract(self):
        return rasterio.open(self.raw_path)

    def outputs(self):
        return [self.site_path("raster", ".png"), self.site_path("raster", ".bin"),
                self.site_path("raster", ".json"), self.standard_path("raster", ".tif")]

    def transform(self, src) -> AdapterResult:
        c = self.cfg
        png, binf, meta_f, cog = self.outputs()
        band = int(c.get("band", 1))
        with src:
            bounds, width, height = _target_grid(src, self.ctx.aoi, int(c.get("max_px", 1600)))
            data = _warp(src, band, bounds, width, height)
            sgrid = store_window(src, self.ctx.aoi)
            stored = read_store(src, band, sgrid)

        valid = np.isfinite(data)
        if c.get("valid_range"):
            lo, hi = c["valid_range"]
            valid &= (data >= lo) & (data <= hi)
            stored[(stored < lo) | (stored > hi)] = np.nan
        if not valid.any():
            raise ValueError("no valid pixels inside the AOI")

        # 【中文】开尔文自动转换 / Kelvin → °C
        if is_kelvin(c, data[valid]):
            data, stored = data - 273.15, stored - 273.15
            print(f"    {self.id}: values look like Kelvin, converted to °C")
        data[~valid] = np.nan

        p_lo, p_hi = c.get("stretch", [2, 98])
        vmin, vmax = np.percentile(data[valid], [p_lo, p_hi]).astype(float)
        cmap_name = c.get("colormap", "inferno")

        # 1) PNG overlay
        norm = np.clip((data - vmin) / max(vmax - vmin, 1e-6), 0, 1)
        rgba = (colormaps[cmap_name](np.nan_to_num(norm)) * 255).astype("uint8")
        rgba[..., 3] = np.where(valid, 255, 0)
        _save_png(rgba, png)

        # 2) value grid (coarser if large) / 数值网格
        vmax_px = int(c.get("value_px", 900))
        vg = data
        step = int(np.ceil(max(width, height) / vmax_px))
        if step > 1:
            h2, w2 = height // step, width // step
            vg = np.nanmean(data[: h2 * step, : w2 * step].reshape(h2, step, w2, step), axis=(1, 3))
        grid = np.where(np.isfinite(vg), np.round(vg * VALUE_SCALE), NODATA_I16).astype("<i2")
        grid.tofile(binf)

        # 3) standard COG (EPSG:32616, native resolution) / 标准栅格
        _, transform, w_, h_ = sgrid
        profile = dict(driver="COG", width=w_, height=h_, count=1, dtype="float32",
                       crs=f"EPSG:{STORE_CRS}", transform=transform, nodata=np.nan,
                       compress="deflate", predictor=3)
        with rasterio.open(cog, "w", **profile) as dst:
            dst.write(stored, 1)
            dst.update_tags(units=c.get("units", ""), timestamp=c.get("timestamp") or "")

        # 4) metadata / 元数据
        meta = {
            "id": self.id,
            "corners": _corners(bounds),
            "merc_bounds": list(bounds),
            "grid": {"width": int(grid.shape[1]), "height": int(grid.shape[0]),
                     "scale": VALUE_SCALE, "nodata": NODATA_I16},
            "vmin": round(vmin, 2), "vmax": round(vmax, 2),
            "units": c.get("units", ""),
            "colormap": cmap_name, "stops": ramp_stops(cmap_name),
            "stats": {"mean": round(float(np.nanmean(data)), 2),
                      "p05": round(float(np.nanpercentile(data, 5)), 2),
                      "p95": round(float(np.nanpercentile(data, 95)), 2)},
            "timestamp": c.get("timestamp"),
        }
        write_json(meta_f, meta)

        layer = self.base_layer() | {
            "image": f"raster/{self.id}.png",
            "values": f"raster/{self.id}.bin",
            "meta": f"raster/{self.id}.json",
        }
        return AdapterResult(layer=layer)


class RgbRasterAdapter(DatasetAdapter):
    """【中文】三波段真彩色底图 / three-band true-color basemap."""
    kind = "raster_rgb"

    def extract(self):
        return rasterio.open(self.raw_path)

    def outputs(self):
        return [self.site_path("raster", ".png"), self.site_path("raster", ".json")]

    def transform(self, src) -> AdapterResult:
        c = self.cfg
        png, meta_f = self.outputs()
        with src:
            bounds, width, height = _target_grid(src, self.ctx.aoi, int(c.get("max_px", 2000)))
            bands = [_warp(src, b, bounds, width, height) for b in c.get("bands", [1, 2, 3])]

        stack = np.stack(bands, axis=-1)
        valid = np.all(np.isfinite(stack), axis=-1) & np.any(stack != 0, axis=-1)
        p_lo, p_hi = c.get("stretch", [2, 98])
        out = np.zeros((height, width, 4), dtype="uint8")
        for i in range(3):
            b = stack[..., i]
            lo, hi = np.percentile(b[valid], [p_lo, p_hi])
            out[..., i] = (np.clip((b - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype("uint8")
        out[..., 3] = np.where(valid, 255, 0)
        _save_png(out, png)

        write_json(meta_f, {"id": self.id, "corners": _corners(bounds), "merc_bounds": list(bounds)})
        layer = self.base_layer() | {"image": f"raster/{self.id}.png", "meta": f"raster/{self.id}.json"}
        return AdapterResult(layer=layer)
