"""
【中文】极端情况分析：就医时间增量是哪一块造成的。读取 pipeline.core 保存的逐次运行明细（runs_+N.npz）：
1. 分解：按就医时间分档（< p50、p50–75、p75–90、p90–95、p95–99、≥ p99），每档各原因的平均分钟数
   （Shapley：热病症新增就诊、设备用户新增就诊、医院停电、医院断水；拥堵另列），以及满负荷医院的就诊比例；
2. 链条：最坏 5% / 1% 的运行与中间 50% 的运行在上游各环节（热失效、停电人·小时、高峰日新增就诊、医院关闭小时、
   参数）上的中位数对比；
3. 通径分析：按模型的因果链做标准化回归，得到各不确定参数经由各条路径对 log(1 + 就医时间) 的直接、间接与总效应，
   500 次自助抽样给出 95% 区间。它描述的是"2,000 次运行之间的差别从哪里来"，与敲除实验（关掉一条关系的效果）互补。

    python -m pipeline.extremes [--scenarios +2,+4]

Where the added time to care comes from in the worst runs; writes site/data/twin/core/extremes.json.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from .adapters.base import write_json
from .build import ROOT

CAUSES = ("heat", "device", "power", "water", "congestion", "rutting")
BINS = [("below p50", 0, 50), ("p50–75", 50, 75), ("p75–90", 75, 90), ("p90–95", 90, 95), ("p95–99", 95, 99), ("p99 and above", 99, 100.01)]
CHAIN = [("thermal failures", "tot:thermal"), ("person-hours without power", "tot:pop_hours"),
         ("hospital hours closed (summer)", "tot:hospital_hours"), ("peak-day heat-illness visits", "tot:peak_day_heat_visits"),
         ("peak-day device-user visits", "tot:peak_day_dep_visits"), ("peak-day open share of hospitals", "tot:peak_day_open_share"),
         ("hospitals at the queue cap", "ed:hospitals_at_cap"), ("share of visits at hospitals at the cap", "ed:share_visits_at_cap"),
         ("K_design", "th:C-P1.Kd"), ("theta_50 (°C)", "th:C-P3"), ("sigma (K)", "th:C-P3.sigma"), ("repair (h)", "th:C-P6"),
         ("q (visit probability)", "th:C-H13"), ("battery (h)", "th:C-H12"), ("rho0", "th:C-H14"), ("D0", "th:C-H15"), ("W0 (min)", "th:C-H16")]

# 【中文】通径模型：外生参数 → 中介变量 → 结局，按模型的因果顺序 / path model in the model's causal order
EXO = {"K_design": "th:C-P1.Kd", "cool_slope": "th:C-P1", "theta50": "th:C-P3", "sigma": "th:C-P3.sigma", "repair": "th:C-P6",
       "hosp_backup": "th:C-H1", "q": "th:C-H13", "battery": "th:C-H12", "k_heat": "th:C-H11",
       "rho0": "th:C-H14", "D0": "th:C-H15", "W0": "th:C-H16"}
MED = {"failures": ("tot:thermal", True), "outage": ("tot:pop_hours", True), "hosp_closed": ("tot:hospital_hours", True),
       "device_peak": ("tot:peak_day_dep_visits", True), "heat_peak": ("tot:peak_day_heat_visits", False)}
EQ = {"failures": ["K_design", "cool_slope", "theta50", "sigma"],
      "outage": ["failures", "repair"],
      "hosp_closed": ["outage", "hosp_backup"],
      "device_peak": ["outage", "q", "battery"],
      "heat_peak": ["k_heat", "outage"],
      "Y": ["device_peak", "heat_peak", "hosp_closed", "outage", "rho0", "D0", "W0"]}


def load_runs(run_id: str, scen: str) -> dict | None:
    p = ROOT / "data/standard/results" / run_id / f"runs_{scen}.npz"
    if not p.exists():
        return None
    z = np.load(p)
    return {k: z[k] for k in z.files}


def decomposition_bins(d: dict) -> list:
    t = d["ed:time"]
    out = []
    for name, lo, hi in BINS:
        m = (t >= np.percentile(t, lo)) & ((t < np.percentile(t, hi)) if hi <= 100 else True)
        if not m.any():
            continue
        row = {"bin": name, "runs": int(m.sum()), "total": round(float(t[m].mean()), 2),
               "share_visits_at_cap": round(float(d["ed:share_visits_at_cap"][m].mean()), 3)}
        row |= {c: round(float(d[f"dec:{c}"][m].mean()), 2) for c in CAUSES}
        out.append(row)
    return out


def chain(d: dict) -> list:
    t = d["ed:time"]
    groups = {"middle 50%": (t >= np.percentile(t, 25)) & (t <= np.percentile(t, 75)),
              "worst 5%": t >= np.percentile(t, 95), "worst 1%": t >= np.percentile(t, 99)}
    rows = []
    for label, k in CHAIN:
        if k not in d:
            continue
        rows.append({"variable": label} | {g: round(float(np.median(d[k][m])), 4) for g, m in groups.items()})
    return rows


def _z(x):
    s = x.std()
    return (x - x.mean()) / (s if s > 0 else 1)


def path_analysis(d: dict, boot: int = 500, seed: int = 1) -> dict:
    V = {k: d[v] for k, v in EXO.items()}
    V |= {k: (np.log1p(np.maximum(d[v], 0)) if lg else d[v].astype(float)) for k, (v, lg) in MED.items()}
    V["Y"] = np.log1p(np.maximum(d["ed:time"], 0))
    N = len(V["Y"])

    def fit(idx):
        Z = {k: _z(v[idx]) for k, v in V.items()}
        B, R2 = {}, {}
        for y, xs in EQ.items():
            X = np.c_[[Z[x] for x in xs]].T
            b, *_ = np.linalg.lstsq(X, Z[y], rcond=None)
            B.update({(x, y): float(bi) for x, bi in zip(xs, b)})
            R2[y] = float(1 - ((Z[y] - X @ b) ** 2).mean())
        return B, R2

    def total(B, s, dst="Y"):
        return 1.0 if s == dst else sum(b * total(B, y, dst) for (x, y), b in B.items() if x == s)

    def routes(B, s, dst="Y", pre=()):
        if s == dst:
            yield pre
            return
        for (x, y), _ in B.items():
            if x == s:
                yield from routes(B, y, dst, pre + ((x, y),))

    B, R2 = fit(np.arange(N))
    rng = np.random.default_rng(seed)
    BS = [fit(rng.integers(0, N, N))[0] for _ in range(boot)]
    ci = lambda f: [round(float(x), 3) for x in np.percentile([f(b) for b in BS], [2.5, 97.5])]  # noqa: E731
    coef = [{"from": x, "to": y, "beta": round(b, 3), "ci95": ci(lambda BB: BB[(x, y)])} for (x, y), b in B.items()]
    eff = []
    for s in list(EXO) + list(MED):
        tt = total(B, s)
        r = [{"route": " → ".join([p[0][0]] + [e[1] for e in p]), "effect": round(float(np.prod([B[e] for e in p])), 3)}
             for p in routes(B, s)]
        eff.append({"variable": s, "kind": "parameter" if s in EXO else "mediator", "total": round(tt, 3),
                    "ci95": ci(lambda BB: total(BB, s)), "direct": round(B.get((s, "Y"), 0.0), 3),
                    "routes": sorted([x for x in r if abs(x["effect"]) >= 0.005], key=lambda x: -abs(x["effect"]))})
    sq = {e["variable"]: e["total"] ** 2 for e in eff if e["kind"] == "parameter"}
    S = sum(sq.values()) or 1
    for e in eff:
        if e["kind"] == "parameter":
            e["share_of_explained"] = round(sq[e["variable"]] / S, 3)
    eff.sort(key=lambda e: (e["kind"] != "parameter", -abs(e["total"])))
    return {"outcome": "log(1 + time to care per ED visit, min)", "runs": N, "equations": EQ,
            "r2": {k: round(v, 3) for k, v in R2.items()}, "coefficients": coef, "effects": eff,
            "note": "Standardised OLS along the model's causal order; parameters are sampled independently, so total² "
                    "approximates each parameter's share of the explained spread. A linear summary of a non-linear model."}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Decompose time to care in the worst runs and run a path analysis")
    ap.add_argument("--scenarios", default="+2,+4")
    ap.add_argument("--boot", type=int, default=500)
    args = ap.parse_args(argv)
    site = ROOT / "site/data/twin/core"
    s = json.loads((site / "summary.json").read_text(encoding="utf-8"))
    out = {"run_id": s["run_id"], "scenarios": {}}
    for sc in args.scenarios.split(","):
        d = load_runs(s["run_id"], sc)
        if d is None:
            print(f"[extremes] {sc}: no per-run file for {s['run_id']} (rerun pipeline.core)")
            continue
        out["scenarios"][sc] = {"bins": decomposition_bins(d), "chain": chain(d), "path": path_analysis(d, args.boot)}
        b = out["scenarios"][sc]["bins"][-2:]
        for row in b:
            print(f"[extremes] {sc} °C {row['bin']:14s} total {row['total']:7.1f} min = " +
                  " + ".join(f"{c} {row[c]:.1f}" for c in CAUSES) + f"; visits at capped hospitals {row['share_visits_at_cap']:.0%}")
        top = [e for e in out["scenarios"][sc]["path"]["effects"] if e["kind"] == "parameter"][:4]
        print(f"[extremes] {sc} °C path analysis, R²(Y) {out['scenarios'][sc]['path']['r2']['Y']}: " +
              ", ".join(f"{e['variable']} {e['total']:+.2f}" for e in top))
    write_json(site / "extremes.json", out)
    print(f"[extremes] wrote {site / 'extremes.json'}")


if __name__ == "__main__":
    main()
