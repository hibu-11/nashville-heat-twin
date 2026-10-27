"""
【中文】由最近一次级联运行的 summary.json 生成 docs/RESULTS.md（数字全部来自运行结果，不手填）。
    python -m pipeline.report [--summary site/data/twin/results/summary.json]
Writes docs/RESULTS.md from the latest cascade summary; no number is typed by hand.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def n(v, d=0):
    if v is None:
        return "—"
    return f"{v:,.{d}f}"


def ci(r, unit="h"):
    if not r or r.get("rho") is None:
        return "—"
    size = f"n = {r['n']:,} days" if unit == "d" else f"n = {r['n']:,} h, {r.get('n_days', '—')} days"
    return f"{r['rho']:.2f} [{r['lo']:.2f}, {r['hi']:.2f}] ({size})"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default=str(ROOT / "site/data/twin/results/summary.json"))
    ap.add_argument("--out", default=str(ROOT / "docs/RESULTS.md"))
    a = ap.parse_args(argv)
    s = json.loads(Path(a.summary).read_text(encoding="utf-8"))
    net, v = s["network"], s["validation"]
    L = []
    w = L.append
    w("# Results — heat-cascade model v0\n")
    w(f"Generated from cascade run `{s['run_id']}` (build `{s['inputs_build_run_id']}`, code `{s['code_version']}`, "
      f"seed {s['seed']}, {s['runs']:,} Monte Carlo runs per scenario plus {s['mid_runs']:,} runs at mid parameters). "
      f"Period {s['period'][0]} – {s['period'][1]}, {s['hours']:,} hours. Methods: [HANDBOOK.md](HANDBOOK.md).\n")
    w("> These are preliminary results from a model with placeholder links and parameters (HANDBOOK §3.4). "
      "They show how the coupled system responds under stated assumptions; they are not estimates of actual outages.\n")

    w("## 1. Network\n")
    w("| Element | Count |\n| --- | --- |")
    for k, label in (("substations", "Substations (OSM, AOI + 4 km)"), ("zones", "Service zones (placeholder)"),
                     ("supply_edges", "Supply edges"), ("peer_links", "Load-transfer peer pairs"),
                     ("hospitals", "Hospitals"), ("nursing_homes", "Nursing homes"), ("dialysis", "Dialysis facilities"),
                     ("water_plants", "Water works"), ("signals", "Traffic signals"), ("roads_with_signals", "Road segments with a signal")):
        w(f"| {label} | {net[k]:,} |")
    w(f"| Population in service zones | {s['population_in_zones']:,} (age 65+: {s['elderly_in_zones']:,}) |\n")

    w("## 2. Scenarios (season totals, Jun–Aug)\n")
    w("Mean over runs, with the 95th percentile in brackets. Scenarios add a uniform offset to the observed 2023 air temperature.\n")
    w("| Scenario | Peak air temp. | Runs with any failure | Thermal failures | Overload trips | Trips per thermal failure | "
      "Person-hours without power | Compound heat–outage person-hours | Dialysis facility-hours down |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for k, t in s["scenarios"].items():
        lab = "2023 observed" if k == "+0" else f"{k} °C"
        w(f"| {lab} | {t['max_air_temp_c']} °C | {t['share_runs_with_any_failure']:.1%} | {n(t['thermal']['mean'], 1)} [{n(t['thermal']['95'])}] | "
          f"{n(t['overload']['mean'], 1)} [{n(t['overload']['95'])}] | {n(t['amplification']['mean'], 2)} | "
          f"{n(t['pop_hours']['mean'])} [{n(t['pop_hours']['95'])}] | {n(t['compound_pop_hours']['mean'])} [{n(t['compound_pop_hours']['95'])}] | "
          f"{n(t['dialysis_hours']['mean'], 1)} |")
    m = s["mid"]
    w(f"\nWith every parameter at its mid value (observed 2023), the mean is {n(m['thermal']['mean'], 2)} thermal failures and "
      f"{n(m['pop_hours']['mean'])} person-hours without power. Most of the risk in the full Monte Carlo therefore comes from "
      "the tails of the parameter ranges, not from the Bernoulli draws.\n")

    w("## 3. Sensitivity (observed 2023 scenario)\n")
    w("Spearman ρ between each sampled parameter and the season totals of a run. Sorted by |ρ| with person-hours without power.\n")
    w("| Parameter | Name | Basis | ρ person-hours | ρ compound person-hours | ρ thermal failures | ρ overload trips |")
    w("| --- | --- | --- | --- | --- | --- | --- |")
    for r in s["sensitivity"]:
        w(f"| `{r['param']}` | {r['name']} | {r['basis']} | {n(r['pop_hours'], 2)} | {n(r['compound_pop_hours'], 2)} | "
          f"{n(r['thermal_failures'], 2)} | {n(r['overload_failures'], 2)} |")

    w("\n## 4. Validation\n")
    w("| Check | Result |\n| --- | --- |")
    w(f"| V1 Model vs EAGLE-I, all hours (Spearman ρ, 95% day-block CI) | {ci(v['power_all_hours'])} |")
    w(f"| V2 Model vs EAGLE-I, non-storm hours | {ci(v['power_non_storm_hours'])} |")
    w(f"| V3 Air temperature vs EAGLE-I, non-storm hours (data only) | {ci(v['temperature_vs_observed_non_storm'])} |")
    w(f"| V3 Daily max air temperature vs daily max outages (data only) | {ci(v['daily_tmax_vs_observed'], 'd')} |")
    w(f"| Model daily max vs observed daily max | {ci(v['daily_max_model_vs_observed'], 'd')} |")
    p = v["pavement_requests_lst_period"]
    w(f"| V4 Pavement requests ({p['period']}, {p['n_pos']} of {p['n_pos'] + p['n_neg']:,} segments): AUC of P(T7 > x50) (Eq. 15) | {p['auc']:.3f} |")
    w(f"| V4 Same, T7 itself / single-day peak LST | {v['pavement_requests_lst_period_t7']['auc']:.3f} / {v['pavement_requests_lst_period_lst_peak']['auc']:.3f} |")
    w(f"| V5 Same, segment length only (baseline) | {v['pavement_requests_lst_period_length_only']['auc']:.3f} |")
    w(f"| V5 Same, T7 within segment-length quintiles | {v['pavement_requests_lst_period_within_length_quintiles']['auc']:.3f} |")
    r2 = v["road_requests_lst_period"]
    w(f"| V4 All road requests (pavement + other road), LST period, {r2['n_pos']} segments | {r2['auc']:.3f} "
      f"(length only {v['road_requests_lst_period_length_only']['auc']:.3f}; within length quintiles "
      f"{v['road_requests_lst_period_within_length_quintiles']['auc']:.3f}) |")
    r3 = v["pavement_requests_summer"]
    w(f"| V4 Pavement requests, Jun–Aug ({r3['n_pos']} segments) | {r3['auc']:.3f} (length only "
      f"{v['pavement_requests_summer_length_only']['auc']:.3f}; within length quintiles "
      f"{v['pavement_requests_summer_within_length_quintiles']['auc']:.3f}) |\n")

    w("Observed customers out (Davidson County, EAGLE-I) on non-storm hours, by air temperature:\n")
    w("| Air temperature | Hours | Median | 90th percentile | Share of hours > 1,000 customers |\n| --- | --- | --- | --- | --- |")
    for b in v["observed_by_temperature_non_storm"]:
        w(f"| {b['bin_c']} °C | {b['hours']} | {n(b['median'])} | {n(b['p90'])} | {b['share_hours_over_1000']:.1%} |")

    w("\n## 5. Substations with the highest expected outage hours (observed 2023)\n")
    w("| Substation | Type | Max kV | Expected hours down | Peak mean hot-spot (°C) |\n| --- | --- | --- | --- | --- |")
    for r in s["substations_top"][:10]:
        w(f"| {r.get('name') or r['asset_id']} | {r.get('type') or '—'} | {n(r.get('kv_max'), 1)} | {n(r['expected_down_hours'], 2)} | "
          f"{n(r['theta_h_peak_c'], 1)} |")

    pv = s["pavement"]
    w(f"\n## 6. Pavement module\n\n{pv['roads']:,} segments with hourly LST. Maximum 7-day running mean of daily-max LST (T7): "
      f"5th / 50th / 95th percentile {pv['t7_quantiles']['5']} / {pv['t7_quantiles']['50']} / {pv['t7_quantiles']['95']} °C. "
      f"Mean P(T7 > x50) = {pv['p_exceed_mean']:.3f}; {pv['roads_p_exceed_over_0_5']:,} segments with P > 0.5.\n")
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
