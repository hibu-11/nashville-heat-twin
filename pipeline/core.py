"""
【中文】精简主线模型（骨架）的入口。链条与取舍理由见 docs/CORE_MODEL.md 和 twin/core.yaml。
完整模型仍是 `python -m pipeline.cascade`（并保存在 git 分支 full-model / 标签 full-model-v1）。

    python -m pipeline.core [--runs 2000] [--seed 20261027] [--start 2023-06-01] [--end 2023-08-31]
                            [--scenarios 0,2,4] [--air-field on|off]

输出 data/standard/results/<run_id>/ 与 site/data/twin/core/（summary.json、timeseries.json、stress_hours.json）。
stress_hours.json 与完整模型格式相同，可直接给 `python -m pipeline.access --stress …` 使用。

Core (skeleton) model entry point. The full model remains `python -m pipeline.cascade`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

from . import access, lineb
from .adapters.base import write_json
from .build import ROOT, code_version
from .cascade import air_field_temperatures, load, river_inputs
from .twin.cascade import Network, c_to_f
from .twin.core import CORE_PARAMS, simulate_core
from .twin.params import Params
from .twin.river import shed_fraction
from .twin.validate import spearman_ci

# 【中文】与完整模型对比的指标 / outputs compared with the full model
COMPARE = ["thermal", "pop_hours", "dialysis_hours", "hospital_hours", "water_out_hours", "shed_station_hours"]


def adequacy_shed(river, Ta, th, dT):
    """【中文】K4：只含负荷侧的系统缺口。TVA 逐小时负荷按 C-P1 斜率随情景增温放大，
    与可用容量 a·C_sys + P_imp 比较；不含河温降额（完整模型 M-18 的供给侧）。
    K4: demand-side shortfall only (no river derating). Returns (N, H) shed share or None."""
    if river is None:
        return None
    h = river["hourly"]
    TF = c_to_f(Ta)[None, :]
    beta, T0 = th["C-P1"][:, None], th["C-P1.T0"][:, None]
    scale = (1 + beta * np.maximum(0, TF + dT * 9 / 5 - T0)) / (1 + beta * np.maximum(0, TF - T0))
    load_mw = np.nan_to_num(h["load_mw"].to_numpy(float), nan=0.0)[None, :] * scale
    H = len(Ta)
    _, shed = shed_fraction(np.zeros(H), np.full(H, 1e9), load_mw, 0.0, river["model"]["system_capacity_mw"], th)
    return shed


# 【中文】研究区内某类设施全部不可达时，对受影响人口计的就医时间增量（假设；研究区外的设施不在路网里）
# Added minutes counted for cells that lose every facility of a type inside the area (assumption: facilities outside
# the area are not on the network).
LOST_PENALTY_MIN = 30.0


def access_runs(ctx, net, sim, th, hours, tz, off=frozenset()):
    """【中文】K8：每次运行在其降级路段最多的小时，按该次运行实际熄灭的信号灯（通行能力 × φ_dark）和实际停电的
    医院 / 透析中心，计算各人口格到最近可用设施的时间，与同一小时的正常情况相减。从未降级的运行变化为 0。
    K8: per run, at its hour with the most degraded segments, travel time with that run's dark signals and
    facility outages minus the normal time at the same hour. Runs that never degrade contribute zero.
    off: "R14" (or R15 / R16) ignores dark-signal capacity loss; "R17" ignores facility closures.
    care_time_loss = sum over hospital, dialysis and EMS of the population-mean added minutes, with cells that lose
    every facility of a type counted at LOST_PENALTY_MIN."""
    no_phi = bool(off & {"R14", "R15", "R16"})
    edges, pop = ctx["edges"], ctx["pop"]
    ridx = {r: i for i, r in enumerate(net.roads)}
    e_road = np.array([ridx.get(r, -1) for r in edges["road_id"]])
    ctl = e_road >= 0
    w = sim["worst"]
    N = len(w["hour"])
    keys = list(ctx["dest"])
    m = {k: {"delta": np.zeros(N), "affected_pop": np.zeros(N), "cell_max": np.zeros(N), "over_thr": np.zeros(N),
             "lost": np.zeros(N, bool), "pen": np.zeros(N)} for k in keys}
    local = hours.tz_convert(tz).hour
    base = {}
    for r in np.where(w["hour"] >= 0)[0]:
        lh = int(local[w["hour"][r]])
        if lh not in base:
            base[lh] = access.evaluate(ctx, lh, summary=False)[1]
        phi = np.ones(len(edges))
        if not no_phi:
            phi[ctl] = np.where(w["roads"][r, e_road[ctl]], th["C-T5"][r], 1.0)
        down = {} if "R17" in off else (
            {i: 1.0 for i, d in zip(net.hosp, w["hosp"][r]) if d} | {i: 1.0 for i, d in zip(net.dial, w["dial"][r]) if d})
        _, t = access.evaluate(ctx, lh, phi, down, summary=False)
        for k in keys:
            t0, t1 = base[lh][k], t[k]
            ok = np.isfinite(t0)
            dt_ = np.where(ok & np.isfinite(t1), t1 - t0, np.nan)
            m[k]["lost"][r] = bool((ok & ~np.isfinite(t1)).any())
            d = np.nan_to_num(dt_, nan=0.0)
            m[k]["delta"][r] = float((d * pop).sum() / pop.sum())
            dp = np.where(ok & ~np.isfinite(t1), LOST_PENALTY_MIN, d)
            m[k]["pen"][r] = float((dp * pop).sum() / pop.sum())
            m[k]["affected_pop"][r] = float(pop[d > 1.0].sum())
            m[k]["cell_max"][r] = float(d.max())
            thr = ctx["dest"][k]["thr"]
            m[k]["over_thr"][r] = float(pop[(t1 > thr) & ~(t0 > thr)].sum())
    q = lambda a: {p_: round(float(np.percentile(a, p_)), 3) for p_ in (50, 95, 99)} | {"mean": round(float(np.mean(a)), 3), "max": round(float(np.max(a)), 3)}  # noqa: E731
    care = sum(m[k]["pen"] for k in keys)
    out = {"runs_with_degraded_segments": round(float((w["hour"] >= 0).mean()), 4),
           "care_time_loss_min": q(care), "lost_penalty_min": LOST_PENALTY_MIN, "_care_runs": care}
    for k in keys:
        x = m[k]
        out[k] = {"threshold_min": ctx["dest"][k]["thr"], "delta_pop_mean_min": q(x["delta"]),
                  "affected_pop_over_1min": q(x["affected_pop"]), "largest_cell_increase_min": q(x["cell_max"]),
                  "pop_newly_over_threshold": q(x["over_thr"]), "runs_with_none_available": round(float(x["lost"].mean()), 4)}
    return out


def lineb_inputs(assets, net, hours, tz):
    """【中文】B 线输入：养老院住户、各分区依赖电力设备的人数、每小时所属的日序号 / line B inputs."""
    return {"nh_res": lineb.nursing_residents(assets, net),
            "zone_dep": lineb.zone_dependents(assets, net, ROOT / "raw/health/empower_zip_davidson.json",
                                              ROOT / "raw/health/zcta_health.gpkg"),
            "day": pd.factorize(hours.tz_convert(tz).date)[0]}


def waiting(sim, th, off=frozenset()):
    """【中文】B 线：取每次运行新增就诊最多的一天，按排队近似 W = W0·ρ/(1−ρ) 换算为急诊等待的增加（分钟）。
    ρ = ρ0·(1 + 新增 / D0) / 当天医院平均可用比例（按停电小时折算），上限 0.95；A 线的医院关闭因此也会抬高等待。
    Line B: peak-day extra visits → added ED waiting through W = W0·ρ/(1−ρ), ρ capped at 0.95; hospital-hours
    closed that day reduce capacity, so line A closures also raise waiting."""
    N = len(th["C-H14"])
    if "R22" in off or "peak_day_extra_visits" not in sim["totals"]:
        return np.zeros(N)
    rho0, D0, W0 = th["C-H14"], th["C-H15"], th["C-H16"]
    open_share = sim["totals"]["peak_day_open_share"]
    rho = np.minimum(0.95, rho0 * (1 + sim["totals"]["peak_day_extra_visits"] / D0) / np.maximum(open_share, 1e-3))
    return W0 * (rho / (1 - rho) - rho0 / (1 - rho0))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the core (skeleton) heat-cascade model")
    ap.add_argument("--runs", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--start", default="2023-06-01")
    ap.add_argument("--end", default="2023-08-31")
    ap.add_argument("--scenarios", default="0,2,4", help="uniform air-temperature offsets in °C; 0 must be included")
    ap.add_argument("--air-field", choices=["on", "off"], default="on")
    ap.add_argument("--outage-source", default="eaglei_davidson")
    args = ap.parse_args(argv)
    scen = [float(x) for x in args.scenarios.split(",")]
    if 0.0 not in scen:
        sys.exit("--scenarios must include 0")

    cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text(encoding="utf-8"))
    proj = cfg["project"]
    tz = proj.get("timezone", "UTC")
    std = ROOT / proj.get("standard_dir", "data/standard")
    site_root = ROOT / proj.get("site_data_dir", "site/data") / "twin"
    site = site_root / "core"
    site.mkdir(parents=True, exist_ok=True)
    dep_cfg = next(d for d in cfg["datasets"] if d["kind"] == "dependency_rules")
    core_spec = yaml.safe_load((ROOT / "twin" / "core.yaml").read_text(encoding="utf-8"))

    assets, deps, couplings = load(std, "assets"), load(std, "dependencies"), load(std, "couplings")
    drivers, events = load(std, "drivers"), load(std, "events")
    build = json.loads((ROOT / proj.get("site_data_dir", "site/data") / "build.json").read_text(encoding="utf-8"))
    missing = [k for k in CORE_PARAMS if k not in set(couplings["coupling_id"])]
    if missing:
        sys.exit(f"couplings table lacks {missing}; run `python -m pipeline.build` after editing twin/couplings.csv")

    hours = pd.date_range(pd.Timestamp(args.start, tz=tz), pd.Timestamp(args.end, tz=tz) + pd.Timedelta(hours=23),
                          freq="h").tz_convert("UTC")
    wide = drivers.pivot_table(index="timestamp", columns="variable", values="value").reindex(hours)
    Ta = wide["air_temp_c"].interpolate(limit_direction="both").to_numpy()
    storm = pd.Series(wide["thunder"].fillna(0).to_numpy()).rolling(7, center=True, min_periods=1).max().to_numpy() > 0
    local_h = hours.tz_convert(tz).hour
    day_mask = np.asarray((local_h >= 8) & (local_h < 20))

    params = Params(couplings)
    net = Network(assets, deps, dep_cfg)
    Ta_sub, Ta_zone, air_info = air_field_temperatures(cfg, assets, net, Ta, hours, tz, args.air_field)
    river = river_inputs(cfg, hours)
    print(f"[core] {len(net.sid)} substations, {len(net.zone_id)} zones, {int(net.U.sum())} supply edges, {len(hours)} hours")

    actx = access.prepare(cfg, std, assets, deps, drivers, params, verbose=False)
    print(f"[core] access network: {actx['net']['stats']['edges']} edges, {len(actx['cells'])} population cells")
    LB = lineb_inputs(assets, net, hours, tz)
    print(f"[core] line B: {LB['nh_res'].sum():,.0f} nursing-home residents, {LB['zone_dep'].sum():,.0f} electricity-dependent residents")
    sims, th0 = {}, None
    for dT in scen:
        rng = np.random.default_rng(args.seed)          # 【中文】公共随机数 / common random numbers
        th = params.sample(args.runs, rng)
        th0 = th if dT == 0 else th0
        print(f"[core] {dT:+.0f} °C: {args.runs} runs …")
        shed = adequacy_shed(river, Ta, th, dT)
        sims[dT] = simulate_core(net, Ta + dT, th, rng, day_mask,
                                 Ta_sub=None if Ta_sub is None else Ta_sub + dT,
                                 Ta_zone=None if Ta_zone is None else Ta_zone + dT, shed=shed, lineb=LB)
        sims[dT]["runs_with_shed"] = None if shed is None else round(float((shed.max(1) > 0).mean()), 4)
        sims[dT]["access"] = access_runs(actx, net, sims[dT], th, hours, tz)
        # 【中文】就医时间（综合）= A 线路程增量 + B 线等待增量 / time to care = line A travel + line B waiting
        sims[dT]["wait"] = waiting(sims[dT], th)
        sims[dT]["time_to_care"] = sims[dT]["access"].pop("_care_runs") + sims[dT]["wait"]
    mc = sims[0.0]
    tot = mc["totals"]

    # ------------------------------------------------------------------ validation (same tests as the full model)
    eagle = events[events["source_id"] == args.outage_source].set_index("start_time")["severity"]
    obs = eagle.reindex(hours).fillna(0).to_numpy()
    day = np.asarray(hours.tz_convert(tz).date)
    model = mc["pop_out"].mean(0)
    val = {"power_all_hours": spearman_ci(model, obs, day),
           "power_non_storm_hours": spearman_ci(model[~storm], obs[~storm], day[~storm])}

    # ------------------------------------------------------------------ sensitivity
    sens = []
    for k in CORE_PARAMS:
        v = th0[k]
        if np.ptp(v) == 0:
            continue
        row = {"param": k, "name": params.table.at[k, "param_name"], "basis": params.table.at[k, "basis"]}
        for name in ("pop_hours", "indoor_outage_pop_hours", "thermal"):
            y = tot[name]
            row[name] = round(float(spearmanr(v, y).statistic), 3) if np.std(y) > 0 else None
        sens.append(row)
    sens.sort(key=lambda r: -abs(r["pop_hours"] or 0))

    # ------------------------------------------------------------------ comparison with the latest full-model run
    full = None
    fp = site_root / "results" / "summary.json"
    if fp.exists():
        fs = json.loads(fp.read_text(encoding="utf-8"))
        full = {"run_id": fs["run_id"], "scenarios": {
            s: {k: v[k]["mean"] for k in COMPARE if k in v} | {"overload": v["overload"]["mean"]}
            for s, v in fs["scenarios"].items()}}

    q = lambda a: {p: round(float(np.percentile(a, p)), 2) for p in (5, 50, 95)} | {"mean": round(float(np.mean(a)), 2)}  # noqa: E731
    stamp = dt.datetime.now(dt.timezone.utc)
    phash = hashlib.sha256(couplings.to_csv(index=False).encode()).hexdigest()[:10]
    run_id = f"core-{stamp:%Y%m%dT%H%M%SZ}-{phash}"
    run = {"run_id": run_id, "model": "core skeleton (docs/CORE_MODEL.md)", "created": stamp.isoformat(timespec="seconds"),
           "code_version": code_version(), "inputs_build_run_id": build.get("run_id"), "couplings_sha256": phash,
           "seed": args.seed, "runs": args.runs, "period": [args.start, args.end], "timezone": tz,
           "scenarios_delta_c": scen, "air_field": air_info, "outage_source": args.outage_source, "hours": len(hours),
           "links": [k["id"] for k in core_spec["links"]], "deferred": [d["id"] for d in core_spec["deferred"]],
           "network": {"substations": len(net.sid), "zones": len(net.zone_id), "supply_edges": int(net.U.sum()),
                       "hospitals": len(net.hosp), "nursing_homes": len(net.nurs), "dialysis": len(net.dial),
                       "water_plants": len(net.plants), "signals": len(net.signals)}}
    scen_summary = {}
    for dT, r in sims.items():
        t = r["totals"]
        scen_summary[f"{dT:+.0f}"] = {k: q(v) for k, v in t.items()} | {
            "share_runs_with_any_failure": round(float((t["thermal"] > 0).mean()), 3),
            "share_runs_with_any_outage": round(float((t["pop_hours"] > 0).mean()), 3),
            "runs_with_shed": r["runs_with_shed"],
            "indoor_ac_max_c": None if np.all(np.isnan(r["hourly"]["indoor_ac_max_c"])) else
            round(float(np.nanmax(r["hourly"]["indoor_ac_max_c"])), 1),
            "max_air_temp_c": round(float(np.max(Ta) + dT), 1), "access": r["access"],
            "wait_increase_min": q(r["wait"]), "time_to_care_min": q(r["time_to_care"])}
    summary = run | {"population_in_zones": int(net.zone_pop.sum()), "elderly_in_zones": int(net.zone_eld.sum()),
                     "poverty_in_zones": int(net.zone_pov.sum()), "scenarios": scen_summary,
                     "validation": val, "sensitivity": sens, "full_model": full}
    res_dir = std / "results" / run_id
    res_dir.mkdir(parents=True, exist_ok=True)
    write_json(res_dir / "run.json", run | {"parameter_draws": {k: th0[k].tolist() for k in CORE_PARAMS}})
    write_json(res_dir / "summary.json", summary)
    write_json(site / "summary.json", summary)
    write_json(site / "timeseries.json", {
        "run_id": run_id, "start": hours[0].strftime("%Y-%m-%dT%H:%MZ"), "n": len(hours), "timezone": tz,
        "air_temp_c": np.round(Ta, 2).tolist(), "observed_customers_out": obs.astype(int).tolist(),
        "scenarios": {f"{dT:+.0f}": {"pop_out_mean": np.round(r["pop_out"].mean(0), 1).tolist(),
                                    "indoor_outage_pop_mean": np.round(r["hourly"]["indoor_out_pop"][:, 0], 1).tolist(),
                                    "subs_down_mean": np.round(r["hourly"]["n_down"][:, 0], 3).tolist()}
                      for dT, r in sims.items()}})
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

    for s, v in scen_summary.items():
        print(f"[core] {s} °C: any outage {v['share_runs_with_any_outage']:.1%}, person-hours without power "
              f"{v['pop_hours']['mean']:,.0f}, indoor heat person-hours from outages {v['indoor_outage_pop_hours']['mean']:,.0f} "
              f"(65+ {v['indoor_outage_elderly_hours']['mean']:,.0f}), shed runs {v['runs_with_shed']}")
        a_ = v["access"]
        print(f"        access at each run's worst hour: hospital Δ mean {a_['hospital']['delta_pop_mean_min']['mean']} min "
              f"(p99 {a_['hospital']['delta_pop_mean_min'][99]}), EMS Δ mean {a_['ems']['delta_pop_mean_min']['mean']} min, "
              f"largest cell increase p95 {a_['hospital']['largest_cell_increase_min'][95]} min, "
              f"runs with no dialysis centre available {a_['dialysis']['runs_with_none_available']:.1%}")
        print(f"        line B: excess heat-illness visits {v['heat_visits_excess']['mean']:.1f}, device-user visits "
              f"{v['dep_visits']['mean']:.2f}, nursing-home resident-hours {v['nh_exposed_hours']['mean']:.0f}, "
              f"peak-day extra visits {v['peak_day_extra_visits']['mean']:.2f}, ED wait +{v['wait_increase_min']['mean']:.2f} min; "
              f"time to care +{v['time_to_care_min']['mean']:.2f} min")
    print(f"[core] {run_id}: ρ(model, EAGLE-I) {val['power_all_hours']['rho']}, top sensitivity "
          f"{[(r['param'], r['pop_hours']) for r in sens[:3]]}")


if __name__ == "__main__":
    main()
