"""
【中文】生成关系图集页面：把骨架模型结果、敲除贡献、B 线假设情景和实际热浪结果注入模板，
写出 site/architecture/relation-atlas.html。卡片上的结果数字在页面加载时从注入的数据计算，模型重跑后再执行本脚本即可。
    .venv/bin/python scripts/build_atlas.py

Builds the relation atlas from docs/atlas/relation-atlas.template.html and the latest results.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "site/data/twin/core"
TEMPLATE = ROOT / "docs/atlas/relation-atlas.template.html"
OUT = ROOT / "site/architecture/relation-atlas.html"
PLACEHOLDER = '  const CONTRIB = null, CONTRIB_NOTE = "", SUMMARY = null, VARIANTS = null, HEATWAVES = null;   // filled by scripts/build_atlas.py'
HW_LABELS = {"hw2024aug": "2024 Aug 26–30", "hw2022jun": "2022 Jun 21–25", "hw2025aug": "2025 Aug 15–19", "hw2023aug": "2023 Aug 22–26"}
KEEP = ["share_runs_with_any_outage", "thermal", "pop_hours", "hospital_hours", "nursing_hours", "dialysis_hours",
        "water_out_hours", "indoor_outage_pop_hours", "indoor_outage_elderly_hours", "indoor_no_ac_pop_hours",
        "indoor_ac_max_c", "runs_with_shed", "heat_visits_excess", "dep_visits", "nh_exposed_hours", "peak_day_extra_visits",
        "time_to_care_min", "ed_travel_increase_min", "ed_congestion_min", "wait_increase_min", "dialysis_sessions_affected"]


def read(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def summary_slice(s: dict) -> dict:
    sc = {}
    for k, v in s["scenarios"].items():
        a = v.get("access", {})
        sc[k] = {f: v[f] for f in KEEP if f in v} | {"access": {
            "runs_with_degraded_segments": a.get("runs_with_degraded_segments"),
            "dialysis": {"runs_with_none_available": a.get("dialysis", {}).get("runs_with_none_available")}}}
    full = s.get("full_model") or {}
    return {"run_id": s["run_id"], "scenarios": sc, "sensitivity": s.get("sensitivity", []),
            "full_model": {"run_id": full.get("run_id"), "scenarios": {k: {"pop_hours": v.get("pop_hours")}
                                                                       for k, v in (full.get("scenarios") or {}).items()}} if full else None}


def heatwaves() -> list:
    out = []
    for tag, label in HW_LABELS.items():
        s = read(CORE / tag / "summary.json")
        if not s:
            continue
        sc = {}
        for k, v in s["scenarios"].items():
            t = v.get("time_to_care_min", {})
            sc[k] = {"share_runs_with_any_outage": v["share_runs_with_any_outage"], "pop_hours": v["pop_hours"]["mean"],
                     "heat_visits_excess": v.get("heat_visits_excess", {}).get("mean"), "ttc_median": t.get("50"),
                     "ttc_p95": t.get("95"), "dialysis_sessions": v.get("dialysis_sessions_affected", {}).get("mean")}
        out.append({"tag": tag, "label": label, "period": s["period"], "run_id": s["run_id"], "scenarios": sc})
    return out


def note(c: dict, s: dict) -> str:
    b4 = c["outcomes"].get("4.0", {}).get("base", {})
    t4 = s["scenarios"]["+4"]["time_to_care_min"]
    return (f"Contribution = share of time to care lost when that one relation is switched off, same random numbers ({c['runs']} runs). "
            f"Time to care = added travel (rerouting and congestion) plus added waiting per ED visit on each run's peak day, "
            f"with per-hospital queues. At +4 °C the median is +{t4['50']:.1f} min and the p95 +{t4['95']:.0f} min; the mean "
            f"(+{b4.get('time_to_care_min', float('nan')):.1f} min in the knockout runs) is driven by emergency departments near capacity "
            f"and rests on T4 assumptions, so contributions describe the expected value. Positive = adds to time to care; negative "
            f"(teal) = buffers. Series links share the downstream effect; figures do not add up. Module badges: weakest data tier "
            f"of the module's own inputs; ↑ = weakest including upstream."
            f"<span class=\"zh\">贡献度 = 只关掉这一条关系、其他不变（相同随机数，{c['runs']} 次运行）时就医时间下降的比例。就医时间 = 每次急诊就诊在高峰日"
            f"增加的路程（改道与拥堵）加上增加的等待，按医院分别排队。+4 °C 时中位数 +{t4['50']:.1f} 分钟，p95 +{t4['95']:.0f} 分钟；"
            f"均值由接近满负荷的急诊决定，依赖 T4 假设，所以贡献度描述的是期望值。正值表示放大，负值（青色）表示缓冲。"
            f"串联的关系共享下游效果，数字不能相加。模块标签：本模块输入中最弱的数据档；↑ 表示连同上游的最弱档。</span>")


def main():
    t = TEMPLATE.read_text(encoding="utf-8")
    assert t.count(PLACEHOLDER) == 1, "placeholder line not found in the template"
    s, c, v = read(CORE / "summary.json"), read(CORE / "contrib.json"), read(CORE / "contrib_variants.json")
    contrib = {"relations": {k: {"edges": r["edges"], "contribution": r["contribution"]} for k, r in c["relations"].items()},
               "nodes": c["nodes"]} if c else None
    dump = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    line = (f"  const CONTRIB = {dump(contrib)}, CONTRIB_NOTE = {dump(note(c, s) if (c and s) else '')}, "
            f"SUMMARY = {dump(summary_slice(s) if s else None)}, VARIANTS = {dump(v)}, HEATWAVES = {dump(heatwaves())};")
    OUT.write_text(t.replace(PLACEHOLDER, line), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} (summary {s['run_id'] if s else None}, contrib {'yes' if c else 'no'}, "
          f"variants {'yes' if v else 'no'}, heat waves {len(heatwaves())})")


if __name__ == "__main__":
    main()
