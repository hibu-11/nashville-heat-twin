"""
【中文】级联模拟入口：读取标准表 → 抽样参数 → 逐小时模拟 → 验证 → 敏感性分析 → 写结果。
每次运行生成 run_id，记录参数、随机种子、代码版本和输入标准表的构建 run_id（设计方案第 5 节）。

    python -m pipeline.cascade [--runs 400] [--seed 20261027] [--start 2023-06-01] [--end 2023-08-31]
                               [--scenarios 0,2,4]   # 【中文】均匀升温情景（°C），0 = 实测 2023 / uniform warming offsets

Cascade entry point. Writes data/standard/results/<run_id>/ and site/data/twin/results/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

from .adapters.base import write_json
from .build import ROOT, code_version
from .twin.airfield import local_temperatures
from .twin.cascade import Network, c_to_f, pavement, simulate
from .twin.river import mohseni, shed_fraction
from .twin.params import Params
from .twin.validate import auc, outage_vs_temperature, spearman_ci, stratified_auc

# 【中文】进入电力 / 设施模拟的参数（敏感性分析只看这些；C-H4、C-H5 只作背景，C-T1 只用于路面）
# parameters that enter the power/facility simulation (sensitivity is computed for these only)
POWER_PARAMS = ["C-P1", "C-P1.T0", "C-P1.Kd", "C-P1.Td", "C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m",
                "C-P2.tau", "C-P3", "C-P3.sigma", "C-P4", "C-P6", "C-H1", "C-H2", "C-W2", "C-W3", "C-T2", "C-POP2",
                "C-P9", "C-P9.span", "C-P9.Qmin", "C-P9.flow", "C-P9.avail", "C-P9.imp"]


def load(std: Path, name: str):
    f = std / f"{name}.parquet"
    if not f.exists():
        sys.exit(f"missing standard table {f}; run `python -m pipeline.build` first")
    return gpd.read_parquet(f) if name in ("assets", "events") else pd.read_parquet(f)


def river_inputs(cfg, hours):
    """【中文】读取 river_thermal 适配器的逐小时表（河温、流量、TVA 负荷）和模型；没有则返回 None。
    Hourly river / load table and model from the river_thermal dataset, or None."""
    rv = next((d for d in cfg["datasets"] if d["kind"] == "river_thermal"), None)
    if rv is None:
        return None
    std = ROOT / cfg["project"].get("standard_dir", "data/standard") / "river"
    f, mj = std / f"{rv['id']}_hourly.parquet", std / f"{rv['id']}_model.json"
    if not f.exists():
        print(f"[cascade] {rv['id']} not built; no water → power link (R-P0 tier 0)")
        return None
    h = pd.read_parquet(f).set_index("timestamp").reindex(hours)
    m = json.loads(mj.read_text(encoding="utf-8"))
    print(f"[cascade] {rv['id']}: {m['plant_capacity_mw']:,.0f} MW once-through cooled, load data for "
          f"{int(h['load_mw'].notna().sum())} of {len(hours)} hours")
    return {"hourly": h, "model": m, "dataset": rv["id"]}


def river_shed(river, Ta, th, dT):
    """【中文】M-18：每次运行的逐小时火电降额（MW）与轮流停电比例 (N, H)。情景增温同时抬高河温
    （按河温模型）和 TVA 负荷（按 C-P1 斜率）。没有负荷数据的小时不计缺口。
    Per-run hourly derate and shed share; scenario warming raises river temperature and TVA load."""
    if river is None:
        return None, None
    h, sm = river["hourly"], river["model"]["stream_model"]
    tw = mohseni(h["ta7_c"].to_numpy(float) + dT, sm["mu"], sm["alpha"], sm["beta"], sm["gamma"])
    TF = c_to_f(Ta)[None, :]
    beta, T0 = th["C-P1"][:, None], th["C-P1.T0"][:, None]
    scale = (1 + beta * np.maximum(0, TF + dT * 9 / 5 - T0)) / (1 + beta * np.maximum(0, TF - T0))
    load = h["load_mw"].to_numpy(float)[None, :] * scale
    derate, shed = shed_fraction(np.nan_to_num(tw, nan=0.0), np.nan_to_num(h["q_cfs"].to_numpy(float), nan=1e9),
                                 np.nan_to_num(load, nan=0.0), river["model"]["plant_capacity_mw"],
                                 river["model"]["system_capacity_mw"], th)
    return shed, derate


def river_summary(shed, derate):
    if shed is None:
        return None
    return {"runs_with_shed": round(float((shed.max(1) > 0).mean()), 4),
            "shed_hours_mean": round(float((shed > 0).sum(1).mean()), 2),
            "derate_mw_max_mean": round(float(derate.max(1).mean()), 1),
            "derate_hours_mean": round(float((derate > 0).sum(1).mean()), 2)}


def air_field_temperatures(cfg, assets, net, Ta, hours, tz, mode="on"):
    """【中文】读取城市气温场（kind: air_field）的标准栅格，给每个变电站（中心点）和供电分区（内部平均）
    算逐小时气温。没有气温场或 mode = off 时返回 None（全城用 BNA）。
    Local hourly temperatures at substations and zones from the air field; None if unavailable."""
    af = next((d for d in cfg["datasets"] if d["kind"] == "air_field"), None)
    if mode == "off" or af is None:
        return None, None, {"method": "BNA everywhere (A-D4)"}
    std = ROOT / cfg["project"].get("standard_dir", "data/standard") / "air_field"
    tif, mj = std / f"{af['id']}.tif", std / f"{af['id']}_model.json"
    if not tif.exists():
        print(f"[cascade] air field {af['id']} not built; using BNA everywhere (A-D4)")
        return None, None, {"method": "BNA everywhere (A-D4)", "note": "air field not built"}
    geom = assets.set_index("asset_id").geometry
    subs = gpd.GeoSeries(geom.loc[net.sid].centroid.values, crs=assets.crs)
    zones = list(geom.loc[net.zone_id].values)
    Ta_sub, Ta_zone, info = local_temperatures(tif, mj, Ta, hours, tz, subs, zones)
    print(f"[cascade] air field {af['id']}: station offsets {info['station_offset_c']} °C, zone offsets {info['zone_offset_c']} °C")
    return Ta_sub, Ta_zone, info | {"dataset": af["id"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the heat-cascade model v0")
    ap.add_argument("--runs", type=int, default=400, help="Monte Carlo runs with sampled parameters")
    ap.add_argument("--mid-runs", type=int, default=200, help="runs with every parameter at its mid value")
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--start", default="2023-06-01")
    ap.add_argument("--end", default="2023-08-31")
    ap.add_argument("--scenarios", default="0,2,4", help="uniform air-temperature offsets in °C; 0 must be included")
    # 【中文】城市气温场（M-6）：on = 各变电站 / 分区用本地气温；off = 全城用 BNA（v0 的假设 A-D4）
    ap.add_argument("--air-field", choices=["on", "off"], default="on", help="local temperatures from the urban field (M-6)")
    ap.add_argument("--outage-source", default="eaglei_davidson", help="events source_id of the observed outages")
    args = ap.parse_args(argv)
    scen = [float(x) for x in args.scenarios.split(",")]
    if 0.0 not in scen:
        sys.exit("--scenarios must include 0 (the observed 2023 baseline)")

    cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text(encoding="utf-8"))
    proj = cfg["project"]
    tz = proj.get("timezone", "UTC")
    dep_cfg = next(d for d in cfg["datasets"] if d["kind"] == "dependency_rules")
    std = ROOT / proj.get("standard_dir", "data/standard")
    site = ROOT / proj.get("site_data_dir", "site/data") / "twin" / "results"
    site.mkdir(parents=True, exist_ok=True)

    assets, deps, couplings = load(std, "assets"), load(std, "dependencies"), load(std, "couplings")
    drivers, events, exposures = load(std, "drivers"), load(std, "events"), load(std, "exposures")
    build = json.loads((ROOT / proj.get("site_data_dir", "site/data") / "build.json").read_text(encoding="utf-8"))

    # 【中文】驱动：逐小时气温 / driver: hourly air temperature
    hours = pd.date_range(pd.Timestamp(args.start, tz=tz), pd.Timestamp(args.end, tz=tz) + pd.Timedelta(hours=23),
                          freq="h").tz_convert("UTC")
    wide = drivers.pivot_table(index="timestamp", columns="variable", values="value").reindex(hours)
    Ta = wide["air_temp_c"].interpolate(limit_direction="both").to_numpy()
    thunder = wide["thunder"].fillna(0).to_numpy()
    storm = pd.Series(thunder).rolling(7, center=True, min_periods=1).max().to_numpy() > 0   # ±3 h

    params = Params(couplings)
    net = Network(assets, deps, dep_cfg)
    Ta_sub, Ta_zone, air_info = air_field_temperatures(cfg, assets, net, Ta, hours, tz, args.air_field)
    river = river_inputs(cfg, hours)
    print(f"[cascade] {len(net.sid)} substations, {len(net.zone_id)} zones, {int(net.U.sum())} supply edges, "
          f"{int(net.P.sum() / 2)} peer links, {len(hours)} hours")

    # 【中文】各情景使用相同随机数（公共随机数法），情景差异只来自温度
    # common random numbers: every scenario reuses the same draws, so differences come from temperature only
    sims = {}
    for dT in scen:
        rng = np.random.default_rng(args.seed)
        th = params.sample(args.runs, rng)
        print(f"[cascade] Monte Carlo {dT:+.0f} °C: {args.runs} runs (parameters sampled) …")
        shed, derate = river_shed(river, Ta, th, dT)
        sims[dT] = simulate(net, Ta + dT, th, rng, Ta_sub=None if Ta_sub is None else Ta_sub + dT,
                            Ta_zone=None if Ta_zone is None else Ta_zone + dT, shed=shed)
        sims[dT]["river"] = river_summary(shed, derate)
    rng = np.random.default_rng(args.seed)
    th = params.sample(args.runs, rng)
    mc = sims[0.0]
    rng = np.random.default_rng(args.seed + 1)
    th_mid = params.sample(args.mid_runs, rng, mode="mid")
    print(f"[cascade] baseline: {args.mid_runs} runs (parameters at mid) …")
    mid = simulate(net, Ta, th_mid, rng, Ta_sub=Ta_sub, Ta_zone=Ta_zone, shed=river_shed(river, Ta, th_mid, 0.0)[0])
    # 【中文】对照：同样的随机数，但全城用 BNA 一个站（A-D4），量化城市气温场的影响
    # comparison with the same draws but one station for the whole city (A-D4)
    station_only = None
    if Ta_sub is not None:
        print("[cascade] comparison: observed temperature, BNA everywhere (A-D4) …")
        rng = np.random.default_rng(args.seed)
        th_cmp = params.sample(args.runs, rng)
        station_only = simulate(net, Ta, th_cmp, rng)["totals"]

    # 【中文】路面模块（只在有逐小时 LST 的时段）/ pavement module on the LST period
    roads_src = proj.get("chain_check", {}).get("assets", "roads_lst")
    series_src = proj.get("chain_check", {}).get("exposures", "lst_hourly_2023")
    rexp = exposures[(exposures["source_id"] == series_src) & exposures["asset_id"].str.startswith(roads_src + ":")]
    pav = pavement(rexp, th, tz)
    road_len = assets[assets["source_id"] == roads_src].set_index("asset_id").geometry.length
    pav["length_m"] = pav["asset_id"].map(road_len).to_numpy()

    # ------------------------------------------------------------------ validation
    eagle = events[events["source_id"] == args.outage_source].set_index("start_time")["severity"]
    obs = eagle.reindex(hours).fillna(0).to_numpy()          # 【中文】无记录的小时按 0 处理（A-D2）
    day = hours.tz_convert(tz).date
    model = mc["pop_out"].mean(0)
    val = {
        "power_all_hours": spearman_ci(model, obs, day),
        "power_non_storm_hours": spearman_ci(model[~storm], obs[~storm], np.asarray(day)[~storm]),
        "temperature_vs_observed_non_storm": spearman_ci(Ta[~storm], obs[~storm], np.asarray(day)[~storm]),
        "temperature_vs_observed_all": spearman_ci(Ta, obs, day),
        "observed_by_temperature_non_storm": outage_vs_temperature(Ta, obs, storm),
    }
    d_obs = pd.Series(obs, index=hours).groupby(day).max()
    d_mod = pd.Series(model, index=hours).groupby(day).max()
    d_ta = pd.Series(Ta, index=hours).groupby(day).max()
    val["daily_max_model_vs_observed"] = spearman_ci(d_mod.values, d_obs.values, np.arange(len(d_obs)))
    val["daily_tmax_vs_observed"] = spearman_ci(d_ta.values, d_obs.values, np.arange(len(d_obs)))

    # 【中文】路面：311 道路类请求（匹配到路段）作为正例 / 311 road requests matched to segments
    ev311 = events[(events["source_id"] == "hub311_2023") & events["asset_id"].notna()]
    lst_days = rexp["timestamp"].dt.tz_convert(tz).dt.date
    d0, d1 = lst_days.min(), lst_days.max()
    in_win = ev311["start_time"].dt.tz_convert(tz).dt.date.between(d0, d1)
    for label, sel in (("pavement_requests_lst_period", in_win & ev311["event_type"].eq("pavement")),
                       ("road_requests_lst_period", in_win & ev311["event_type"].isin(["pavement", "road_other"])),
                       ("pavement_requests_summer", ev311["event_type"].eq("pavement"))):
        hit = set(ev311.loc[sel, "asset_id"])
        val[label] = auc(pav["p_exceed"], pav["asset_id"].isin(hit)) | {"period": f"{d0} – {d1}" if "lst" in label else "Jun–Aug 2023"}
        y = pav["asset_id"].isin(hit)
        val[label + "_lst_peak"] = auc(pav["lst_daymax_peak"], y)
        val[label + "_t7"] = auc(pav["lst_t7_max"], y)
        # 【中文】混杂检查：只用路段长度的基线，以及按长度五分位分层后的 AUC
        # confounding check: a length-only baseline and the AUC within length quintiles
        val[label + "_length_only"] = auc(pav["length_m"], y)
        val[label + "_within_length_quintiles"] = stratified_auc(pav["lst_t7_max"], y, pav["length_m"])

    # ------------------------------------------------------------------ sensitivity
    tot = mc["totals"]
    # 【中文】级联放大系数 = 过载跳闸次数 / 热失效次数（Eq. 8 的二次失效相对初始失效）
    # amplification = overload trips per thermal failure
    amp = tot["overload"] / np.maximum(1, tot["thermal"])
    sens = []
    for k in POWER_PARAMS:
        v = th[k]
        if np.ptp(v) == 0:          # 【中文】常数参数跳过 / skip constants
            continue
        row = {"param": k, "name": params.table.at[k, "param_name"], "basis": params.table.at[k, "basis"]}
        for out_name, y in (("pop_hours", tot["pop_hours"]), ("compound_pop_hours", tot["compound_pop_hours"]),
                            ("thermal_failures", tot["thermal"]), ("overload_failures", tot["overload"])):
            row[out_name] = round(float(spearmanr(v, y).statistic), 3) if np.std(y) > 0 else None
        sens.append(row)
    sens.sort(key=lambda r: -abs(r["pop_hours"] or 0))

    q = lambda a: {p: round(float(np.percentile(a, p)), 2) for p in (5, 25, 50, 75, 95)} | {"mean": round(float(np.mean(a)), 2)}  # noqa: E731
    sub_risk = pd.DataFrame({"asset_id": net.sid, "name": net.subs["name"].fillna(pd.Series(net.sid).str.split(":").str[-1]),
                             "type": net.subs["stype"],
                             "kv_max": net.subs["kv_max"], "expected_down_hours": mc["hourly"]["p_down"].sum(0),
                             "mean_hourly_p_thermal_peak": mc["hourly"]["p_thermal"].max(0),
                             "theta_h_peak_c": mc["hourly"]["theta_h"].max(0)}).sort_values("expected_down_hours", ascending=False)

    # ------------------------------------------------------------------ write
    stamp = dt.datetime.now(dt.timezone.utc)
    phash = hashlib.sha256(couplings.to_csv(index=False).encode()).hexdigest()[:10]
    run_id = f"cascade-{stamp:%Y%m%dT%H%M%SZ}-{phash}"
    run = {"run_id": run_id, "created": stamp.isoformat(timespec="seconds"), "code_version": code_version(),
           "inputs_build_run_id": build.get("run_id"), "couplings_sha256": phash, "seed": args.seed,
           "runs": args.runs, "mid_runs": args.mid_runs, "period": [args.start, args.end], "timezone": tz,
           "scenarios_delta_c": scen, "air_field": air_info, "outage_source": args.outage_source,
           "hours": len(hours), "network": {"substations": len(net.sid), "zones": len(net.zone_id),
                                             "supply_edges": int(net.U.sum()), "peer_links": int(net.P.sum() / 2),
                                             "hospitals": len(net.hosp), "nursing_homes": len(net.nurs),
                                             "dialysis": len(net.dial), "water_plants": len(net.plants),
                                             "signals": len(net.signals), "roads_with_signals": len(net.roads)}}
    scen_summary = {}
    for dT, r in sims.items():
        t = r["totals"]
        scen_summary[f"{dT:+.0f}"] = {k: q(v) for k, v in t.items()} | {
            "amplification": q(t["overload"] / np.maximum(1, t["thermal"])),
            "share_runs_with_any_failure": round(float((t["thermal"] + t["overload"] > 0).mean()), 3),
            "river": r.get("river"),
            "max_air_temp_c": round(float(np.max(Ta) + dT), 1)}
    summary = run | {
        "population_in_zones": int(net.zone_pop.sum()), "elderly_in_zones": int(net.zone_eld.sum()),
        "mc": {k: q(v) for k, v in tot.items()} | {"amplification": q(amp)},
        "scenarios": scen_summary,
        "mid": {k: q(v) for k, v in mid["totals"].items()},
        "station_only": None if station_only is None else {k: q(v) for k, v in station_only.items()},
        "validation": val, "sensitivity": sens,
        "substations_top": sub_risk.head(15).round(3).to_dict(orient="records"),
        "pavement": {"roads": int(len(pav)), "p_exceed_mean": round(float(pav["p_exceed"].mean()), 3),
                     "roads_p_exceed_over_0_5": int((pav["p_exceed"] > 0.5).sum()),
                     "t7_quantiles": {q_: round(float(pav["lst_t7_max"].quantile(q_ / 100)), 1) for q_ in (5, 50, 95)}},
        "context": {"C-H4_outage_RR_nonaccidental": [params.low["C-H4"], params.mid["C-H4"], params.high["C-H4"]],
                    "C-H5_heat_blackout_amplification_lower_bound": params.mid["C-H5"]},
    }
    res_dir = std / "results" / run_id
    res_dir.mkdir(parents=True, exist_ok=True)
    write_json(res_dir / "run.json", run | {"parameter_draws": {k: v.tolist() for k, v in th.items()}})
    write_json(res_dir / "summary.json", summary)
    pd.DataFrame({"timestamp": np.repeat(hours, len(net.sid)), "asset_id": np.tile(net.sid, len(hours)),
                  "p_down": mc["hourly"]["p_down"].ravel(), "p_thermal": mc["hourly"]["p_thermal"].ravel(),
                  "theta_h_c": mc["hourly"]["theta_h"].ravel()}).to_parquet(res_dir / "substations_hourly.parquet")
    pav.to_parquet(res_dir / "pavement.parquet")

    # 【中文】网页文件 / web outputs
    pct = lambda a, p: np.round(np.percentile(a, p, axis=0), 1).tolist()  # noqa: E731
    write_json(site / "timeseries.json", {
        "run_id": run_id, "start": hours[0].strftime("%Y-%m-%dT%H:%MZ"), "n": len(hours), "timezone": tz,
        "air_temp_c": np.round(Ta, 2).tolist(), "storm": storm.astype(int).tolist(),
        "observed_customers_out": obs.astype(int).tolist(),
        "pop_out_p05": pct(mc["pop_out"], 5), "pop_out_p50": pct(mc["pop_out"], 50), "pop_out_p95": pct(mc["pop_out"], 95),
        "pop_out_mean": np.round(mc["pop_out"].mean(0), 1).tolist(), "pop_out_mid_mean": np.round(mid["pop_out"].mean(0), 1).tolist(),
        "subs_down_mean": np.round(mc["hourly"]["n_down"][:, 0], 3).tolist(),
        "share_runs_out": np.round((mc["pop_out"] > 0).mean(0), 4).tolist(),
        "scenarios": {f"{dT:+.0f}": {"pop_out_mean": np.round(r["pop_out"].mean(0), 1).tolist(),
                                    "share_runs_out": np.round((r["pop_out"] > 0).mean(0), 4).tolist(),
                                    "pop_out_p95": pct(r["pop_out"], 95),
                                    "subs_down_mean": np.round(r["hourly"]["n_down"][:, 0], 3).tolist()}
                      for dT, r in sims.items()},
        "signals_dark_mean": np.round(mc["hourly"]["signals_dark"][:, 0], 2).tolist(),
        "roads_degraded_mean": np.round(mc["hourly"]["roads_degraded"][:, 0], 2).tolist(),
        "water_out_p": np.round(mc["hourly"]["water_out"][:, 0], 4).tolist(),
    })
    # 【中文】节点逐小时失效概率：uint8（×250），行 = 节点，列 = 小时 / per-node hourly probabilities
    nodes = net.sid + net.hosp + net.nurs + net.dial
    files = {}
    for dT, r in sims.items():
        mat = np.concatenate([r["hourly"]["p_down"], r["hourly"]["hosp"], r["hourly"]["nurs"], r["hourly"]["dial"]], axis=1).T
        name = f"p_down_{dT:+.0f}.bin".replace("+", "p").replace("-", "m")
        np.round(np.clip(mat, 0, 1) * 250).astype("uint8").tofile(site / name)
        files[f"{dT:+.0f}"] = name
    write_json(site / "p_down_index.json", {"nodes": nodes, "hours": len(hours), "scale": 250, "files": files,
                                            "zone_substation": dict(zip(net.zone_id, [net.sid[s] if s >= 0 else None for s in net.zone_sub]))})
    write_json(site / "pavement.json", {"run_id": run_id, "metric": "P(7-day max LST > PG high grade)",
                                        "roads": dict(zip(pav["asset_id"], np.round(pav["p_exceed"], 3))),
                                        "t7": dict(zip(pav["asset_id"], pav["lst_t7_max"]))})
    write_json(site / "summary.json", summary)
    # 【中文】路网可达性（pipeline.access）的输入：每个情景中预期降级路段最多的小时，及该小时各路段与设施的失效概率
    # stress hour per scenario for pipeline.access: road degradation and facility outage probabilities
    stress = {"run_id": run_id, "roads": net.roads, "hospitals": net.hosp, "dialysis": net.dial, "scenarios": {}}
    for dT, r in sims.items():
        hh = r["hourly"]
        k = int(np.argmax(hh["roads_degraded"][:, 0]))
        stress["scenarios"][f"{dT:+.0f}"] = {
            "hour_utc": hours[k].isoformat(), "hour_local": hours[k].tz_convert(tz).isoformat(),
            "roads_degraded_mean": round(float(hh["roads_degraded"][k, 0]), 2),
            "p_road_degraded": np.round(hh["roads_p"][k], 4).tolist(),
            "p_hospital_down": np.round(hh["hosp"][k], 4).tolist(), "p_dialysis_down": np.round(hh["dial"][k], 4).tolist()}
    write_json(res_dir / "stress_hours.json", stress)
    write_json(site / "stress_hours.json", stress)
    print(f"[cascade] {run_id}\n  pop-hours without power (median): {summary['mc']['pop_hours'][50]:,.0f}"
          f"\n  thermal failures (median): {summary['mc']['thermal'][50]}, overload trips: {summary['mc']['overload'][50]}"
          f"\n  ρ(model, EAGLE-I) all hours: {val['power_all_hours']['rho']}  non-storm: {val['power_non_storm_hours']['rho']}"
          f"\n  ρ(Ta, EAGLE-I) non-storm: {val['temperature_vs_observed_non_storm']['rho']}"
          f"\n  pavement AUC (LST period): {val['pavement_requests_lst_period']['auc']}")


if __name__ == "__main__":
    main()
