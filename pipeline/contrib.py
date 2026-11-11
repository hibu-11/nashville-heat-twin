"""
【中文】骨架模型的因果贡献（敲除实验）与模块数据分级。
对关系图集中的每条关系，用相同的随机数（公共随机数）分别运行"全部开启"和"只关掉这一条"，比较三个结局：
就医时间增量（A 线，医院 + 透析 + 急救的人口加权分钟数，研究区内无可用设施按 30 分钟计）、停电人·小时、
室内高温暴露人·小时（B 线的输入）。贡献 = (基准 − 敲除) / 基准：正值表示这条关系放大结局，负值表示它起缓冲作用。
串联链上任何一环被关掉，下游效果都会消失，因此串联各环的贡献相同；贡献不能相加。
同时按变量表与参数表的可信度栏，给结构图的每个模块计算"本模块输入最弱档"和"连同上游最弱档"。

    python -m pipeline.contrib [--runs 1000] [--scenarios 2,4]

Knockout (do-intervention) contributions of each relation and data-confidence tiers of each module.
Writes site/data/twin/core/contrib.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time

import numpy as np
import pandas as pd
import yaml

from . import access
from .adapters.base import write_json
from .build import ROOT
from .cascade import air_field_temperatures, load, river_inputs
from . import care
from .core import access_runs, adequacy_shed, lineb_inputs, time_to_care
from .twin.cascade import Network
from .twin.core import KNOCKOUTS, simulate_core
from .twin.params import Params

# 【中文】在 pipeline.core 层面处理的敲除 / knockouts handled outside simulate_core
OUTER = {
    "R01": "local temperature = background (airport) series everywhere (no urban field)",
    "R05": "TVA load is not scaled by scenario warming",
    "R06": "no rotating outages from a system shortfall",
    "R14": "dark signals keep full capacity (R14–R16 are in series, so one knockout covers all three)",
    "R17": "closed facilities stay on the destination list",
    "R22": "extra care demand does not lengthen waiting",
}
# 【中文】关系 → 结构图上的边 / relation → map edges
EDGES = {
    "R01": [["bg", "urban"]], "R02": [["urban", "load"]], "R03a": [["urban", "hotspot"]], "R03b": [["load", "hotspot"]],
    "R04": [["hotspot", "failure"]], "R05": [["load", "margin"]], "R06": [["margin", "shed"], ["shed", "topo"]],
    "R07": [["failure", "topo"]], "R08": [["topo", "zone"]], "R09": [["zone", "plant"]],
    "R10": [["plant", "storage"], ["storage", "wservice"]], "R11": [["zone", "facility"]], "R12": [["wservice", "facility"]],
    "R13": [["zone", "signals"]], "R14": [["signals", "capacity"], ["capacity", "travel"], ["travel", "access"]],
    "R17": [["facility", "access"]], "R18": [["zone", "indoor"]], "R19": [["urban", "indoor"]],
    "R21": [["exposure", "illness"]], "R22": [["illness", "access"]], "R23": [["facility", "exposure"]],
    "R24": [["zone", "illness"]],
}
# 【中文】结构图模块 → 输入变量与参数（用于数据分级）/ map module → input variables and couplings
NODE_INPUTS = {
    "bg": ["CLM-01"], "urban": ["CLM-19", "CLM-20", "BLD-05", "BLD-06", "BLD-11"],
    "load": ["PWR-03", "PWR-04", "PWR-05", "PWR-06", "C-P1.Kd", "C-P1.Td"], "hotspot": ["PWR-11"], "failure": ["PWR-15"],
    "topo": ["PWR-01", "PWR-02", "PWR-24"], "zone": ["PWR-20"], "margin": ["PWR-07", "PWR-09", "PWR-32", "PWR-33"],
    "shed": ["C-P9.avail", "C-P9.imp"], "river": ["C-P9", "C-P9.span", "C-P9.Qmin", "C-P9.flow"], "overload": ["C-P4"],
    "signals": ["TRN-06", "TRN-07"], "capacity": ["TRN-12", "TRN-15"], "travel": ["TRN-01", "TRN-10", "TRN-11", "TRN-13", "TRN-14"],
    "plant": ["WAT-01", "WAT-09"], "storage": ["WAT-04"], "wservice": ["C-W1"],
    "facility": ["HLT-01", "HLT-03", "HLT-05", "HLT-07", "HLT-08", "C-H3"], "access": ["TRN-21", "POP-01", "C-H14", "C-H15", "C-H16"],
    "indoor": ["BLD-08", "BLD-09", "BLD-12", "HLT-24"], "pop": ["POP-01", "POP-02", "POP-03"],
    "exposure": ["HLT-23", "BLD-04"], "illness": ["HLT-12", "HLT-17", "C-H11", "C-H13"],
}
MAP_EDGES = [e for v in EDGES.values() for e in v] + [["indoor", "exposure"], ["pop", "exposure"], ["urban", "exposure"],
                                                      ["exposure", "illness"], ["illness", "access"], ["overload", "failure"],
                                                      ["bg", "river"], ["river", "margin"],
                                                      ["facility", "exposure"], ["zone", "illness"]]
TIERS = ["T1", "T2", "T3", "T4"]


def weakest(ts):
    ts = [t for t in ts if t in TIERS]
    return max(ts, key=TIERS.index) if ts else None


def node_tiers() -> dict:
    read = lambda p: pd.read_csv(ROOT / p, comment="#", dtype=str, keep_default_na=False)  # noqa: E731
    v, c = read("twin/variables.csv"), read("twin/couplings.csv")
    tier = dict(zip(v["var_id"], v["confidence"])) | dict(zip(c["coupling_id"], c["confidence"]))
    note = dict(zip(v["var_id"], v["name_en"])) | dict(zip(c["coupling_id"], c["param_name"]))
    own = {}
    for n, ids in NODE_INPUTS.items():
        missing = [i for i in ids if i not in tier]
        if missing:
            raise SystemExit(f"node {n}: unknown ids {missing}")
        w = weakest(tier[i] for i in ids)
        own[n] = {"tier": w, "weakest_inputs": [f"{i} {note[i]}" for i in ids if tier[i] == w]}
    up = {}
    for a, b in MAP_EDGES:
        up.setdefault(b, set()).add(a)

    def chain(n, seen=()):
        return weakest([own[n]["tier"]] + [chain(u, seen + (n,)) for u in up.get(n, ()) if u not in seen])
    return {n: own[n] | {"inherited": chain(n)} for n in own}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Knockout contributions of each relation in the core model")
    ap.add_argument("--runs", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--start", default="2023-06-01")
    ap.add_argument("--end", default="2023-08-31")
    ap.add_argument("--scenarios", default="2,4")
    ap.add_argument("--variants", action="store_true",
                    help="instead of knockouts, run assumption variants for line B (q, ED parameters) → contrib_variants.json")
    args = ap.parse_args(argv)
    scen = [float(x) for x in args.scenarios.split(",")]

    cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text(encoding="utf-8"))
    proj = cfg["project"]
    tz = proj.get("timezone", "UTC")
    std = ROOT / proj.get("standard_dir", "data/standard")
    dep_cfg = next(d for d in cfg["datasets"] if d["kind"] == "dependency_rules")
    assets, deps, couplings, drivers = load(std, "assets"), load(std, "dependencies"), load(std, "couplings"), load(std, "drivers")
    hours = pd.date_range(pd.Timestamp(args.start, tz=tz), pd.Timestamp(args.end, tz=tz) + pd.Timedelta(hours=23),
                          freq="h").tz_convert("UTC")
    wide = drivers.pivot_table(index="timestamp", columns="variable", values="value").reindex(hours)
    Ta = wide["air_temp_c"].interpolate(limit_direction="both").to_numpy()
    local_h = hours.tz_convert(tz).hour
    day_mask = np.asarray((local_h >= 8) & (local_h < 20))
    params = Params(couplings)
    net = Network(assets, deps, dep_cfg)
    Ta_sub, Ta_zone, _ = air_field_temperatures(cfg, assets, net, Ta, hours, tz, "on")
    river = river_inputs(cfg, hours)
    actx = access.prepare(cfg, std, assets, deps, drivers, params, verbose=False)
    LB = lineb_inputs(assets, net, hours, tz)
    CP = care.prepare(actx, net, assets)

    if args.variants:
        return run_variants(args, scen, Ta, Ta_sub, Ta_zone, day_mask, hours, tz, params, net, river, actx, LB, CP, proj)
    cases = ["base"] + list(OUTER) + list(KNOCKOUTS)
    res = {}
    for dT in scen:
        res[dT] = {}
        for case in cases:
            t0 = time.time()
            rng = np.random.default_rng(args.seed)          # 【中文】公共随机数 / common random numbers
            th = params.sample(args.runs, rng)
            shed = None if case == "R06" else adequacy_shed(river, Ta, th, 0.0 if case == "R05" else dT)
            local = case != "R01"
            sim = simulate_core(net, Ta + dT, th, rng, day_mask,
                                Ta_sub=Ta_sub + dT if (local and Ta_sub is not None) else None,
                                Ta_zone=Ta_zone + dT if (local and Ta_zone is not None) else None,
                                shed=shed, off=frozenset([case]) & set(KNOCKOUTS), lineb=LB)
            acc = access_runs(actx, net, sim, th, hours, tz, off=frozenset([case]) & {"R14", "R17"})
            care_ = acc.pop("_care_runs")
            ed = time_to_care(CP, sim, th, acc, off=frozenset([case]) & {"R14", "R17", "R22"})
            ttc, wait = ed["time"], ed["wait"]
            t = sim["totals"]
            res[dT][case] = {"time_to_care_min": round(float(ttc.mean()), 4), "wait_increase_min": round(float(wait.mean()), 4),
                             "time_to_care_median_min": round(float(np.median(ttc)), 4),
                             "ed_travel_increase_min": round(float(ed["travel"].mean()), 4),
                             "dialysis_sessions_affected": round(float(ed["dialysis_sessions"].mean()), 2),
                             "care_time_loss_min": acc["care_time_loss_min"]["mean"],
                             "dialysis_none_available": acc["dialysis"]["runs_with_none_available"],
                             "pop_hours": round(float(t["pop_hours"].mean()), 1),
                             "indoor_outage_pop_hours": round(float(t["indoor_outage_pop_hours"].mean()), 1),
                             "indoor_pop_hours": round(float(t["indoor_pop_hours"].mean()), 1)}
            print(f"[contrib] {dT:+.0f} °C {case:5s} ttc {res[dT][case]['time_to_care_min']:.3f} (wait {res[dT][case]['wait_increase_min']:.3f}) · care {res[dT][case]['care_time_loss_min']:.3f} min · "
                  f"pop-h {res[dT][case]['pop_hours']:.0f} · indoor {res[dT][case]['indoor_pop_hours']:.0f} ({time.time() - t0:.0f} s)")

    def share(dT, case, k):
        b, x = res[dT]["base"][k], res[dT][case][k]
        return None if not b else round((b - x) / b, 4)
    rel = {}
    for case in cases[1:]:
        rel[case] = {"what_is_switched_off": OUTER.get(case) or KNOCKOUTS[case], "edges": EDGES[case],
                     "contribution": {f"{dT:+.0f}": {k: share(dT, case, k) for k in ("time_to_care_min", "time_to_care_median_min", "ed_travel_increase_min", "wait_increase_min", "dialysis_sessions_affected", "care_time_loss_min", "pop_hours", "indoor_pop_hours", "indoor_outage_pop_hours")} for dT in scen}}
    out = {"created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "runs": args.runs, "seed": args.seed,
           "scenarios_delta_c": scen,
           "method": "Knockout (do-intervention) with common random numbers: contribution = (base − knockout) / base. "
                     "Positive: the relation adds to the outcome; negative: it buffers. Relations in series share the "
                     "downstream effect, so contributions do not add up. time_to_care_min = added travel (rerouting and congestion) "
                     "plus added waiting per ED visit on each run's peak day, with per-hospital queues (pipeline.care). "
                     "dialysis_sessions_affected is reported separately. care_time_loss_min (old line A metric) = population-mean added "
                     "minutes to hospital + dialysis + EMS at each run's worst hour, cells that lose every facility of a "
                     "type inside the area counted at 30 min (assumption).",
           "outcomes": res, "relations": rel, "nodes": node_tiers()}
    p = ROOT / proj.get("site_data_dir", "site/data") / "twin" / "core" / "contrib.json"
    write_json(p, out)
    print(f"[contrib] wrote {p}")


# 【中文】B 线假设的情景对照：固定某些 T4 参数，比较就医时间的中位数与 p95 / line B assumption variants
VARIANTS = {
    "base": {},
    "q = 0 (no device-user visits)": {"C-H13": 0.0},
    "q = 0.01": {"C-H13": 0.01},
    "q = 0.15": {"C-H13": 0.15},
    "ED slack (rho0 0.60, D0 1400, W0 20)": {"C-H14": 0.60, "C-H15": 1400, "C-H16": 20},
    "ED stretched (rho0 0.85, D0 700, W0 45)": {"C-H14": 0.85, "C-H15": 700, "C-H16": 45},
}


def run_variants(args, scen, Ta, Ta_sub, Ta_zone, day_mask, hours, tz, params, net, river, actx, LB, CP, proj):
    res = {}
    for dT in scen:
        res[f"{dT:+.0f}"] = {}
        for name, fix in VARIANTS.items():
            rng = np.random.default_rng(args.seed)
            th = params.sample(args.runs, rng)
            for k, v in fix.items():
                th[k] = np.full(args.runs, float(v))
            shed = adequacy_shed(river, Ta, th, dT)
            sim = simulate_core(net, Ta + dT, th, rng, day_mask, Ta_sub=None if Ta_sub is None else Ta_sub + dT,
                                Ta_zone=None if Ta_zone is None else Ta_zone + dT, shed=shed, lineb=LB)
            acc = access_runs(actx, net, sim, th, hours, tz)
            ed = time_to_care(CP, sim, th, acc)
            t = ed["time"]
            res[f"{dT:+.0f}"][name] = {"time_to_care_mean": round(float(t.mean()), 2), "time_to_care_median": round(float(np.median(t)), 2),
                                       "time_to_care_p95": round(float(np.percentile(t, 95)), 1),
                                       "wait_median": round(float(np.median(ed["wait"])), 2),
                                       "device_visits": round(float(sim["totals"]["dep_visits"].mean()), 1),
                                       "share_runs_over_30min": round(float((t > 30).mean()), 3)}
            print(f"[variants] {dT:+.0f} °C {name:42s} median {res[f'{dT:+.0f}'][name]['time_to_care_median']:.2f} "
                  f"p95 {res[f'{dT:+.0f}'][name]['time_to_care_p95']:.1f} mean {res[f'{dT:+.0f}'][name]['time_to_care_mean']:.1f} min")
    out = {"created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "runs": args.runs, "variants": VARIANTS, "results": res}
    p = ROOT / proj.get("site_data_dir", "site/data") / "twin" / "core" / "contrib_variants.json"
    write_json(p, out)
    print(f"[variants] wrote {p}")


if __name__ == "__main__":
    main()
