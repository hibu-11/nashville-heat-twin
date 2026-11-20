"""
【中文】电力部分简化的对比试验（2026-11-19，CORE_MODEL §4.7）：原负荷与 IEEE 热点模型 vs 两参数气温脆弱性曲线。
"fragility" 各变体的 T50、σ_T、w 由每次运行的原参数换算（fragility_from_ieee），滞后时长取原顶油时间常数；
所有变体用相同的参数抽样与随机数。结果写到 data/standard/results/<out>（仓库里的副本：twin/evidence/power_compare_2000.json）。
    PYTHONPATH=$PWD .venv/bin/python scripts/power_compare.py 2000 power_compare_2000.json

Power simplification test (2026-11-19): former load + IEEE hot-spot chain vs the air-temperature fragility with
T50, sigma_T and w mapped from each run's former draws. Same draws and random numbers in every variant.
"""
import json
import sys
import time

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

from pipeline import access, care
from pipeline.build import ROOT
from pipeline.core import (Params, Network, load, air_field_temperatures, river_inputs, lineb_inputs, adequacy_shed,
                           access_runs, time_to_care)
from pipeline.twin.core import simulate_core, fragility_from_ieee

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
OUT = sys.argv[2] if len(sys.argv) > 2 else "power_compare.json"
cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text())
tz = cfg["project"]["timezone"]
std = ROOT / cfg["project"].get("standard_dir", "data/standard")
dep_cfg = next(d for d in cfg["datasets"] if d["kind"] == "dependency_rules")
assets, deps, couplings, drivers = load(std, "assets"), load(std, "dependencies"), load(std, "couplings"), load(std, "drivers")
hours = pd.date_range(pd.Timestamp("2023-06-01", tz=tz), pd.Timestamp("2023-08-31", tz=tz) + pd.Timedelta(hours=23),
                      freq="h").tz_convert("UTC")
wide = drivers.pivot_table(index="timestamp", columns="variable", values="value").reindex(hours)
Ta = wide["air_temp_c"].interpolate(limit_direction="both").to_numpy()
lh = hours.tz_convert(tz).hour
day_mask = np.asarray((lh >= 8) & (lh < 20))
params, net = Params(couplings), Network(assets, deps, dep_cfg)
Ta_sub, Ta_zone, _ = air_field_temperatures(cfg, assets, net, Ta, hours, tz, "on")
river = river_inputs(cfg, hours)
actx = access.prepare(cfg, std, assets, deps, drivers, params, verbose=False)
actx["dest"] = {"hospital": actx["dest"]["hospital"]}
LB, CP = lineb_inputs(assets, net, hours, tz), care.prepare(actx, net, assets)

VARIANTS = {"ieee": dict(power="ieee"), "fragility": dict(power="fragility"),
            "fragility_nolag": dict(power="fragility", tau=0.01), "fragility_noshed": dict(power="fragility", shed=False)}
PLAN = {0: ["ieee", "fragility"], 2: ["ieee", "fragility"], 4: list(VARIANTS)}


def stats(r):
    t, y = r["totals"], r["ed"]["time"]
    top1 = y >= np.percentile(y, 99)
    d = r["ed"]["decomp"]
    tot1 = sum(d[c][top1].mean() for c in ("heat", "device", "power", "water")) + d["congestion"][top1].mean()
    return {"any_outage": round(float((t["pop_hours"] > 0).mean()), 3), "thermal_mean": round(float(t["thermal"].mean()), 2),
            "pop_hours_mean": round(float(t["pop_hours"].mean())), "hospital_hours_mean": round(float(t["hospital_hours"].mean()), 2),
            "dep_visits_mean": round(float(t["dep_visits"].mean()), 1),
            "ttc_median": round(float(np.median(y)), 2), "ttc_p95": round(float(np.percentile(y, 95)), 1),
            "ttc_mean": round(float(y.mean()), 2), "ttc_top1_mean": round(float(y[top1].mean()), 1),
            "top1_device_share": round(float(d["device"][top1].mean() / tot1), 3)}


res, keep = {"runs": RUNS, "scenarios": {}}, {}
for dT, names in PLAN.items():
    res["scenarios"][f"+{dT}"] = {}
    for name in names:
        t0 = time.time()
        v = VARIANTS[name]
        rng = np.random.default_rng(20261027)
        th = params.sample(RUNS, rng)
        if v["power"] == "fragility":
            # 【中文】由原参数换算 / mapped from the former draws
            T50, sT, wl = fragility_from_ieee(th)
            th["C-P11"], th["C-P11.sigma"], th["C-P11.w"] = T50[:, 0], sT[:, 0], wl[:, 0]
            th["C-P11.tau"] = np.full_like(th["C-P2.tau"], v["tau"]) if "tau" in v else th["C-P2.tau"].copy()
        shed = adequacy_shed(river, Ta, th, dT) if v.get("shed", True) else None   # 【中文】原 K4 / former K4
        sim = simulate_core(net, Ta + dT, th, rng, day_mask, Ta_sub=Ta_sub + dT, Ta_zone=Ta_zone + dT, shed=shed,
                            lineb=LB, power=v["power"], supply_dependency=True)  # 【中文】对比时的结构 / structure at the time
        sim["access"] = access_runs(actx, net, sim, th, hours, tz)
        sim["ed"] = time_to_care(CP, sim, th, sim["access"], decompose=True)
        res["scenarios"][f"+{dT}"][name] = stats(sim)
        keep[(dT, name)] = (sim["totals"]["pop_hours"], sim["ed"]["time"])
        print(f"+{dT} {name:18s} {res['scenarios'][f'+{dT}'][name]} ({time.time() - t0:.0f} s)", flush=True)
    a = keep[(dT, "ieee")]
    for name in names[1:]:
        b = keep[(dT, name)]
        res["scenarios"][f"+{dT}"][name]["run_level_spearman_vs_ieee"] = {
            "pop_hours": round(float(spearmanr(a[0], b[0]).statistic), 3), "time_to_care": round(float(spearmanr(a[1], b[1]).statistic), 3)}
T50, sT, wl = fragility_from_ieee(params.sample(RUNS, np.random.default_rng(20261027)))
res["implied_fragility"] = {"T50_c": {p: round(float(np.percentile(T50, p)), 1) for p in (5, 50, 95)},
                            "sigma_T_c": {p: round(float(np.percentile(sT, p)), 2) for p in (5, 50, 95)},
                            "w_lag": {p: round(float(np.percentile(wl, p)), 2) for p in (5, 50, 95)}}
print(res["implied_fragility"])
(ROOT / "data/standard/results" / OUT).write_text(json.dumps(res, indent=1))
