"""
【中文】检验路段夏季地表温度（LST）与车辙深度的关系，作为暂缓环节 D3（路面高温 → 车辙 → 维修成本）的依据。
数据：HPMS 2024 Davidson 路段的车辙深度（英寸）与货车 AADT；路段夏季 LST（nashville_roads_lst_full）。
每个 HPMS 路段取中点，匹配 30 m 内最近的 LST 路段。模型：log(车辙 + 0.01) ~ LST + log 货车 AADT + log AADT + 道路等级，
HC1 稳健标准误。横截面、单年，且路段间空间相关，显著性偏高；只作为"有无信号"的证据，不作因果解释。
HPMS 不公开发布（publish: false），这里只写出汇总结果。
    .venv/bin/python scripts/rutting_lst.py

Cross-sectional test of rut depth against summer road LST (evidence for deferred link D3).
Writes twin/evidence/rutting_lst.json (aggregates only).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

CRS = 32616


def ols_hc1(X: pd.DataFrame, y: np.ndarray) -> tuple[pd.Series, pd.Series, float]:
    A = X.values
    b, *_ = np.linalg.lstsq(A, y, rcond=None)
    e = y - A @ b
    n, k = A.shape
    inv = np.linalg.inv(A.T @ A)
    meat = (A * e[:, None]).T @ (A * e[:, None]) * n / (n - k)
    se = np.sqrt(np.diag(inv @ meat @ inv))
    return pd.Series(b, X.columns), pd.Series(se, X.columns), float(1 - e.var() / y.var())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hpms", default="raw/traffic/hpms_2024_davidson.parquet")
    ap.add_argument("--roads", default="raw/nashville_roads_lst_full.shp")
    ap.add_argument("--out", default="twin/evidence/rutting_lst.json")
    ap.add_argument("--max-dist", type=float, default=30)
    a = ap.parse_args(argv)

    h = gpd.read_parquet(a.hpms)
    h = h[h.rutting.notna()].to_crs(CRS)
    h["mid"] = h.geometry.interpolate(0.5, normalized=True)
    pts = h.set_geometry("mid")[["rutting", "aadt", "aadt_single_unit", "aadt_combination", "f_system", "mid"]]
    roads = gpd.read_file(a.roads).to_crs(CRS)[["lst_mean", "geometry"]]
    j = gpd.sjoin_nearest(pts, roads, max_distance=a.max_dist)
    j = j[~j.index.duplicated()]
    j = j[j.lst_mean.notna()]

    rho, p = spearmanr(j.rutting, j.lst_mean)
    by_class = {}
    for fs, g in j.groupby("f_system"):
        if len(g) > 40:
            r, pv = spearmanr(g.rutting, g.lst_mean)
            by_class[str(int(fs))] = {"n": int(len(g)), "rho": round(float(r), 3), "p": float(f"{pv:.2g}")}

    t = j[j.aadt_combination.notna() & j.aadt.notna()]
    X = pd.get_dummies(t.f_system.astype(int), prefix="f", drop_first=True).astype(float)
    X["lst"] = t.lst_mean
    X["log_truck"] = np.log1p(t.aadt_single_unit.fillna(0) + t.aadt_combination)
    X["log_aadt"] = np.log1p(t.aadt)
    X["const"] = 1.0
    b, se, r2 = ols_hc1(X, np.log(t.rutting.values + 0.01))
    p5, p50, p95 = np.percentile(j.lst_mean, [5, 50, 95])
    r = h.rutting
    out = {
        "source": "HPMS 2024 Davidson (rutting, AADT, truck AADT, f_system) joined to summer road LST (nashville_roads_lst_full)",
        "method": f"section midpoint to nearest LST road within {a.max_dist:.0f} m; OLS log(rut + 0.01 in) ~ LST + log truck AADT + log AADT + f_system, HC1 SE",
        "caveat": "Cross-sectional single year; spatial autocorrelation not modelled, so p-values are optimistic; no pavement age, binder grade or structure. Evidence of a signal, not a causal estimate.",
        "n_sections_with_rutting": int(len(h)),
        "n_matched": int(len(j)),
        "spearman_all": {"rho": round(float(rho), 3), "p": float(f"{p:.2g}")},
        "spearman_by_f_system": by_class,
        "ols": {"n": int(len(t)), "r2": round(r2, 3),
                "lst_per_degC": round(float(b["lst"]), 4), "lst_se": round(float(se["lst"]), 4),
                "log_truck": round(float(b["log_truck"]), 4), "log_truck_se": round(float(se["log_truck"]), 4),
                "log_aadt": round(float(b["log_aadt"]), 4), "log_aadt_se": round(float(se["log_aadt"]), 4)},
        "lst_p5_p50_p95_degC": [round(float(x), 1) for x in (p5, p50, p95)],
        "rut_ratio_p95_vs_p5_lst": round(float(np.exp(b["lst"] * (p95 - p5))), 3),
        "rut_in_p50_p90": [round(float(x), 3) for x in np.percentile(r, [50, 90])],
        "share_ge_0.20in_fair_or_worse": round(float((r >= 0.2).mean()), 3),
        "share_gt_0.40in_poor": round(float((r > 0.4).mean()), 3),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("n_matched", "spearman_all", "ols", "lst_p5_p50_p95_degC", "rut_ratio_p95_vs_p5_lst",
                                          "share_ge_0.20in_fair_or_worse", "share_gt_0.40in_poor")}, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
