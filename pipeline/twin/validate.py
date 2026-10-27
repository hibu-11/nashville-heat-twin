"""
【中文】验证指标（设计方案阶段 D 的雏形，学术手册 Eq. 17–18）：
    Spearman 秩相关 ρ，按天分块 bootstrap 置信区间；AUC（Mann–Whitney）；气温分箱的经验停电曲线。
Validation metrics (handbook Eq. 17–18).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr


def spearman_ci(x, y, groups, n_boot=500, seed=0) -> dict:
    """【中文】ρ 与 95% 置信区间；按 groups（日期）整块重抽样，保留日内自相关。
    ρ with a 95% day-block bootstrap interval (keeps within-day autocorrelation)."""
    x, y, g = np.asarray(x, float), np.asarray(y, float), np.asarray(groups)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y, g = x[ok], y[ok], g[ok]
    if len(x) < 10 or np.nanstd(x) == 0 or np.nanstd(y) == 0:
        return {"rho": None, "lo": None, "hi": None, "n": int(len(x))}
    rho = float(spearmanr(x, y).statistic)
    rng = np.random.default_rng(seed)
    days = np.unique(g)
    members = {d: np.where(g == d)[0] for d in days}
    boots = []
    for _ in range(n_boot):
        pick = np.concatenate([members[d] for d in rng.choice(days, size=len(days), replace=True)])
        if np.std(x[pick]) > 0 and np.std(y[pick]) > 0:
            boots.append(spearmanr(x[pick], y[pick]).statistic)
    lo, hi = (np.percentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan))
    return {"rho": round(rho, 3), "lo": round(float(lo), 3), "hi": round(float(hi), 3), "n": int(len(x)),
            "n_days": int(len(days))}


def auc(score, label) -> dict:
    """【中文】AUC = P(正例得分 > 负例得分) = U / (n1 n0)（Eq. 17b）/ AUC via Mann–Whitney U."""
    s, l = np.asarray(score, float), np.asarray(label, bool)
    pos, neg = s[l], s[~l]
    if len(pos) == 0 or len(neg) == 0:
        return {"auc": None, "n_pos": int(len(pos)), "n_neg": int(len(neg))}
    u = mannwhitneyu(pos, neg, alternative="two-sided")
    return {"auc": round(float(u.statistic / (len(pos) * len(neg))), 3), "p_value": float(u.pvalue),
            "n_pos": int(len(pos)), "n_neg": int(len(neg))}


def outage_vs_temperature(ta, obs, storm, bins=(20, 24, 28, 30, 32, 34, 36, 40)) -> list:
    """【中文】非雷暴小时的实测停电用户数按气温分箱（纯数据检查，不依赖模型）。
    Observed customers out on non-storm hours, binned by air temperature (data-only check)."""
    df = pd.DataFrame({"ta": ta, "obs": obs, "storm": storm}).dropna()
    df = df[~df["storm"].astype(bool)]
    df["bin"] = pd.cut(df["ta"], bins=list(bins))
    g = df.groupby("bin", observed=True)["obs"]
    return [{"bin_c": str(k), "hours": int(len(v)), "median": float(v.median()), "p90": float(v.quantile(0.9)),
             "share_hours_over_1000": round(float((v > 1000).mean()), 3)} for k, v in g]


def stratified_auc(score, label, strata_var, q=5) -> dict:
    """【中文】按 strata_var 的分位数分层，层内算 AUC，再按层内正例数加权平均（控制路段长度等混杂）。
    AUC within quantile strata of a confounder, weighted by positives per stratum."""
    df = pd.DataFrame({"s": score, "y": np.asarray(label, bool), "z": strata_var}).dropna()
    df["bin"] = pd.qcut(df["z"], q, labels=False, duplicates="drop")
    parts = []
    for _, g in df.groupby("bin"):
        r = auc(g["s"], g["y"])
        if r["auc"] is not None:
            parts.append((r["auc"], r["n_pos"]))
    if not parts:
        return {"auc": None}
    w = sum(n for _, n in parts)
    return {"auc": round(sum(a * n for a, n in parts) / w, 3), "strata": len(parts), "n_pos": int(w)}
