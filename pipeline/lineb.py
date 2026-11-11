"""
【中文】B 线第一版（2026-11-10）：高温 → 热病症与就医需求 → 等待时间 → 就医时间。
- zone_dependents：把 HHS emPOWER 各邮编区依赖电力医疗设备的人数，按面积分到供电分区。
- nursing_residents：各养老院的每日平均住户数（CMS）。
- calibrate：用 2014–2023 年 5–9 月（无停电）模拟的室内高温暴露人·小时，回归 Davidson 每年的高温病症急诊人次，
  得到每小时基线就诊数 a 和每人·小时暴露的就诊系数 k（C-H11）。
    python -m pipeline.lineb calibrate

Line B v1 inputs: emPOWER electricity-dependent residents per zone, nursing-home residents, and the calibration of
heat-illness visits on simulated indoor heat exposure (no outages) for 2014–2023.
Writes twin/evidence/lineb_calibration.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

from .build import ROOT
from .cascade import air_field_temperatures, load
from .twin.cascade import Network
from .twin.params import Params

STORE_CRS = 32616


def zone_dependents(assets: gpd.GeoDataFrame, net: Network, path: Path, zcta_path: Path,
                    field: str = "Power_Dependent_Devices_DME") -> np.ndarray:
    """【中文】emPOWER 只给邮编区的人数（无边界），用 ZCTA 边界按面积重叠比例分到供电分区。
    emPOWER gives counts per ZIP without geometry; allocate by area overlap of ZCTA polygons with zones."""
    d = json.loads(path.read_text())
    cnt = pd.DataFrame([f["attributes"] for f in d["features"]])
    cnt = cnt.assign(zcta5=cnt["Zip_Code"].astype(str), n=pd.to_numeric(cnt[field], errors="coerce").fillna(0))
    z = gpd.read_file(zcta_path)[["zcta5", "geometry"]].to_crs(STORE_CRS)
    z["zcta5"] = z["zcta5"].astype(str)
    z = z.merge(cnt[["zcta5", "n"]], on="zcta5", how="inner")
    z["a0"] = z.geometry.area
    zones = assets[assets["asset_type"] == "service_zone"][["asset_id", "geometry"]].to_crs(STORE_CRS)
    ov = gpd.overlay(z[["n", "a0", "geometry"]], zones, how="intersection")
    ov["share"] = ov.geometry.area / ov["a0"]
    per = (ov["n"] * ov["share"]).groupby(ov["asset_id"]).sum()
    return np.array([float(per.get(zid, 0.0)) for zid in net.zone_id])


def nursing_residents(assets: gpd.GeoDataFrame, net: Network,
                      field: str = "Average Number of Residents per Day") -> np.ndarray:
    nh = assets[assets["asset_id"].isin(net.nurs)].set_index("asset_id")
    attrs = nh["attributes"].map(lambda a: json.loads(a) if isinstance(a, str) else (a or {}))
    res = attrs.map(lambda a: pd.to_numeric(a.get(field), errors="coerce"))
    return np.array([float(res.get(i)) if pd.notna(res.get(i)) else 0.0 for i in net.nurs])


def calibrate(argv=None):
    from .twin.core import simulate_core
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2014-2023")
    ap.add_argument("--ed", default="raw/health/tn_hri_annual_ed.json")
    ap.add_argument("--out", default="twin/evidence/lineb_calibration.json")
    a = ap.parse_args(argv)
    y0, y1 = (int(x) for x in a.years.split("-"))

    cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text(encoding="utf-8"))
    proj = cfg["project"]
    tz = proj.get("timezone", "UTC")
    std = ROOT / proj.get("standard_dir", "data/standard")
    dep_cfg = next(d for d in cfg["datasets"] if d["kind"] == "dependency_rules")
    assets, deps, couplings, drivers = load(std, "assets"), load(std, "dependencies"), load(std, "couplings"), load(std, "drivers")
    net = Network(assets, deps, dep_cfg)
    params = Params(couplings)
    rng = np.random.default_rng(1)
    th = params.sample(1, rng, mode="mid")
    wide = drivers.pivot_table(index="timestamp", columns="variable", values="value")

    ed = pd.DataFrame(json.loads((ROOT / a.ed).read_text()))
    ed["count"] = pd.to_numeric(ed["count"], errors="coerce")
    visits = ed[ed["county"] == "Davidson"].assign(year=lambda d: d["year"].astype(int)).set_index("year")["count"]

    rows = []
    for y in range(y0, y1 + 1):
        hours = pd.date_range(pd.Timestamp(f"{y}-05-01", tz=tz), pd.Timestamp(f"{y}-09-30 23:00", tz=tz), freq="h").tz_convert("UTC")
        Ta = wide["air_temp_c"].reindex(hours).interpolate(limit_direction="both").to_numpy()
        if np.isnan(Ta).all():
            continue
        local_h = hours.tz_convert(tz).hour
        day_mask = np.asarray((local_h >= 8) & (local_h < 20))
        Ta_sub, Ta_zone, _ = air_field_temperatures(cfg, assets, net, Ta, hours, tz, "on")
        sim = simulate_core(net, Ta, th, np.random.default_rng(y), day_mask, Ta_sub=Ta_sub, Ta_zone=Ta_zone,
                            shed=None, off=frozenset({"R04"}))          # 【中文】无停电 / no outages
        rows.append({"year": y, "hours": len(hours), "indoor_pop_hours": float(sim["totals"]["indoor_pop_hours"][0]),
                     "visits": float(visits.get(y, np.nan))})
    df = pd.DataFrame(rows).dropna()
    X = np.c_[np.ones(len(df)), df["indoor_pop_hours"]]
    yv = df["visits"].to_numpy()
    b, *_ = np.linalg.lstsq(X, yv, rcond=None)
    e = yv - X @ b
    cov = e.var(ddof=2) * np.linalg.inv(X.T @ X)
    rho, p = spearmanr(df["indoor_pop_hours"], df["visits"])
    H = float(df["hours"].mean())
    out = {"source": "Tennessee Department of Health heat-illness ED visits, Davidson, by year (tdh_hri_ed); simulated indoor heat exposure with mid parameters and no outages (core model, May–September)",
           "years": df["year"].tolist(), "table": df.round(1).to_dict(orient="records"),
           "model": "annual visits = a_season + k · indoor heat person-hours",
           "a_season": round(float(b[0]), 2), "k_per_person_hour": float(f"{b[1]:.4g}"), "k_se": float(f"{np.sqrt(cov[1, 1]):.3g}"),
           "a_per_hour": float(f"{b[0] / H:.4g}"), "season_hours": H,
           "r2": round(float(1 - e.var() / yv.var()), 3), "spearman": {"rho": round(float(rho), 3), "p": round(float(p), 3)},
           "caveat": "Ten annual points; exposure is simulated indoor heat (homes without AC dominate), not observed. 2020 visits are low (COVID-19)."}
    Path(ROOT / a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("a_season", "k_per_person_hour", "k_se", "a_per_hour", "r2", "spearman")}, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        calibrate(sys.argv[2:])
    else:
        raise SystemExit("usage: python -m pipeline.lineb calibrate [--years 2014-2023]")
