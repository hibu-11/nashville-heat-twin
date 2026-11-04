"""
【中文】用 EAGLE-I Davidson 县 15 分钟停电序列估计「用户恢复供电时长」，作为 C-P6 的依据。
事件定义：超出 7 天滚动中位数背景 > 500 户；间隔 ≤ 1 h 合并；ASOS BNA 在事件前 3 h 至结束有雷暴记为风暴事件。
2018 年 EAGLE-I 覆盖不全，剔除。结果是县级汇总，包含倒闸转供，不是设备修复时间。
    .venv/bin/python scripts/eaglei_restoration.py

Estimates customer restoration times from the EAGLE-I Davidson County 15-min series (evidence for C-P6).
Writes twin/evidence/eaglei_restoration.json (aggregates only).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

Q = [0.1, 0.25, 0.5, 0.75, 0.9]


def events(series: pd.Series, storm_hours: pd.DatetimeIndex, min_excess: float) -> pd.DataFrame:
    bg = series.rolling("7D", min_periods=96).median().fillna(0)
    ex = (series - bg).clip(lower=0)
    on = ex > min_excess
    grp = (on != on.shift()).cumsum()
    runs = [(g.index[0], g.index[-1]) for _, g in ex[on].groupby(grp[on])]
    merged: list[tuple] = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= pd.Timedelta(hours=1):
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    rows = []
    for a, b in merged:
        seg = ex[a:b]
        pk, tp = seg.max(), seg.idxmax()
        after = ex[tp:b + pd.Timedelta(hours=72)]
        below = after < 0.1 * pk
        t90 = (below.idxmax() - tp).total_seconds() / 3600 if below.any() else np.nan
        storm = ((storm_hours >= a - pd.Timedelta(hours=3)) & (storm_hours <= b)).any()
        rows.append(dict(start=a, end=b, dur_h=(b - a).total_seconds() / 3600 + 0.25, peak=pk,
                         t90_h=t90, storm=bool(storm), summer=a.month in (6, 7, 8)))
    return pd.DataFrame(rows)


def summary(e: pd.DataFrame) -> dict:
    return {"n": int(len(e)), "quantiles": Q,
            "duration_h": e.dur_h.quantile(Q).round(2).tolist(),
            "t90_h": e.t90_h.quantile(Q).round(2).tolist()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--eaglei", default="raw/eaglei/eaglei_davidson_2014_2025.csv")
    ap.add_argument("--drivers", default="data/standard/drivers.parquet")
    ap.add_argument("--out", default="twin/evidence/eaglei_restoration.json")
    ap.add_argument("--min-excess", type=float, default=500)
    a = ap.parse_args(argv)

    d = pd.read_csv(a.eaglei, parse_dates=["run_start_time"])
    s = d.set_index("run_start_time")["customers_out"].sort_index()
    s = s[~s.index.duplicated()]
    s = s.reindex(pd.date_range("2015-01-01", "2025-12-31 23:45", freq="15min")).fillna(0.0)
    s = s[s.index.year != 2018]

    dr = pd.read_parquet(a.drivers, columns=["timestamp", "variable", "value", "source_id"])
    th = dr[(dr.variable == "thunder") & (dr.source_id == "asos_bna")].set_index("timestamp")["value"]
    th.index = th.index.tz_convert("UTC").tz_localize(None)
    th = th.groupby(level=0).max()

    e = events(s, th[th > 0].index, a.min_excess)
    ns = e[~e.storm]
    big = ns[ns.peak > 3000]
    out = {
        "source": "EAGLE-I county customers out (eaglei2023), Davidson County FIPS 47037, 2015–2025 excl. 2018",
        "method": f"excess over 7-day rolling median > {a.min_excess:.0f} customers; gaps <= 1 h merged; "
                  "storm = ASOS BNA thunder from 3 h before start to end; t90 = hours from peak until excess < 10% of peak",
        "caveat": "County aggregate; restoration includes switching, so it is customer outage time, not equipment repair time.",
        "all": summary(e),
        "storm": summary(e[e.storm]),
        "non_storm": summary(ns),
        "non_storm_summer": summary(ns[ns.summer]),
        "non_storm_peak_gt_3000": summary(big),
        "non_storm_peak_gt_3000_share_single_snapshot": round(float((big.dur_h <= 0.25).mean()), 3),
        "non_storm_peak_gt_3000_min_30min": summary(big[big.dur_h >= 0.5]),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    for k in ("non_storm", "storm", "non_storm_peak_gt_3000_min_30min"):
        print(k, out[k])
    print("wrote", a.out)


if __name__ == "__main__":
    main()
