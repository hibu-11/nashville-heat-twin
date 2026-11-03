"""
【中文】路网可达性（PIPELINE_SPEC M-28 / M-29，关系 R-T4 tier 2、R-H3）。在级联模拟之后运行：
    python -m pipeline.access [--cell-m 250]
读取标准表（路段、HPMS、TMAS、医院、透析中心、消防 / 急救站、供电分区、建筑）和级联输出 stress_hours.json，
计算人口网格到最近可用设施的行程时间，比较以下情况：
    night / am_peak / pm_peak   正常运行（BPR，TMAS 工作日小时曲线）
    stress <情景>               该情景中预期降级路段最多的小时：信号灯熄灭按期望通行能力折减，
                                停电概率 ≥ 0.5 的医院 / 透析中心视为不可用
    all_signals_dark_pm         压力测试：晚高峰全部信号控制路段熄灭（全城大停电的上限情形）
人口网格：分区人口按建筑面积分到建筑，再汇总到 cell_m 网格（M-39 的简化版）。

Network access after the cascade run (M-28 / M-29). Writes access.json and access_grid.geojson.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from .adapters.base import write_json
from .build import ROOT
from .twin import traffic
from .twin.params import Params
from .twin.rules import attrs


def population_cells(buildings, zones, cell_m):
    """【中文】分区人口按建筑占地面积分配到建筑，再按网格汇总；网格中心取人口加权的建筑中心。
    Zone population → buildings by footprint area → grid cells (population-weighted centres)."""
    za = attrs(zones)
    z = gpd.GeoDataFrame({"zone": zones["asset_id"], "pop": pd.to_numeric(za["pop_total"], errors="coerce").fillna(0),
                          "eld": pd.to_numeric(za["pop_elderly"], errors="coerce").fillna(0)},
                         geometry=zones.geometry, crs=zones.crs)
    b = gpd.GeoDataFrame({"area": buildings.geometry.area}, geometry=buildings.geometry.centroid, crs=buildings.crs)
    b = gpd.sjoin(b, z, predicate="within", how="inner")
    tot = b.groupby("zone")["area"].transform("sum")
    b["p"] = b["pop"] * b["area"] / tot
    b["e"] = b["eld"] * b["area"] / tot
    b["cx"], b["cy"] = np.floor(b.geometry.x / cell_m).astype(int), np.floor(b.geometry.y / cell_m).astype(int)
    b["wx"], b["wy"] = b.geometry.x * b["p"], b.geometry.y * b["p"]
    c = b.groupby(["cx", "cy"]).agg(pop=("p", "sum"), eld=("e", "sum"), wx=("wx", "sum"), wy=("wy", "sum")).reset_index()
    c = c[c["pop"] > 0]
    c["x"], c["y"] = c["wx"] / c["pop"], c["wy"] / c["pop"]
    return c.drop(columns=["wx", "wy"])


def summarise(t, pop, thr):
    ok = np.isfinite(t)
    if not ok.any():   # 【中文】该类设施全部不可用 / no facility of this type is available
        return {"pop_mean_min": None, "pop_p90_min": None, "max_min": None, f"pop_share_over_{thr}_min": 1.0,
                "pop_unreachable_share": 1.0}
    w = pop[ok]
    tt = t[ok]
    o = np.argsort(tt)
    cw = np.cumsum(w[o]) / w.sum()
    return {"pop_mean_min": round(float(np.average(tt, weights=w)), 2),
            "pop_p90_min": round(float(tt[o][np.searchsorted(cw, 0.9)]), 2),
            "max_min": round(float(tt.max()), 2),
            f"pop_share_over_{thr}_min": round(float(w[tt > thr].sum() / pop.sum()), 4),
            "pop_unreachable_share": round(float(pop[~ok].sum() / pop.sum()), 4)}


def prepare(cfg: dict, std: Path, assets=None, deps=None, drivers=None, params=None, cell_m: float = 250.0,
            verbose: bool = True) -> dict:
    """【中文】准备路网、TMAS 小时曲线、人口网格和设施节点（M-28 / M-29），供 evaluate 反复调用。
    Network, hourly profile, population cells and facility nodes, reused by evaluate()."""
    proj = cfg["project"]
    tz = proj.get("timezone", "UTC")
    ac = proj.get("access", {})
    assets = gpd.read_parquet(std / "assets.parquet") if assets is None else assets
    deps = pd.read_parquet(std / "dependencies.parquet") if deps is None else deps
    drivers = pd.read_parquet(std / "drivers.parquet") if drivers is None else drivers
    params = Params(pd.read_parquet(std / "couplings.parquet")) if params is None else params
    by = lambda sid: assets[assets["source_id"] == sid]  # noqa: E731

    net = traffic.build_network(by(ac.get("roads", "roads_lst")), by(ac.get("hpms", "hpms_2024")))
    eta = traffic.hourly_profile(drivers[drivers["source_id"] == ac.get("counts", "tmas_2023")], tz)
    cells = population_cells(assets[assets["asset_type"] == "building"], assets[assets["asset_type"] == "service_zone"], cell_m)
    cells["node"] = traffic.snap(net, cells[["x", "y"]].to_numpy(), max_m=ac.get("snap_m", 500))
    cells = cells[cells["node"] >= 0].reset_index(drop=True)
    dest = {}
    for key, sid, thr in (("hospital", "hospitals", ac.get("hospital_min", 15)),
                          ("dialysis", "dialysis", ac.get("dialysis_min", 15)),
                          ("ems", "osm_fire_stations", ac.get("ems_min", 8))):
        d = by(sid)
        pts = d.geometry.representative_point()
        nodes = traffic.snap(net, np.c_[pts.x, pts.y], max_m=ac.get("snap_m", 500))
        dest[key] = {"ids": list(d["asset_id"]), "nodes": nodes, "thr": thr}
        if verbose:
            print(f"[access] {key}: {len(d)} facilities, {int((nodes >= 0).sum())} on the network")
    controlled = set(deps.loc[deps["dep_type"] == "control", "to_asset"])
    if verbose:
        print(f"[access] network {net['stats']}")
    return {"net": net, "edges": net["edges"], "eta": eta, "cells": cells, "pop": cells["pop"].to_numpy(),
            "cell_nodes": cells["node"].to_numpy(), "dest": dest, "cell_m": cell_m, "crs": assets.crs,
            "is_ctl": net["edges"]["road_id"].isin(controlled).to_numpy(),
            "cap_lane": {"fwy": params["C-T6.cap_fwy"], "art": params["C-T6.cap_art"], "loc": params["C-T6.cap_loc"]},
            "A": params["C-T6.a"], "B": params["C-T6.b"], "phi_dark": params["C-T5"]}


def evaluate(ctx: dict, hour_local: int, phi=None, down=None, summary: bool = True):
    """【中文】给定当地小时、路段通行能力系数 phi 和设施失效 down（id → 概率或 0/1），算各格到最近可用设施的时间。
    Travel time from every cell to the nearest available facility for one hour, capacity factor and outage set."""
    w = traffic.travel_time(ctx["edges"], ctx["eta"][hour_local], ctx["cap_lane"], ctx["A"], ctx["B"], phi)
    out, times = {"hour_local": hour_local}, {}
    for key, d in ctx["dest"].items():
        ok = [n for n, i in zip(d["nodes"], d["ids"]) if n >= 0 and not (down and down.get(i, 0) >= 0.5)]
        t = traffic.nearest_time(ctx["net"], w, ok)[ctx["cell_nodes"]]
        times[key] = t
        if summary:
            out[key] = summarise(t, ctx["pop"], d["thr"]) | {"facilities_available": len(ok)}
    return out, times


def main(argv=None):
    ap = argparse.ArgumentParser(description="Network access to facilities (M-28 / M-29)")
    ap.add_argument("--cell-m", type=float, default=250.0)
    ap.add_argument("--stress", default=None, help="stress_hours.json from pipeline.cascade or pipeline.core (default: latest full-model run)")
    a = ap.parse_args(argv)
    cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text(encoding="utf-8"))
    proj = cfg["project"]
    std = ROOT / proj.get("standard_dir", "data/standard")
    site = ROOT / proj.get("site_data_dir", "site/data") / "twin" / "results"
    stress_path = Path(a.stress) if a.stress else site / "stress_hours.json"
    stress = json.loads(stress_path.read_text(encoding="utf-8"))
    site = stress_path.parent       # 【中文】结果写在所用 stress_hours.json 旁边（完整或骨架模型）/ outputs sit next to the stress file

    ctx = prepare(cfg, std, cell_m=a.cell_m)
    net, edges, cells, pop, dest, is_ctl = ctx["net"], ctx["edges"], ctx["cells"], ctx["pop"], ctx["dest"], ctx["is_ctl"]
    eta, cap_lane, A, B, phi_dark = ctx["eta"], ctx["cap_lane"], ctx["A"], ctx["B"], ctx["phi_dark"]
    assets_crs = ctx["crs"]

    res, grids = {}, {}
    for label, h in (("night", 3), ("am_peak", 8), ("pm_peak", 17)):
        res[label], grids[label] = evaluate(ctx, h)
    res["all_signals_dark_pm"], grids["all_signals_dark_pm"] = evaluate(ctx, 17, np.where(is_ctl, phi_dark, 1.0))

    road_idx = {r: i for i, r in enumerate(stress["roads"])}
    for scen, s in stress["scenarios"].items():
        p_road = np.array(s["p_road_degraded"])
        p_e = np.array([p_road[road_idx[r]] if r in road_idx else 0.0 for r in edges["road_id"]])
        phi = 1 - (1 - phi_dark) * p_e
        down = dict(zip(stress["hospitals"], s["p_hospital_down"])) | dict(zip(stress["dialysis"], s["p_dialysis_down"]))
        h = pd.Timestamp(s["hour_local"]).hour
        r, g = evaluate(ctx, h, phi, down)
        base, _ = evaluate(ctx, h)
        r |= {"hour_local_iso": s["hour_local"], "roads_degraded_mean": s["roads_degraded_mean"],
              "delta_pop_mean_min": {k: None if r[k]["pop_mean_min"] is None else round(r[k]["pop_mean_min"] - base[k]["pop_mean_min"], 3) for k in dest}}
        res[f"stress_{scen}"], grids[f"stress_{scen}"] = r, g
        print(f"[access] stress {scen} at {s['hour_local']}: Δ mean minutes {r['delta_pop_mean_min']}, facilities available { {k: r[k]['facilities_available'] for k in dest} }")

    summary = {"run_id": stress["run_id"], "method": "PIPELINE_SPEC M-28 / M-29", "cell_m": a.cell_m,
               "network": net["stats"], "population_in_cells": int(pop.sum()), "cells": int(len(cells)),
               "hourly_profile_weekday": np.round(eta, 4).tolist(),
               "parameters": {"C-T5": phi_dark, "C-T6.a": A, "C-T6.b": B, "cap_lane": cap_lane},
               "controlled_edge_share": round(float(is_ctl.mean()), 3), "conditions": res}
    for k in ("pm_peak", "all_signals_dark_pm"):
        print(f"[access] {k}: hospital mean {res[k]['hospital']['pop_mean_min']} min, EMS mean {res[k]['ems']['pop_mean_min']} min")
    write_json(site / "access.json", summary)
    write_json(std / "results" / stress["run_id"] / "access.json", summary)

    # 【中文】网页网格：晚高峰、全城信号熄灭、各情景压力小时的医院 / 急救时间 / grid for the viewer
    g = gpd.GeoDataFrame(cells[["pop", "eld"]].round(1),
                         geometry=gpd.points_from_xy((cells["x"] // a.cell_m + 0.5) * a.cell_m,
                                                     (cells["y"] // a.cell_m + 0.5) * a.cell_m),
                         crs=assets_crs).buffer(a.cell_m / 2, cap_style="square")
    g = gpd.GeoDataFrame(cells[["pop", "eld"]].round(1), geometry=g, crs=assets_crs)
    for label, t in grids.items():
        for key in ("hospital", "ems"):
            g[f"{key}_{label}"] = np.round(t[key], 2)
    g.to_crs(4326).to_file(site / "access_grid.geojson", driver="GeoJSON")
    print(f"[access] wrote {site / 'access.json'} and access_grid.geojson ({len(g)} cells)")


if __name__ == "__main__":
    main()
