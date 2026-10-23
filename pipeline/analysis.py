"""
【中文】G1 全链条检查（设计方案第 8 节阶段 1）：LST → 资产 → 事件 端到端可查询。
把逐小时 exposures（热浪期 / 对照期的均值）与匹配到同一资产的 events 连起来，
按资产热浪期 LST 五分位汇总事件率。只输出聚合数字，可以公开。
这是流程检查，不是统计检验：事件数很少，不能据此下结论。

Gate G1 check (design section 8, stage 1): LST → assets → events, end to end.
Joins hourly exposures (heat window / baseline means) with events matched to the
same assets and summarises event rates by quintile of heat-window LST.
Aggregates only. A pipeline check, not a statistical test.
"""
from __future__ import annotations

import pandas as pd


def chain_check(tables: dict, project: dict) -> dict | None:
    cfg = project.get("chain_check")
    heat, base = project.get("heatwave"), project.get("baseline")
    if not (cfg and heat and base):
        return None
    tz = project.get("timezone", "UTC")
    assets = tables["assets"]
    assets = assets[assets["source_id"] == cfg["assets"]]
    exp = tables["exposures"]
    exp = exp[(exp["source_id"] == cfg["exposures"]) & exp["asset_id"].isin(assets["asset_id"])]
    ev = tables["events"]
    ev = ev[(ev["source_id"] == cfg["events"]) & ev["asset_id"].isin(assets["asset_id"])]
    if assets.empty or exp.empty:
        return {"ok": False, "reason": "no hourly exposures for the chain-check assets yet"}

    def period(ts):
        d = ts.dt.tz_convert(tz).dt.date
        out = pd.Series(pd.NA, index=ts.index, dtype="string")
        for name, w in (("heatwave", heat), ("baseline", base)):
            out[(d >= pd.Timestamp(w["start"]).date()) & (d <= pd.Timestamp(w["end"]).date())] = name
        return out

    exp = exp.assign(period=period(exp["timestamp"])).dropna(subset=["period"])
    lst = exp.pivot_table(index="asset_id", columns="period", values="lst_mean", aggfunc="mean")
    days = {n: (pd.Timestamp(w["end"]) - pd.Timestamp(w["start"])).days + 1 for n, w in (("heatwave", heat), ("baseline", base))}
    # 【中文】只统计有 LST 帧的日期，避免缺帧日期拉低事件率 / days actually covered by LST frames
    covered = exp.groupby("period")["timestamp"].apply(lambda t: t.dt.tz_convert(tz).dt.date.nunique()).to_dict()

    ev = ev.assign(period=period(ev["start_time"])).dropna(subset=["period"])
    n_ev = ev.groupby(["asset_id", "period"]).size().unstack(fill_value=0)

    lst = lst.reindex(columns=["heatwave", "baseline"]).rename(columns={"heatwave": "lst_heat", "baseline": "lst_base"})
    df = assets.set_index("asset_id")[["geometry"]].join(lst, how="inner")
    for p in ("heatwave", "baseline"):
        df[f"ev_{p}"] = n_ev[p].reindex(df.index).fillna(0).astype(int) if p in n_ev else 0
    df["km"] = df.geometry.length / 1000
    df = df.dropna(subset=["lst_heat"])
    df["bin"] = pd.qcut(df["lst_heat"], 5, labels=[f"Q{i}" for i in range(1, 6)])

    rows = []
    for b, g in df.groupby("bin", observed=True):
        km = g["km"].sum()
        rows.append({
            "bin": str(b), "assets": int(len(g)), "km": round(km, 1),
            "lst_heat_min": round(g["lst_heat"].min(), 1), "lst_heat_max": round(g["lst_heat"].max(), 1),
            "lst_heat_mean": round(g["lst_heat"].mean(), 2), "lst_base_mean": round(g["lst_base"].mean(), 2),
            "events_heatwave": int(g["ev_heatwave"].sum()), "events_baseline": int(g["ev_baseline"].sum()),
            "per_100km_day_heatwave": round(100 * g["ev_heatwave"].sum() / km / days["heatwave"], 3) if km else None,
            "per_100km_day_baseline": round(100 * g["ev_baseline"].sum() / km / days["baseline"], 3) if km else None,
        })
    return {
        "ok": True,
        "assets_source": cfg["assets"], "exposures_source": cfg["exposures"], "events_source": cfg["events"],
        "heatwave": heat, "baseline": base, "days": days, "days_with_lst": covered,
        "assets_total": int(len(assets)), "assets_with_exposure": int(len(df)),
        "events_matched": int(len(ev)), "bins": rows,
        "note": "Pipeline check for gate G1 (LST → assets → events). Counts are small; "
                "this is not a statistical test of heat effects.",
    }
