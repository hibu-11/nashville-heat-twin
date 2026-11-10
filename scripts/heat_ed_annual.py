"""
【中文】B 线初步检验：Davidson 县每年的高温病症急诊人次（田纳西卫生厅开放数据 ayhy-c48z，2012–2023）与
BNA 当年 5–9 月的高温指标（≥35 °C 天数、日均气温超过 25 °C 的度日等）是否相关。年度数据只有 10 个重叠年份，
只能说明有无信号；逐日关系需要申请逐日急诊数据。周边四县合计作为稳健性检查。
    .venv/bin/python scripts/heat_ed_annual.py

Annual heat-illness ED visits (Tennessee Department of Health) against BNA summer heat metrics, a first test for
line B. Writes twin/evidence/heat_ed_annual.json (published aggregates only).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

CORE5 = ["Davidson", "Rutherford", "Williamson", "Sumner", "Wilson"]


def heat_metrics(path: str) -> pd.DataFrame:
    b = pd.read_csv(path, usecols=["valid", "tmpf"], na_values="M")
    t = pd.to_datetime(b["valid"]).dt.tz_localize("UTC").dt.tz_convert("America/Chicago")
    c = pd.Series(((b["tmpf"] - 32) * 5 / 9).to_numpy(), index=t)
    d = c.resample("D").agg(["max", "mean", "count"])
    d = d[(d["count"] >= 18) & d.index.month.isin([5, 6, 7, 8, 9])]
    return d.groupby(d.index.year).agg(
        days_ge35=("max", lambda x: int((x >= 35).sum())), days_ge33=("max", lambda x: int((x >= 33.3).sum())),
        degree_days_over25=("mean", lambda x: float(np.clip(x - 25, 0, None).sum())), mean_tmax=("max", "mean"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ed", default="raw/health/tn_hri_annual_ed.json")
    ap.add_argument("--bna", default="raw/asos_bna_hourly.csv")
    ap.add_argument("--out", default="twin/evidence/heat_ed_annual.json")
    a = ap.parse_args(argv)

    ed = pd.DataFrame(json.loads(Path(a.ed).read_text()))
    ed["count"] = pd.to_numeric(ed["count"], errors="coerce")
    ed["year"] = ed["year"].astype(int)
    dav = ed[ed["county"] == "Davidson"].set_index("year")["count"].rename("davidson")
    msa = ed[ed["county"].isin(CORE5)].groupby("year")["count"].sum(min_count=len(CORE5)).rename("five_county")
    df = heat_metrics(a.bna).join(dav).join(msa).dropna(subset=["davidson"])

    cor = {}
    for m in ("days_ge35", "days_ge33", "degree_days_over25", "mean_tmax"):
        r1, p1 = spearmanr(df[m], df["davidson"])
        r2, p2 = spearmanr(df[m], df["five_county"])
        cor[m] = {"davidson_rho": round(float(r1), 3), "davidson_p": round(float(p1), 3),
                  "five_county_rho": round(float(r2), 3), "five_county_p": round(float(p2), 3)}
    X = np.c_[np.ones(len(df)), df["degree_days_over25"]]
    y = np.log(df["davidson"].to_numpy(float))
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    se = float(np.sqrt(e.var(ddof=2) * np.linalg.inv(X.T @ X)[1, 1]))
    out = {
        "source": "Tennessee Department of Health heat-related illness ED visits by county and year (healthdata.tn.gov ayhy-c48z); BNA ASOS hourly air temperature",
        "method": "May–September heat metrics from BNA daily max / mean (local time, days with ≥ 18 hourly reports); Spearman correlation with annual visits; log-linear fit of Davidson visits on degree-days of daily mean above 25 °C (Nashville minimum-mortality temperature, Gasparrini et al. 2015).",
        "caveat": "Ten overlapping years (2014–2023); annual totals only; 2020 is low, probably because of COVID-19 care avoidance. Evidence of a signal, not a daily exposure–response curve.",
        "years": [int(x) for x in df.index],
        "table": df.round(2).reset_index(names="year").to_dict(orient="records"),
        "spearman": cor,
        "log_visits_per_degree_day_over25": {"slope": round(float(b[1]), 5), "se": round(se, 5), "n": int(len(df))},
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps({"spearman": cor, "slope": out["log_visits_per_degree_day_over25"]}, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
