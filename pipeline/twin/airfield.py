"""
【中文】城市气温场（docs/PIPELINE_SPEC.md M-6）：用 2022 年早 / 午 / 晚三次走航测温标定回归模型，
把机场站（BNA）的逐小时气温扩展成 30 m 的气温场，替换"全城用一个站"的假设 A-D4。

    a_p(x) = Σ_k b_{k,p} · z̃_k(x)                      每个时段 p 的气温距平（相对该次走航平均）
    θ_A(x, t) = θ_BNA(t) + A(x, h(t)) − A(x_BNA, h(t))    A 为按当地时刻在三个时段间线性插值的距平

预测因子 z_k（标准化后、截断到训练范围）：不透水面、林地比例（NLCD 2021）、水体比例与离水距离、
高程与地形位置（3DEP）。走航点先聚合到 100 m 网格，用 1 km 空间分块交叉验证评价。

Urban air-temperature field (PIPELINE_SPEC M-6): regressions fitted on the 2022 morning /
afternoon / evening traverses turn the BNA hourly series into a 30 m field, replacing the
single-station assumption A-D4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy.ndimage import distance_transform_edt, uniform_filter

F_TO_C = lambda f: (np.asarray(f, float) - 32.0) * 5.0 / 9.0  # noqa: E731

# 【中文】NLCD 类别：11 开阔水体，41–43 林地 / NLCD classes: 11 open water, 41–43 forest
WATER, FOREST = (11,), (41, 42, 43)
PREDICTORS = ["imp_90", "imp_510", "forest_90", "forest_510", "water_990", "log_dist_water", "elev", "tpi_990"]


def predictor_grids(dem_path, imp_path, lc_path) -> tuple[dict, rasterio.Affine, str]:
    """【中文】在 3DEP 高程网格（EPSG:32616，约 30 m）上计算预测因子；窗口为 3、17、33 个像元。
    Predictors on the DEM grid (EPSG:32616, ~30 m); focal windows of 3, 17 and 33 pixels."""
    with rasterio.open(dem_path) as d:
        elev = d.read(1).astype("float64")
        tr, crs, shape = d.transform, d.crs, (d.height, d.width)
    elev[elev < -100] = np.nan
    px = abs(tr.a)

    def warp(path, resampling):
        dst = np.full(shape, np.nan)
        with rasterio.open(path) as s:
            reproject(rasterio.band(s, 1), dst, src_nodata=s.nodata, dst_transform=tr, dst_crs=crs,
                      dst_nodata=np.nan, resampling=resampling)
        return dst

    imp = warp(imp_path, Resampling.average)
    imp[(imp < 0) | (imp > 100)] = np.nan
    lc = warp(lc_path, Resampling.nearest)
    water = np.isin(lc, WATER).astype(float)
    forest = np.isin(lc, FOREST).astype(float)
    fill = lambda a: np.where(np.isfinite(a), a, np.nanmean(a))  # noqa: E731
    focal = lambda a, n: uniform_filter(fill(a), size=n, mode="nearest")  # noqa: E731
    g = {
        "imp_90": focal(imp / 100, 3), "imp_510": focal(imp / 100, 17),
        "forest_90": focal(forest, 3), "forest_510": focal(forest, 17),
        "water_990": focal(water, 33),
        "log_dist_water": np.log1p(distance_transform_edt(water < 0.5) * px),
        "elev": fill(elev), "tpi_990": fill(elev) - focal(elev, 33),
    }
    return g, tr, str(crs)


def sample(grids: dict, tr, x, y) -> pd.DataFrame:
    """【中文】最近像元取值 / nearest-pixel values at points (x, y in the grid CRS)."""
    col = np.floor((np.asarray(x) - tr.c) / tr.a).astype(int)
    row = np.floor((np.asarray(y) - tr.f) / tr.e).astype(int)
    h, w = next(iter(grids.values())).shape
    ok = (row >= 0) & (row < h) & (col >= 0) & (col < w)
    out = {k: np.full(len(col), np.nan) for k in grids}
    for k, a in grids.items():
        out[k][ok] = a[row[ok], col[ok]]
    return pd.DataFrame(out)


def aggregate_points(pts: pd.DataFrame, cell_m: float) -> pd.DataFrame:
    """【中文】走航点密集且相邻点高度相关，先按 cell_m 网格取平均 / average dense traverse points per cell."""
    key = (np.floor(pts["x"] / cell_m).astype(int).astype(str) + "_" + np.floor(pts["y"] / cell_m).astype(int).astype(str))
    return pts.groupby(key).mean(numeric_only=True).assign(n_points=pts.groupby(key).size())


def fit_period(cells: pd.DataFrame, block_m: float = 1000.0, folds: int = 5, ridge: float = 1.0, seed: int = 0) -> dict:
    """【中文】标准化后的岭回归（λ 很小，只为数值稳定），并做空间分块交叉验证。
    Ridge regression on standardised predictors (small λ for stability) with spatial block CV."""
    X = cells[PREDICTORS].to_numpy(float)
    y = cells["anom_c"].to_numpy(float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0

    def solve(Xs, ys):
        A = np.c_[np.ones(len(Xs)), Xs]
        reg = ridge * np.eye(A.shape[1])
        reg[0, 0] = 0.0
        return np.linalg.solve(A.T @ A + reg, A.T @ ys)

    Z = (X - mu) / sd
    coef = solve(Z, y)
    blocks = (np.floor(cells["x"] / block_m).astype(int) * 100_003 + np.floor(cells["y"] / block_m).astype(int)).to_numpy()
    ub = np.unique(blocks)
    fold_of = dict(zip(ub, np.random.default_rng(seed).integers(0, folds, len(ub))))
    f = np.array([fold_of[b] for b in blocks])
    pred = np.full(len(y), np.nan)
    for k in range(folds):
        tr_, te = f != k, f == k
        if te.any() and tr_.sum() > len(PREDICTORS) + 1:
            c = solve(Z[tr_], y[tr_])
            pred[te] = np.c_[np.ones(te.sum()), Z[te]] @ c
    resid = y - pred
    return {
        "intercept": float(coef[0]), "coef_std": dict(zip(PREDICTORS, np.round(coef[1:], 4).tolist())),
        "mean": dict(zip(PREDICTORS, mu.tolist())), "sd": dict(zip(PREDICTORS, sd.tolist())),
        "z_min": dict(zip(PREDICTORS, Z.min(0).tolist())), "z_max": dict(zip(PREDICTORS, Z.max(0).tolist())),
        "anom_range": [float(y.min()), float(y.max())],
        "n_cells": int(len(y)), "n_blocks": int(len(ub)),
        "cv_rmse_c": round(float(np.sqrt(np.nanmean(resid ** 2))), 3),
        "null_rmse_c": round(float(np.sqrt(np.mean((y - y.mean()) ** 2))), 3),
        "cv_r2": round(float(1 - np.nanmean(resid ** 2) / np.var(y)), 3),
    }


def predict(model: dict, grids: dict) -> np.ndarray:
    """【中文】把模型应用到整个网格；预测因子截断到训练范围，距平截断到观测范围，避免外推。
    Apply to the grid; predictors clipped to the training range and anomalies to the observed range."""
    shape = next(iter(grids.values())).shape
    out = np.full(shape, model["intercept"])
    for k in PREDICTORS:
        z = (grids[k] - model["mean"][k]) / model["sd"][k]
        out = out + model["coef_std"][k] * np.clip(z, model["z_min"][k], model["z_max"][k])
    return np.clip(out, *model["anom_range"])


def hour_weights(hour_local: np.ndarray, anchors: list[float]) -> np.ndarray:
    """【中文】三个时段（早、午、晚）之间按当地时刻线性插值的权重，夜间从傍晚过渡到次日早晨。
    返回 (len(hour), 3)。Linear weights between the morning / afternoon / evening anchors;
    the night interpolates from evening to the next morning."""
    h = np.asarray(hour_local, float) % 24
    m, a, e = anchors
    w = np.zeros((len(h), 3))
    s1 = (h >= m) & (h < a)
    w[s1, 0], w[s1, 1] = (a - h[s1]) / (a - m), (h[s1] - m) / (a - m)
    s2 = (h >= a) & (h < e)
    w[s2, 1], w[s2, 2] = (e - h[s2]) / (e - a), (h[s2] - a) / (e - a)
    s3 = ~(s1 | s2)
    span = 24 - e + m
    since = (h[s3] - e) % 24
    w[s3, 2], w[s3, 0] = 1 - since / span, since / span
    return w


def offsets(fields: np.ndarray, ref_offset: np.ndarray, hour_local: np.ndarray, anchors: list[float]) -> np.ndarray:
    """【中文】fields：(n_assets, 3) 各资产三个时段的距平；ref_offset：(3,) BNA 处的距平。
    返回 (n_hours, n_assets) 的气温修正量 θ_A(x,t) − θ_BNA(t)。
    Per-asset hourly correction relative to BNA, shape (hours, assets)."""
    w = hour_weights(hour_local, anchors)
    return w @ (np.asarray(fields) - np.asarray(ref_offset)[None, :]).T


def match_dates(asos: pd.DataFrame, targets_c: list[float], hours_local: list[float], months=(6, 7, 8, 9), year=2022, top=3):
    """【中文】走航文件没有日期：在 ASOS 中找早 / 午 / 晚气温与三次走航平均最接近的日子（候选）。
    The traverse files carry no date: rank days whose BNA morning / afternoon / evening temperatures
    best match the traverse means (candidates only)."""
    s = asos[(asos.index.year == year) & asos.index.month.isin(months)]
    rows = []
    for day, g in s.groupby(s.index.date):
        vals = []
        for hl in hours_local:
            v = g[(g.index.hour == int(hl))]
            vals.append(float(v.iloc[0]) if len(v) else np.nan)
        if np.all(np.isfinite(vals)):
            rows.append((str(day), vals, float(np.sqrt(np.mean((np.array(vals) - np.array(targets_c)) ** 2)))))
    rows.sort(key=lambda r: r[2])
    return [{"date": d, "bna_c": [round(v, 1) for v in vals], "rmse_c": round(r, 2)} for d, vals, r in rows[:top]]


def asset_fields(tif, points, polygons=None) -> tuple[np.ndarray, np.ndarray | None]:
    """【中文】从 3 波段距平栅格取资产的距平：点取所在像元，多边形取内部像元平均（无像元时取代表点）。
    返回 (n_points, 3) 与 (n_polygons, 3)。points / polygons 为 EPSG:32616 的 GeoSeries。
    Anomalies at assets: the pixel under each point, the mean of pixels inside each polygon."""
    import shapely

    with rasterio.open(tif) as r:
        a, tr = r.read().astype("float64"), r.transform
    h, w = a.shape[1:]

    def at(x, y):
        col = np.clip(np.floor((np.asarray(x) - tr.c) / tr.a).astype(int), 0, w - 1)
        row = np.clip(np.floor((np.asarray(y) - tr.f) / tr.e).astype(int), 0, h - 1)
        return a[:, row, col].T

    pts = at(points.x, points.y)
    if polygons is None:
        return pts, None
    xs = tr.c + (np.arange(w) + 0.5) * tr.a
    ys = tr.f + (np.arange(h) + 0.5) * tr.e
    gx, gy = np.meshgrid(xs, ys)
    out = np.zeros((len(polygons), 3))
    for i, poly in enumerate(polygons):
        x0, y0, x1, y1 = poly.bounds
        sel = (gx >= x0) & (gx <= x1) & (gy >= y0) & (gy <= y1)
        inside = np.zeros_like(sel)
        inside[sel] = shapely.contains_xy(poly, gx[sel], gy[sel])
        if inside.any():
            out[i] = np.nanmean(a[:, inside], axis=1)
        else:
            rp = poly.representative_point()
            out[i] = at([rp.x], [rp.y])[0]
    return pts, out


def local_temperatures(tif, model_json, ta, hours_utc, tz, points, polygons):
    """【中文】由 BNA 逐小时气温得到各点 / 各多边形的逐小时气温（M-6）。返回 (Ta_pts, Ta_polys, info)。
    Hourly temperatures at points and polygons from the BNA series (M-6)."""
    import json

    m = json.loads(open(model_json, encoding="utf-8").read())
    ref = np.array([m["reference_anomaly_c"][p] for p in ("morning", "afternoon", "evening")])
    hl = hours_utc.tz_convert(tz).hour.to_numpy()
    fp, fz = asset_fields(tif, points, polygons)
    op = offsets(fp, ref, hl, m["anchors_local_hour"])
    oz = offsets(fz, ref, hl, m["anchors_local_hour"])
    ta = np.asarray(ta, float)[:, None]
    info = {"method": "PIPELINE_SPEC M-6", "source": str(tif),
            "station_offset_c": {"min": round(float(op.min()), 2), "mean": round(float(op.mean()), 2), "max": round(float(op.max()), 2)},
            "zone_offset_c": {"min": round(float(oz.min()), 2), "mean": round(float(oz.mean()), 2), "max": round(float(oz.max()), 2)},
            "cv_rmse_c": {p: m["models"][p]["cv_rmse_c"] for p in m["models"]}}
    return ta + op, ta + oz, info
