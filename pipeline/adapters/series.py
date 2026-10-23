"""
【中文】逐小时栅格序列适配器（如 10 m 逐小时 LST），对应设计方案阶段 A（热暴露提取）和时间回放：
    1) 标准栅格：一个多波段 GeoTIFF（EPSG:32616，每个波段一个时刻，波段描述为 UTC 时间）
    2) 标准表 exposures：每个资产每小时的 lst_mean / lst_max / n_pixels / quality_flag
    3) 网页回放帧：每个时刻一张 8 位灰度 + alpha 无损图（默认 WebP，可选 PNG），所有帧共用
       同一个数值范围，浏览器端解码后既用来着色，也用来点击读数
    像元完全相同的帧（上游融合模型偶尔对称复制）会被标记为 suspect，不删除
    4) 网页资产矩阵：int16（×100）[资产 × 时刻]，用于道路按当前小时着色和资产热暴露曲线

Hourly raster series adapter (e.g. 10 m hourly LST) — design stage A (heat
exposure) plus time playback:
    1) standard multi-band GeoTIFF (EPSG:32616, one band per timestamp)
    2) standard hourly exposures for every asset of the configured upstream datasets
    3) one lossless 8-bit grey+alpha image per frame (WebP by default, or PNG), all
       frames on one shared value range; the browser decodes them for both
       colouring and click read-outs
Frames whose pixels are identical to another frame are flagged `suspect`, not dropped.
    4) an int16 (×100) [asset × frame] matrix for the web
"""
from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd
import rasterio
import shapely
from PIL import Image

from ..schema import STORE_CRS
from .base import AdapterResult, DatasetAdapter, ramp_stops, write_json
from .raster import NODATA_I16, VALUE_SCALE, _corners, _target_grid, is_kelvin, read_store, store_window, to_web

LEVELS = 254   # 【中文】灰度 1–255 表示数值，0 表示无数据 / grey 1–255 = value, alpha 0 = no data


class RasterSeriesAdapter(DatasetAdapter):
    kind = "raster_series"

    # ------------------------------------------------------------------ inputs
    @property
    def raw_path(self):
        return self.ctx.raw_dir / self.cfg["dir"]

    def input_files(self):
        return sorted(self.raw_path.glob(self.cfg.get("glob", "*.tif")))

    def upstream(self):
        return [z["source"] for z in self.cfg.get("zonal", [])]

    def frames(self) -> list[tuple[pd.Timestamp, object]]:
        """【中文】从文件名解析 UTC 时间 / parse UTC timestamps from file names."""
        pat = re.compile(self.cfg["time_regex"])
        out = []
        for f in self.input_files():
            m = pat.search(f.name)
            if not m:
                print(f"    {self.id}: skipping {f.name} (no timestamp in name)")
                continue
            g = m.groupdict()
            out.append((pd.Timestamp(f"{g['date']}T{g.get('hour', '00')}:00", tz="UTC"), f))
        if not out:
            raise ValueError(f"no files match {self.cfg.get('glob')} / {self.cfg['time_regex']}")
        return sorted(out, key=lambda x: x[0])

    def outputs(self):
        return [self.site_path("series", ".json"), self.standard_path("raster", ".tif")]

    def extract(self):
        return self.frames()

    # ------------------------------------------------------------------ build
    def transform(self, frames) -> AdapterResult:
        c = self.cfg
        meta_f, store_f = self.outputs()
        frame_dir = self.ctx.site_data_dir / "series" / self.id
        frame_dir.mkdir(parents=True, exist_ok=True)
        for old in frame_dir.glob("*"):
            old.unlink()

        with rasterio.open(frames[0][1]) as src0:
            grid = store_window(src0, self.ctx.aoi)
            web_bounds, web_w, web_h = _target_grid(src0, self.ctx.aoi, int(c.get("max_px", 1000)))
            band = int(c.get("band", 1))
            kelvin = is_kelvin(c, read_store(src0, band, grid))
        _, transform, width, height = grid
        zones = [self._zones(z, transform, width, height) for z in c.get("zonal", [])]

        # 【中文】第一遍：写标准栅格、算分区统计、收集数值范围
        # pass 1: write the standard stack, zonal statistics, value range
        profile = dict(driver="GTiff", width=width, height=height, count=len(frames), dtype="float32",
                       crs=f"EPSG:{STORE_CRS}", transform=transform, nodata=np.nan, tiled=True,
                       blockxsize=256, blockysize=256, compress="deflate", predictor=3, BIGTIFF="IF_SAFER",
                       interleave="band")   # 【中文】按波段存，单帧读取不用解压全部波段 / one band per read
        exposures, frame_info, samples, seen = [], [], [], {}
        rng = np.random.default_rng(0)
        print(f"    {self.id}: {len(frames)} frames, storage grid {width}×{height}, "
              f"{sum(len(z['ids']) for z in zones)} assets for zonal stats")
        with rasterio.open(store_f, "w", **profile) as dst:
            for i, (ts, path) in enumerate(frames):
                with rasterio.open(path) as src:
                    a = read_store(src, band, grid)
                if kelvin:
                    a -= 273.15
                if c.get("valid_range"):
                    lo, hi = c["valid_range"]
                    a[(a < lo) | (a > hi)] = np.nan
                dst.write(a, i + 1)
                dst.set_band_description(i + 1, ts.strftime("%Y-%m-%dT%H:%MZ"))
                ok = np.isfinite(a)
                frame_info.append({"t": ts.strftime("%Y-%m-%dT%H:%MZ"), "valid": round(float(ok.mean()), 3),
                                   **_stats(a[ok])})
                # 【中文】与之前某帧像元完全相同 → 两帧都标记 / identical pixels → flag both frames
                digest = hashlib.sha1(a.tobytes()).hexdigest()
                if digest in seen:
                    j = seen[digest]
                    frame_info[i].setdefault("same_as", []).append(frame_info[j]["t"])
                    frame_info[j].setdefault("same_as", []).append(frame_info[i]["t"])
                else:
                    seen[digest] = i
                if ok.any():
                    v = a[ok]
                    samples.append(rng.choice(v, size=min(v.size, 20_000), replace=False))
                for z in zones:
                    exposures.append(self._zonal(z, a, ts, i))
            dst.update_tags(units=c.get("units", ""), source_id=self.id)

        if not samples:
            raise ValueError("no valid pixels inside the AOI in any frame")
        suspect = {i for i, f in enumerate(frame_info) if f.get("same_as")}
        for e in exposures:
            if e["frame"] in suspect:
                e["df"]["quality_flag"] = "suspect"
        if suspect:
            print(f"    {self.id}: {len(suspect)} frames have pixels identical to another frame; "
                  "their exposures are flagged 'suspect'")
        p_lo, p_hi = c.get("stretch", [1, 99])
        lo, hi = (float(x) for x in np.percentile(np.concatenate(samples), [p_lo, p_hi]))
        lo, hi = np.floor(lo), np.ceil(hi)

        # 【中文】第二遍：从标准栅格生成网页帧 / pass 2: web frames from the standard stack
        fmt = c.get("frame_format", "webp")
        with rasterio.open(store_f) as s:
            for i, info in enumerate(frame_info):
                web = to_web(s.read(i + 1), transform, web_bounds, web_w, web_h)
                name = f"{info['t'][:13].replace(':', '')}.{fmt}"
                _save_frame(_encode(web, lo, hi), frame_dir / name, fmt)
                info["image"] = f"series/{self.id}/{name}"

        # 【中文】网页资产矩阵 / web asset × frame matrices
        asset_series = {}
        for z in zones:
            m = np.full((len(z["ids"]), len(frames)), NODATA_I16, dtype="<i2")
            for i, e in enumerate(exposures):
                if e["source"] != z["source"]:
                    continue
                m[e["rows"], e["frame"]] = np.round(e["df"]["lst_mean"].to_numpy() * VALUE_SCALE)
            m.tofile(frame_dir / f"{z['source']}.bin")
            write_json(frame_dir / f"{z['source']}.json", z["ids"])
            asset_series[z["source"]] = {"index": f"series/{self.id}/{z['source']}.json",
                                         "values": f"series/{self.id}/{z['source']}.bin",
                                         "scale": VALUE_SCALE, "nodata": NODATA_I16}

        cmap_name = c.get("colormap", "inferno")
        meta = {
            "id": self.id, "corners": _corners(web_bounds), "merc_bounds": list(web_bounds),
            "size": [web_w, web_h], "range": [lo, hi], "levels": LEVELS,
            "units": c.get("units", ""), "colormap": cmap_name, "stops": ramp_stops(cmap_name, 17),
            "frames": frame_info, "asset_series": asset_series,
        }
        write_json(meta_f, meta)

        table = pd.concat([e["df"] for e in exposures], ignore_index=True) if exposures else None
        if table is not None:
            table = table.assign(lst_source=c.get("lst_source", self.id), source_id=self.id)
        layer = self.base_layer() | {"meta": f"series/{self.id}.json", "frame_count": len(frames),
                                     "time_start": frame_info[0]["t"], "time_end": frame_info[-1]["t"]}
        return AdapterResult(layer=layer, tables={"exposures": table} if table is not None else {})

    # ------------------------------------------------------------------ zonal
    def _zones(self, z: dict, transform, width: int, height: int) -> dict:
        """【中文】每个资产覆盖的像元（像元中心落在几何内；线要素先按 buffer_m 缓冲）。
        小于一个像元的资产退回到质心所在像元。只算一次，所有帧共用。

        Pixels covered by each asset (pixel centre inside the geometry; lines are
        buffered by buffer_m first). Assets smaller than a pixel fall back to the
        pixel under their centroid. Computed once and shared by every frame."""
        assets = self.ctx.load_assets(z["source"])
        if assets.crs.to_epsg() != STORE_CRS:
            assets = assets.to_crs(STORE_CRS)
        geoms = np.asarray(assets.geometry.values)
        if z.get("buffer_m"):
            geoms = shapely.buffer(geoms, float(z["buffer_m"]), cap_style="flat")
        x0, dx, y0, dy = transform.c, transform.a, transform.f, transform.e   # dy < 0
        pix, owner, n_total = [], [], np.zeros(len(geoms), dtype=np.int32)
        for k, g in enumerate(geoms):
            minx, miny, maxx, maxy = g.bounds
            c0, c1 = max(0, int((minx - x0) / dx)), min(width, int(np.ceil((maxx - x0) / dx)))
            r0, r1 = max(0, int((maxy - y0) / dy)), min(height, int(np.ceil((miny - y0) / dy)))
            idx = np.empty(0, dtype=np.int64)
            if c1 > c0 and r1 > r0:
                cc, rr = np.meshgrid(np.arange(c0, c1), np.arange(r0, r1))
                inside = shapely.contains_xy(g, x0 + (cc + 0.5) * dx, y0 + (rr + 0.5) * dy)
                idx = (rr[inside] * width + cc[inside]).astype(np.int64)
            if idx.size == 0:
                pt = g.centroid
                col, row = int((pt.x - x0) / dx), int((pt.y - y0) / dy)
                if 0 <= col < width and 0 <= row < height:
                    idx = np.array([row * width + col], dtype=np.int64)
            pix.append(idx)
            owner.append(np.full(idx.size, k, dtype=np.int32))
            n_total[k] = idx.size
        has = n_total > 0
        if (~has).any():
            print(f"    {self.id}: {int((~has).sum())} assets of {z['source']} are outside the raster")
        pix, owner = np.concatenate(pix), np.concatenate(owner)
        starts = np.searchsorted(owner, np.arange(len(geoms)))
        return {"source": z["source"], "ids": assets["asset_id"].tolist(), "pix": pix, "owner": owner,
                "starts": starts, "n_total": n_total, "has": has}

    def _zonal(self, z: dict, frame: np.ndarray, ts: pd.Timestamp, i: int) -> dict:
        v = frame.ravel()[z["pix"]]
        ok = np.isfinite(v)
        n = len(z["ids"])
        cnt = np.bincount(z["owner"][ok], minlength=n)
        sums = np.bincount(z["owner"][ok], weights=v[ok], minlength=n)
        vmax = np.full(n, np.nan)
        if z["pix"].size:
            mx = np.maximum.reduceat(np.where(ok, v, -np.inf), z["starts"][z["has"]])
            vmax[z["has"]] = mx
        vmax[cnt == 0] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = sums / cnt
        frac = np.divide(cnt, z["n_total"], out=np.zeros(n), where=z["n_total"] > 0)
        rows = np.flatnonzero(cnt > 0)
        df = pd.DataFrame({
            "asset_id": np.asarray(z["ids"], dtype=object)[rows], "timestamp": ts,
            "lst_mean": np.round(mean[rows], 2), "lst_max": np.round(vmax[rows], 2),
            "n_pixels": cnt[rows].astype("int32"),
            # 【中文】有效像元 ≥ 50% 为 ok，否则 partial / ok when ≥ 50% of the asset's pixels are valid
            "quality_flag": np.where(frac[rows] >= 0.5, "ok", "partial"),
        })
        return {"source": z["source"], "frame": i, "rows": rows, "df": df}


def _stats(v: np.ndarray) -> dict:
    if v.size == 0:
        return {"mean": None, "p05": None, "p95": None}
    p05, p95 = np.percentile(v, [5, 95])
    return {"mean": round(float(v.mean()), 2), "p05": round(float(p05), 2), "p95": round(float(p95), 2)}


def _save_frame(la: np.ndarray, path, fmt: str) -> None:
    """【中文】无损保存；WebP 没有灰度模式，灰度复制到 RGB 三个通道（无损压缩几乎不增加体积）。
    Lossless. WebP has no grey mode, so grey is copied into R, G and B."""
    if fmt == "png":
        Image.fromarray(la, mode="LA").save(path, optimize=True)
    else:
        g, a = la[..., 0], la[..., 1]
        Image.fromarray(np.dstack([g, g, g, a]), mode="RGBA").save(path, "WEBP", lossless=True, method=6, exact=True)


def _encode(data: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """【中文】数值 → 灰度 1–255 + alpha；浏览器端按 lo + (g-1)/254·(hi-lo) 还原。
    value → grey 1–255 + alpha; decoded in the browser as lo + (g-1)/254·(hi-lo)."""
    ok = np.isfinite(data)
    g = np.zeros(data.shape, dtype="uint8")
    g[ok] = (1 + np.round(np.clip((data[ok] - lo) / (hi - lo), 0, 1) * LEVELS)).astype("uint8")
    return np.dstack([g, np.where(ok, 255, 0).astype("uint8")])
