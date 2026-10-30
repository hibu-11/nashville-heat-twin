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


def read(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def air_section(w, s, std):
    """【中文】7. 城市气温场（M-6）/ urban air-temperature field."""
    af = s.get("air_field") or {}
    m = read(std / "air_field" / f"{af.get('dataset', '')}_model.json") if af.get("dataset") else None
    w("## 7. Urban air-temperature field (M-6)\n")
    if not m:
        w("Not used in this run: BNA air temperature everywhere (assumption A-D4).\n")
        return
    w("Regressions on the 2022 heat-mapping traverses (aggregated to 100 m cells, 1 km spatial-block cross-validation). "
      "Predictors: impervious share and forest share within 90 m and 510 m, water share within 990 m, distance to water, "
      "elevation and topographic position.\n")
    w("| Period | Anchor (local hour) | Cells | CV RMSE | Null RMSE | CV R² | Anomaly at BNA |\n| --- | --- | --- | --- | --- | --- | --- |")
    for p, h in zip(("morning", "afternoon", "evening"), m["anchors_local_hour"]):
        x = m["models"][p]
        w(f"| {p} | {h} | {x['n_cells']:,} | {x['cv_rmse_c']} °C | {x['null_rmse_c']} °C | {x['cv_r2']} | "
          f"{m['reference_anomaly_c'][p]:+.2f} °C |")
    d = m.get("candidate_traverse_dates") or []
    if d:
        w(f"\nThe traverse files carry no date. Closest BNA match: {d[0]['date']} (RMSE {d[0]['rmse_c']} °C over the three periods); "
          f"next {', '.join(x['date'] for x in d[1:])}. To be confirmed with the campaign organisers.\n")
    so, mc = s.get("station_only"), s["mc"]
    w(f"Substation temperature offsets relative to BNA: {af['station_offset_c']['min']} to {af['station_offset_c']['max']} °C "
      f"(mean {af['station_offset_c']['mean']}); zones {af['zone_offset_c']['min']} to {af['zone_offset_c']['max']} °C.\n")
    if so:
        w("| Observed 2023, same random draws | Urban field (M-6) | BNA everywhere (A-D4) |\n| --- | --- | --- |")
        for k, lab in (("thermal", "Thermal failures, mean"), ("overload", "Overload trips, mean"),
                       ("pop_hours", "Person-hours without power, mean"), ("compound_pop_hours", "Compound person-hours, mean")):
            w(f"| {lab} | {n(mc[k]['mean'], 1)} | {n(so[k]['mean'], 1)} |")
        w("")


def river_section(w, s, std):
    """【中文】8. 河水温度 → 火电降额（M-18）/ river temperature and thermal derating."""
    rid = next((d for d in ("cumberland_thermal",) if (std / "river" / f"{d}_model.json").exists()), None)
    m = read(std / "river" / f"{rid}_model.json") if rid else None
    w("## 8. River temperature → thermal derating → system supply (M-18)\n")
    if not m:
        w("Not built.\n")
        return
    sm = m["stream_model"]
    w(f"Stream temperature (Mohseni et al. 1998) fitted on {sm['n_samples']} TDEC main-stem samples against the 7-day mean BNA "
      f"air temperature: RMSE {sm['rmse_c']:.2f} °C, R² {sm['r2']:.2f}, upper asymptote {sm['alpha']:.1f} °C. "
      f"Excluded: {m.get('excluded_note')}.\n")
    w("| Plant | Cooling | Summer capacity |\n| --- | --- | --- |")
    for p in m["plants"]:
        w(f"| {p['plant_name']} ({p['County']} Co.) | {p['cooling_type']} (once-through) | {n(p['summer_capacity_mw'])} MW |")
    w(f"\nTVA operable summer capacity {n(m['system_capacity_mw'])} MW (EIA-860 2022).\n")
    w("| Summer | Max modelled river temp. | Min discharge | TVA peak demand |\n| --- | --- | --- | --- |")
    for y, r in m["summer_by_year"].items():
        w(f"| {y} | {r['tw_max_c']} °C | {n(r['q_min_cfs'])} cfs | {n(r['load_peak_mw'])} MW |")
    w("\n| Scenario | Runs with any system shed | Mean shed hours | Mean peak derate | Mean derate hours |\n| --- | --- | --- | --- | --- |")
    for k, t in s["scenarios"].items():
        r = t.get("river")
        if r:
            w(f"| {k} °C | {r['runs_with_shed']:.1%} | {r['shed_hours_mean']} | {n(r['derate_mw_max_mean'])} MW | {r['derate_hours_mean']} |")
    w("\nShed in the warming scenarios comes from TVA demand rising with the C-P1 load slope against a placeholder supply "
      "margin (C-P9.avail, C-P9.imp), not from river derating. Section 10 rejects parameter sets that shed load in an observed summer.\n")


def access_section(w, path):
    """【中文】9. 路网可达性（M-28 / M-29）/ network access."""
    x = read(path)
    w("## 9. Network access (M-28 / M-29)\n")
    if not x:
        w("Not run (`python -m pipeline.access`).\n")
        return
    st = x["network"]
    w(f"Road network from TIGER segments in the AOI: {st['edges']:,} edges, {st['nodes']:,} nodes, "
      f"{st['largest_component_node_share']:.1%} of nodes in the main component. HPMS 2024 AADT matched to "
      f"{st['hpms_aadt_matched_share']:.1%} of edges ({st['hpms_aadt_matched_length_share']:.1%} of length); the rest use class defaults. "
      f"Hourly profile from TMAS weekdays. {x['population_in_cells']:,} residents in {x['cells']:,} cells of {x['cell_m']:.0f} m; "
      f"{x['controlled_edge_share']:.1%} of edges are signal-controlled.\n")
    w("Population-weighted travel time to the nearest available facility (minutes; 90th percentile in brackets).\n")
    def mm(c):
        if c["pop_mean_min"] is None:
            return "none available"
        return f"{n(c['pop_mean_min'], 2)} [{n(c['pop_p90_min'], 2)}] ({c['facilities_available']} open)"

    w("| Condition | Local hour | Expected degraded segments | Hospital | Dialysis | Fire / EMS | Share > 8 min to EMS |")
    w("| --- | --- | --- | --- | --- | --- | --- |")
    for k, c in x["conditions"].items():
        w(f"| {k} | {c['hour_local']} | {n(c.get('roads_degraded_mean'), 1)} | {mm(c['hospital'])} | {mm(c['dialysis'])} | "
          f"{mm(c['ems'])} | {c['ems'].get('pop_share_over_8_min', 0):.1%} |")
    w("\nStress conditions use expected capacity, 1 − (1 − φ_dark)·P(signal dark), and drop facilities with P(down) ≥ 0.5. "
      "`all_signals_dark_pm` is an upper bound: every signal-controlled link at φ_dark in the evening peak.\n")


def calibration_section(w, path):
    """【中文】10. 多年校准（M-43）/ multi-year calibration."""
    x = read(path)
    w("## 10. Multi-year calibration against EAGLE-I (M-43)\n")
    if not x:
        w("Not run (`python -m pipeline.calibrate`).\n")
        return
    ab = x.get("abc", {})
    w(f"Run `{x['run_id']}`: summers {x['years'][0]}–{x['years'][-1]}, {x['runs']:,} prior runs (same parameter draws every year). "
      f"Years left out for EAGLE-I coverage (background < {x.get('min_background', 100):.0f} customers): "
      f"{', '.join(map(str, x.get('years_excluded', []))) or 'none'}. {x['runs_rejected_by_shed_constraint']:,} runs rejected because they "
      f"shed TVA load in an observed summer (A-C3).\n")
    if ab:
        w(f"**Summary statistic (ABC).** S = {ab['statistic']}. Observed S = **{n(ab['observed'])} ± {n(ab['observed_se'])}** customers "
          f"({ab['n_hot_days']} hot and {ab['n_cool_days']} cool days). The prior runs give S = {' / '.join(n(v) for v in ab['model_prior_5_50_95'])} "
          f"(5th / 50th / 95th percentile); {ab['share_runs_within_2se']:.1%} of runs lie within 2 SE of the observation. "
          f"Weights w ∝ exp(−(S_r − S_obs)² / 2 SE²) give an effective sample size of **{x['ess']}** and a posterior mean S of "
          f"{n(ab['model_posterior_mean'])}.\n")
        w(f"Diagnostic: the full daily negative-binomial likelihood collapses onto a few runs (ESS {x.get('ess_full_nb_likelihood')}, "
          f"largest weight {x.get('max_weight_full_nb')}), so it is not used for the posterior.\n")
    w("| Summer | Non-storm days | Hot non-storm days (Tmax ≥ 35 °C) | Background (customers) | NB shape k | Max observed | Model mean on hot days |")
    w("| --- | --- | --- | --- | --- | --- | --- |")
    for y, r in x["per_year"].items():
        w(f"| {y} | {r['non_storm_days']} | {r['hot_non_storm_days']} | {n(r['background_customers'])} | {r['nb_shape_k']} | "
          f"{n(r['obs_max_non_storm'])} | {n(r['model_mean_daily_max_customers_hot_days'])} |")
    w("\n| Parameter | Basis | Prior 5 / 50 / 95 | Posterior 5 / 50 / 95 | Shift (prior SD) |\n| --- | --- | --- | --- | --- |")
    for p in x["posterior"]:
        w(f"| `{p['param']}` {p['name']} | {p['basis']} | {' / '.join(f'{v:g}' for v in p['prior_5_50_95'])} | "
          f"{' / '.join(f'{v:g}' for v in p['posterior_5_50_95'])} | {p['shift_in_prior_sd']:+.2f} |")
    d = x["data_only"]
    h = d.get("hot_minus_cool_median") or {}
    w(f"\n**Data only (no model).** Daily max air temperature vs daily max customers out on non-storm days, all summers pooled: "
      f"{ci(d['daily_tmax_vs_daily_max_outages_non_storm'], 'd')}. Median daily max on hot days (≥ 35 °C, n = {d['n_hot_days']}) "
      f"{n(d['median_daily_max_hot_days'])} vs cool days (< 32 °C, n = {d['n_cool_days']}) {n(d['median_daily_max_cool_days'])} customers"
      + (f"; difference {n(h.get('est'))} [{n(h.get('lo'))}, {n(h.get('hi'))}]" if h else "") + ".\n")
    w("| Daily max temperature | Days | Median | 90th percentile | Share of days > 1,000 customers |\n| --- | --- | --- | --- | --- |")
    for b in d["binned_by_tmax"]:
        w(f"| {b['bin_c']} °C | {b['hours']} | {n(b['median'])} | {n(b['p90'])} | {b['share_hours_over_1000']:.1%} |")
    w("\nBy-year Spearman ρ: " + ", ".join(f"{y} {n(r, 2)}" for y, r in d["by_year_spearman"].items()) + ".\n")


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

    res = Path(a.summary).parent
    std = ROOT / "data/standard"
    air_section(w, s, std)
    river_section(w, s, std)
    access_section(w, res / "access.json")
    calibration_section(w, res / "calibration.json")
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
