"""
【中文】多年校准（PIPELINE_SPEC M-43）：用 EAGLE-I 2015–2025 夏季（6–8 月）的县级停电数据给参数抽样加权。
    python -m pipeline.calibrate [--years 2015-2025] [--runs 2000] [--seed 20261027]

做法（对已有先验抽样加权，不需要额外模拟）：
    1) 每年用同一随机种子抽参数，因此第 r 次运行在各年的参数相同；逐年模拟夏季（含城市气温场、河水降额）。
    2) 观测：非风暴日（当地日内无 ±3 h 雷暴）的日最大停电户数 y_d。
       模型：ŷ_{r,d} = 研究区当日最大停电人口比例 × 全县用户数（假设 A-C1：全县单位用户的高温停电风险与研究区相同）。
    3) 似然：y_d ~ NegBin(μ = b_y + ŷ_{r,d}, k_y)，b_y、k_y 由当年凉爽非风暴日（日最高 < 32 °C）的矩估计给出。
    4) 约束：TVA 在 2015–2025 年夏季没有轮流停电，所以模拟出系统甩负荷（M-18）的运行权重为 0。
    5) 逐日似然 w_r ∝ exp(Σ log p(y_d | r)) 在约 700 天上会退化到少数运行，只作诊断；
       主方法为 ABC：统计量 S = 热日平均 − 凉日平均停电户数，w_r ∝ exp(−(S_r − S_obs)² / 2 SE²)，
       SE 为观测 S 的按天 bootstrap 标准误。报告有效样本量 ESS、参数后验分位数与先验对比。
另做纯数据分析：多年非风暴日的日最高气温与停电的关系、热日与凉日的停电差值（不依赖模型）。

Multi-year calibration (M-43): importance re-weighting of the prior Monte Carlo runs with EAGLE-I
summers 2015–2025, plus a data-only analysis of heat and outages.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib

import numpy as np
import pandas as pd
import yaml
from scipy.special import gammaln, logsumexp
from scipy.stats import spearmanr

from .adapters.base import write_json
from .build import ROOT, code_version
from .cascade import POWER_PARAMS, air_field_temperatures, load, river_inputs, river_shed
from .twin.cascade import Network, simulate
from .twin.params import Params
from .twin.validate import outage_vs_temperature, spearman_ci


def nb_logpmf(y, mu, k):
    """【中文】负二项对数概率（均值 μ，形状 k；方差 = μ + μ²/k）/ negative binomial log pmf."""
    return (gammaln(y + k) - gammaln(k) - gammaln(y + 1) + k * np.log(k / (k + mu)) + y * np.log(mu / (k + mu)))


def wquantile(v, w, qs):
    o = np.argsort(v)
    c = np.cumsum(w[o]) / w.sum()
    return [float(v[o][min(np.searchsorted(c, q), len(v) - 1)]) for q in qs]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Multi-year calibration against EAGLE-I (M-43)")
    ap.add_argument("--years", default="2015-2025")
    ap.add_argument("--runs", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--air-field", choices=["on", "off"], default="on")
    ap.add_argument("--outage-source", default="eaglei_davidson")
    ap.add_argument("--cool-tmax-c", type=float, default=32.0, help="days below this daily max define the background")
    ap.add_argument("--hot-tmax-c", type=float, default=35.0)
    # 【中文】背景停电低于此值的年份视为 EAGLE-I 覆盖不足（如 2018 年 Davidson 背景仅约 4 户），不进入似然
    # years whose background is below this are treated as EAGLE-I coverage gaps and left out of the likelihood
    ap.add_argument("--min-background", type=float, default=100.0)
    ap.add_argument("--max-k", type=float, default=50.0, help="cap on the negative-binomial shape")
    a = ap.parse_args(argv)
    y0, _, y1 = a.years.partition("-")
    years = list(range(int(y0), int(y1 or y0) + 1))

    cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text(encoding="utf-8"))
    proj = cfg["project"]
    tz = proj.get("timezone", "UTC")
    dep_cfg = next(d for d in cfg["datasets"] if d["kind"] == "dependency_rules")
    oc = next(d for d in cfg["datasets"] if d["id"] == a.outage_source)
    n_cust = float(oc["customers_total"])
    std = ROOT / proj.get("standard_dir", "data/standard")
    site = ROOT / proj.get("site_data_dir", "site/data") / "twin" / "results"
    assets, deps, couplings = load(std, "assets"), load(std, "dependencies"), load(std, "couplings")
    drivers, events = load(std, "drivers"), load(std, "events")
    params = Params(couplings)
    net = Network(assets, deps, dep_cfg)
    pop_total = float(net.zone_pop.sum())

    bna = drivers[drivers["station_id"] == "BNA"].pivot_table(index="timestamp", columns="variable", values="value")
    eagle = events[events["source_id"] == a.outage_source].set_index("start_time")["severity"]
    eagle = eagle[~eagle.index.duplicated()]

    loglik, shed_any, per_year, daily_rows = None, None, {}, []
    # 【中文】ABC 统计量的累加：模型在热日 / 凉日的县级停电户数之和，观测值列表
    # accumulators for the ABC summary statistic (hot-day minus cool-day mean customers out)
    m_hot, m_cool, o_hot, o_cool = np.zeros(a.runs), np.zeros(a.runs), [], []
    th = None
    for y in years:
        hours = pd.date_range(pd.Timestamp(f"{y}-06-01", tz=tz), pd.Timestamp(f"{y}-08-31", tz=tz) + pd.Timedelta(hours=23),
                              freq="h").tz_convert("UTC")
        w = bna.reindex(hours)
        Ta = w["air_temp_c"].interpolate(limit_direction="both").to_numpy()
        storm = pd.Series(w["thunder"].fillna(0).to_numpy()).rolling(7, center=True, min_periods=1).max().to_numpy() > 0
        obs = eagle.reindex(hours).fillna(0).to_numpy()           # 【中文】A-D2：无记录 = 0
        Ta_sub, Ta_zone, _ = air_field_temperatures(cfg, assets, net, Ta, hours, tz, a.air_field)
        river = river_inputs(cfg, hours)
        rng = np.random.default_rng(a.seed)
        th = params.sample(a.runs, rng)                            # 【中文】各年参数相同 / same draws every year
        shed, _ = river_shed(river, Ta, th, 0.0)
        print(f"[calibrate] {y}: simulating {a.runs} runs …", flush=True)
        r = simulate(net, Ta, th, rng, Ta_sub=Ta_sub, Ta_zone=Ta_zone, shed=shed)

        day = pd.Index(hours.tz_convert(tz).date)
        df = pd.DataFrame({"day": day, "obs": obs, "ta": Ta, "storm": storm})
        dd = df.groupby("day").agg(y=("obs", "max"), tmax=("ta", "max"), storm=("storm", "max"))
        keep = ~dd["storm"].to_numpy()
        frac = pd.DataFrame(r["pop_out"].T / max(pop_total, 1.0), index=day).groupby(level=0).max().to_numpy().T  # (N, D)
        yhat = frac * n_cust
        cool = keep & (dd["tmax"].to_numpy() < a.cool_tmax_c)
        if cool.sum() < 10:
            cool = keep & (dd["tmax"].to_numpy() <= np.nanpercentile(dd["tmax"][keep], 33))
        yc = dd["y"].to_numpy()[cool]
        b = max(float(np.mean(yc)), 1.0)
        var = float(np.var(yc))
        k = min(b ** 2 / (var - b), a.max_k) if var > b else a.max_k
        yy = dd["y"].to_numpy()[keep]
        used = b >= a.min_background
        ll = nb_logpmf(yy[None, :], b + yhat[:, keep], k).sum(1) if used else np.zeros(a.runs)
        loglik = ll if loglik is None else loglik + ll
        sa = (shed.max(1) > 0) if shed is not None else np.zeros(a.runs, bool)
        shed_any = sa if shed_any is None else shed_any | sa
        hot = keep & (dd["tmax"].to_numpy() >= a.hot_tmax_c)
        cl = keep & (dd["tmax"].to_numpy() < a.cool_tmax_c)
        if used:
            m_hot += yhat[:, hot].sum(1); m_cool += yhat[:, cl].sum(1)
            o_hot += dd["y"].to_numpy()[hot].tolist(); o_cool += dd["y"].to_numpy()[cl].tolist()
        per_year[y] = {"used_in_likelihood": bool(used), "days": int(len(dd)), "non_storm_days": int(keep.sum()),
                       "hot_non_storm_days": int(hot.sum()),
                       "cool_days_for_background": int(cool.sum()), "background_customers": round(b, 1),
                       "nb_shape_k": round(float(k), 3), "obs_max_non_storm": float(yy.max()) if len(yy) else None,
                       "tmax_max_c": round(float(dd["tmax"].max()), 1),
                       "model_mean_daily_max_customers_hot_days": round(float(yhat[:, hot].mean()), 1) if hot.any() else None,
                       "runs_with_system_shed": round(float(sa.mean()), 4)}
        daily_rows.append(dd.assign(year=y, keep=keep & used, model_mean=yhat.mean(0)))
        print(f"[calibrate]   {'used' if used else 'EXCLUDED (coverage)'}: non-storm days {keep.sum()}, hot {hot.sum()}, background {b:.0f} customers, "
              f"k {k:.2f}, runs with system shed {sa.mean():.1%}", flush=True)

    # ------------------------------------------------------------------ weights
    # 【中文】(a) 逐日负二项似然：约 700 天累加后权重退化到少数几次运行（只作诊断）
    # (a) full daily NB likelihood: degenerates onto a few runs over ~700 days (diagnostic only)
    lw = np.where(shed_any, -np.inf, loglik)
    w_nb = np.exp(lw - logsumexp(lw))
    ess_nb = float(1 / np.sum(w_nb ** 2))
    # 【中文】(b) 主方法：ABC，统计量 S = 热日平均 − 凉日平均（县级停电户数），高斯核宽度 = 观测 S 的按天 bootstrap 标准误
    # (b) main: ABC on S = hot-day mean − cool-day mean customers out, Gaussian kernel with the bootstrap SE of observed S
    oh, oc = np.array(o_hot), np.array(o_cool)
    s_obs = float(oh.mean() - oc.mean())
    rb = np.random.default_rng(1)
    boot = [rb.choice(oh, len(oh)).mean() - rb.choice(oc, len(oc)).mean() for _ in range(2000)]
    se = float(np.std(boot))
    s_mod = m_hot / len(oh) - m_cool / len(oc)
    la = np.where(shed_any, -np.inf, -0.5 * ((s_mod - s_obs) / se) ** 2)
    w = np.exp(la - logsumexp(la))
    ess = float(1 / np.sum(w ** 2))
    abc = {"statistic": "mean daily max customers out, hot (Tmax >= %.0f C) minus cool (< %.0f C) non-storm days" % (a.hot_tmax_c, a.cool_tmax_c),
           "observed": round(s_obs, 1), "observed_se": round(se, 1), "n_hot_days": int(len(oh)), "n_cool_days": int(len(oc)),
           "model_prior_5_50_95": [round(float(x), 1) for x in np.percentile(s_mod, [5, 50, 95])],
           "model_posterior_mean": round(float(np.sum(w * s_mod)), 1),
           "share_runs_within_2se": round(float((np.abs(s_mod - s_obs) <= 2 * se).mean()), 3)}
    post = []
    for kp in POWER_PARAMS:
        v = th[kp]
        if np.ptp(v) == 0:
            continue
        pq = np.percentile(v, [5, 50, 95]).tolist()
        wq = wquantile(v, w, [0.05, 0.5, 0.95])
        post.append({"param": kp, "name": params.table.at[kp, "param_name"], "basis": params.table.at[kp, "basis"],
                     "prior_5_50_95": [round(x, 4) for x in pq], "posterior_5_50_95": [round(x, 4) for x in wq],
                     "posterior_mean": round(float(np.sum(w * v)), 4), "prior_mean": round(float(v.mean()), 4),
                     "shift_in_prior_sd": round(float((np.sum(w * v) - v.mean()) / v.std()), 3)})
    post.sort(key=lambda p: -abs(p["shift_in_prior_sd"]))

    # ------------------------------------------------------------------ data-only analysis
    D = pd.concat(daily_rows)
    N = D[D["keep"]]
    grp = np.arange(len(N))
    hot, cool = N["tmax"] >= a.hot_tmax_c, N["tmax"] < a.cool_tmax_c
    rng = np.random.default_rng(0)
    diffs = [np.median(rng.choice(N.loc[hot, "y"], hot.sum())) - np.median(rng.choice(N.loc[cool, "y"], cool.sum()))
             for _ in range(1000)] if hot.sum() > 2 and cool.sum() > 2 else []
    by_year_rho = {int(y): (round(float(spearmanr(g["tmax"], g["y"]).statistic), 3) if g["y"].std() > 0 else None)
                   for y, g in N.groupby("year")}
    data_only = {
        "daily_tmax_vs_daily_max_outages_non_storm": spearman_ci(N["tmax"], N["y"], grp),
        "by_year_spearman": by_year_rho,
        "median_daily_max_hot_days": float(N.loc[hot, "y"].median()) if hot.any() else None,
        "median_daily_max_cool_days": float(N.loc[cool, "y"].median()) if cool.any() else None,
        "hot_minus_cool_median": None if not diffs else {"est": float(N.loc[hot, "y"].median() - N.loc[cool, "y"].median()),
                                                          "lo": float(np.percentile(diffs, 2.5)), "hi": float(np.percentile(diffs, 97.5))},
        "n_hot_days": int(hot.sum()), "n_cool_days": int(cool.sum()),
        "binned_by_tmax": outage_vs_temperature(N["tmax"].to_numpy(), N["y"].to_numpy(), np.zeros(len(N), bool),
                                                bins=(20, 28, 30, 32, 34, 36, 40)),
    }
    stamp = dt.datetime.now(dt.timezone.utc)
    run_id = f"calibration-{stamp:%Y%m%dT%H%M%SZ}-{hashlib.sha256(couplings.to_csv(index=False).encode()).hexdigest()[:10]}"
    out = {"run_id": run_id, "created": stamp.isoformat(timespec="seconds"), "code_version": code_version(),
           "method": "PIPELINE_SPEC M-43 (self-normalised importance sampling of prior runs)",
           "years": years, "runs": a.runs, "seed": a.seed, "outage_source": a.outage_source,
           "customers_total": n_cust, "population_in_zones": pop_total, "air_field": a.air_field,
           "assumptions": {"A-C1": "heat-outage risk per customer elsewhere in Davidson equals the AOI's",
                           "A-C2": "daily maxima on non-storm days are independent given background b_y and shape k_y",
                           "A-C3": "TVA had no summer rotating outages 2015–2025, so runs with system shed get zero weight"},
           "years_excluded": [y for y, r in per_year.items() if not r["used_in_likelihood"]],
           "min_background": a.min_background, "max_k": a.max_k,
           "ess": round(ess, 1), "abc": abc, "ess_full_nb_likelihood": round(ess_nb, 1),
           "max_weight_full_nb": round(float(w_nb.max()), 4), "runs_rejected_by_shed_constraint": int(shed_any.sum()),
           "max_weight": round(float(w.max()), 4), "per_year": per_year, "posterior": post, "data_only": data_only}
    res = std / "results" / run_id
    res.mkdir(parents=True, exist_ok=True)
    write_json(res / "calibration.json", out)
    pd.DataFrame({"run": np.arange(a.runs), "log_lik": loglik, "weight_nb": w_nb, "s_model": s_mod, "weight": w,
                  "shed_any": shed_any,
                  **{k: th[k] for k in POWER_PARAMS}}).to_parquet(res / "weights.parquet")
    write_json(site / "calibration.json", out)
    print(f"[calibrate] {run_id}: ABC ESS {ess:.1f} of {a.runs} (full NB likelihood ESS {ess_nb:.1f}); "
          f"{int(shed_any.sum())} runs rejected by the shed constraint")
    print(f"  S observed {s_obs:.0f} ± {se:.0f}; model prior 5/50/95 {abc['model_prior_5_50_95']}; "
          f"{abc['share_runs_within_2se']:.1%} of runs within 2 SE")
    for p in post[:6]:
        print(f"  {p['param']:12s} prior {p['prior_5_50_95']}  posterior {p['posterior_5_50_95']}")
    print(f"  data only: ρ(Tmax, daily max outages, non-storm) = {data_only['daily_tmax_vs_daily_max_outages_non_storm']}")


if __name__ == "__main__":
    main()
