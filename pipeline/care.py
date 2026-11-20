"""
【中文】就医时间（2026-11-17 定义，医疗设施只含医院）：按急诊就诊人次计算的"路程 + 等待"增量。
- 路程：每个人口网格到各医院的正常路程（当地 17:00 的交通）；医院在高峰日关闭（停电或断水）的那部分时间，
  该网格的病人改去下一家开放的医院（按关闭小时的比例分配）。信号灯熄灭造成的拥堵增量由 pipeline.core.access_runs
  单独给出后加上。
- 等待：每家医院的日常就诊量 = 全县 D0 × 其服务范围的人口比例；利用率 ρ_h = 当天负荷 / (日常负荷 / ρ0 × 开放比例)，
  上限 0.95；等待 W_h = W0·ρ_h/(1−ρ_h)。
- 就医时间增量 = 高峰日每次急诊就诊的平均（路程 + 等待）− 该就诊者正常情况下的（路程 + 等待）。
  就诊包括日常就诊和 B 线新增就诊（热病症、呼吸机等设备用户）。
- 分解（decompose）：把增量按四个因素做 Shapley 分解——热病症新增就诊、设备用户新增就诊、医院停电关闭、
  医院断水关闭；拥堵是可加的，单独列出。

Time to care per ED visit (travel + waiting, per hospital) and its Shapley decomposition.
"""
from __future__ import annotations

from itertools import combinations
from math import factorial

import numpy as np
import pandas as pd

from .twin import traffic

RHO_MAX = 0.95
LOST_PENALTY_MIN = 30.0               # 【中文】同 pipeline.core / same assumption as pipeline.core
FACTORS = ("heat", "device", "power", "water")


def _hospital_times(ctx: dict, net, edges, hour_local: int) -> np.ndarray:
    """【中文】每个人口网格到每家医院的路程（分钟）/ travel time from every population cell to every hospital."""
    w = traffic.travel_time(edges, ctx["eta"][hour_local], ctx["cap_lane"], ctx["A"], ctx["B"], None)
    d = ctx["dest"]["hospital"]
    node_of = dict(zip(d["ids"], d["nodes"]))
    T = np.full((len(ctx["cells"]), len(net.hosp)), np.inf)
    for j, h in enumerate(net.hosp):
        n = node_of.get(h, -1)
        if n >= 0:
            T[:, j] = traffic.nearest_time(ctx["net"], w, [n])[ctx["cell_nodes"]]
    return T


def prepare(ctx: dict, net, assets=None, hour_local: int = 17) -> dict:
    """【中文】网格 × 医院的正常路程矩阵、网格所属分区 / travel matrix cells × hospitals and cell zones."""
    T = _hospital_times(ctx, net, ctx["edges"], hour_local)
    cells = ctx["cells"]
    zidx = {z: i for i, z in enumerate(net.zone_id)}
    cz = np.array([zidx.get(z, -1) for z in cells.get("zone", pd.Series([None] * len(cells)))])
    pop = ctx["pop"].astype(float)
    reach = np.isfinite(T).any(1) & (cz >= 0)
    zone_pop = np.bincount(cz[reach], weights=pop[reach], minlength=len(net.zone_id))
    T, cz, pop = T[reach], cz[reach], pop[reach]
    order = np.argsort(T, axis=1)
    share = pop / pop.sum()
    cp = {"T": T, "order": order, "Tsorted": np.take_along_axis(T, order, axis=1), "cz": cz, "pop": pop,
          "share": share, "zone_pop": zone_pop, "L0": np.bincount(order[:, 0], weights=share, minlength=T.shape[1]),
          "reach": reach}
    cp["rut_unit"] = rut_unit(ctx, net, cp, hour_local)
    return cp


def rut_unit(ctx: dict, net, cp: dict, hour_local: int = 17, dv: float = 1.0) -> float:
    """【中文】K11 车辙（M-49）：每条有实测车辙的路段车速降低 dv × 车辙深度（英寸）mph 时，每次急诊就诊到最近医院的平均路程增量
    （分钟）。增量很小，与车速降低成线性，所以每次运行的车辙增量 = 本值 × (k_rut · ΔT · b_iri · c_speed) / dv。

    K11 rutting (M-49): added travel per ED visit to the nearest hospital when every edge with a measured rut slows by
    dv mph per inch of rut. The effect is small and linear, so each run scales it by k_rut * dT * b_iri * c_speed / dv."""
    e = ctx["edges"]
    if "rut_in" not in e or not (e["rut_in"] > 0).any():
        return 0.0
    v = e["speed_mph"].to_numpy(float)
    slow = np.maximum(v - dv * e["rut_in"].to_numpy(float), 1.0)
    T2 = _hospital_times(ctx, net, e.assign(t0_min=e["length_m"] / (slow * traffic.MPH) / 60.0), hour_local)[cp["reach"]]
    return float((cp["share"] * (np.min(T2, axis=1) - cp["Tsorted"][:, 0])).sum())


def _one(cp: dict, D0: float, rho0: float, W0: float, closed_h: np.ndarray, extra_zone: np.ndarray,
         off=frozenset(), detail: bool = False):
    """【中文】一次运行：每次急诊就诊的平均路程与等待增量 / one run: added travel and waiting per ED visit."""
    order, cz, pop, share, L0 = cp["order"], cp["cz"], cp["pop"], cp["share"], cp["L0"]
    nH = order.shape[1]
    o = np.clip(1 - closed_h / 24.0, 0, 1) if "R17" not in off else np.ones(nH)
    O = o[order]
    stay = np.cumprod(np.c_[np.ones(len(O)), 1 - O[:, :-1]], axis=1)
    wgt = O * stay
    tot = wgt.sum(1, keepdims=True)
    wgt = np.where(tot > 0, wgt / np.maximum(tot, 1e-12), 0.0)
    extra = extra_zone[cz] * pop / np.maximum(cp["zone_pop"][cz], 1e-9)   # 【中文】分区新增就诊按人口分到网格
    dem = D0 * share + extra
    load = np.bincount(order.ravel(), weights=(wgt * dem[:, None]).ravel(), minlength=nH)
    cap = D0 * L0 / rho0 * o
    # 【中文】没有日常服务范围的医院（L0 = 0）按最小的正常容量计，避免改道病人遇到虚构的满负荷
    # hospitals with no normal catchment get the smallest normal capacity, so rerouted patients do not meet a fictitious full queue
    cap = np.where(L0 > 0, cap, D0 * L0[L0 > 0].min() / rho0 * o)
    rho = np.where(cap > 0, np.minimum(RHO_MAX, load / np.maximum(cap, 1e-12)), RHO_MAX)
    W = W0 * rho / (1 - rho)
    base_w = W0 * rho0 / (1 - rho0)
    if "R22" in off:                                              # 【中文】需求不增加等待 / demand does not lengthen waiting
        W = np.where(cap > 0, base_w, W)
    Wk = W[order]
    # 【中文】每位就诊者与自己的正常情况比较 / each visitor is compared with their own normal trip and wait
    lost = tot[:, 0] <= 0
    d_trav = np.where(lost, LOST_PENALTY_MIN, (wgt * cp["Tsorted"]).sum(1) - cp["Tsorted"][:, 0])
    d_wait = np.where(lost, 0.0, (wgt * Wk).sum(1) - base_w)
    travel = float((dem * d_trav).sum() / dem.sum())
    wait = float((dem * d_wait).sum() / dem.sum())
    if not detail:
        return travel, wait
    at_cap = rho >= RHO_MAX - 1e-9
    v_h = np.bincount(order.ravel(), weights=(wgt * dem[:, None]).ravel(), minlength=nH)
    return travel, wait, {"rho": rho, "load": load, "cap": cap, "normal": D0 * L0, "open": o,
                          "share_visits_at_cap": float(v_h[at_cap].sum() / v_h.sum()), "n_at_cap": int(at_cap.sum())}


def ed_time(cp: dict, care: dict, th: dict, congestion: np.ndarray | None = None, off=frozenset()) -> dict:
    """【中文】每次运行：高峰日每次急诊就诊的平均路程与等待增量（分钟）/ per-run added travel and waiting per ED visit."""
    N = len(th["C-H14"])
    out = {k: np.zeros(N) for k in ("travel", "wait", "time", "peak_extra", "share_visits_at_cap", "hospitals_at_cap")}
    for r in range(N):
        tr, wt, d = _one(cp, th["C-H15"][r], th["C-H14"][r], th["C-H16"][r], care["hosp_closed_h"][r],
                         care["extra_zone"][r], off, detail=True)
        out["travel"][r], out["wait"][r], out["time"][r] = tr, wt, tr + wt
        out["peak_extra"][r] = care["extra_zone"][r].sum()
        out["share_visits_at_cap"][r], out["hospitals_at_cap"][r] = d["share_visits_at_cap"], d["n_at_cap"]
    if congestion is not None:
        out["congestion"] = np.asarray(congestion, float)
        out["time"] = out["time"] + out["congestion"]
    return out


def decompose(cp: dict, care: dict, th: dict, congestion: np.ndarray | None = None, runs=None) -> dict:
    """【中文】Shapley 分解：每次运行的就医时间增量分给 热病症新增就诊 / 设备用户新增就诊 / 医院停电 / 医院断水，
    各因素对所有加入顺序的边际贡献取平均；四项之和等于（路程 + 等待）增量。拥堵可加，单独列出。

    Shapley decomposition of each run's added time (travel + waiting) over heat-illness visits, device-user visits,
    hospital closures from power and from water; the four parts add up to the total. Congestion is additive and
    reported separately."""
    N = len(th["C-H14"])
    runs = np.arange(N) if runs is None else np.asarray(runs)
    k = len(FACTORS)
    zero_z, zero_h = np.zeros_like(care["extra_zone"][0]), np.zeros_like(care["hosp_closed_h"][0])
    out = {f: np.zeros(len(runs)) for f in FACTORS} | {"travel": np.zeros(len(runs)), "wait": np.zeros(len(runs))}
    for i, r in enumerate(runs):
        on = {"heat": care["extra_heat_zone"][r], "device": care["extra_dep_zone"][r],
              "power": care["hosp_closed_power_h"][r], "water": care["hosp_closed_water_h"][r]}
        memo = {}

        def v(S):
            if S not in memo:
                ez = (on["heat"] if "heat" in S else zero_z) + (on["device"] if "device" in S else zero_z)
                ch = (on["power"] if "power" in S else zero_h) + (on["water"] if "water" in S else zero_h)
                memo[S] = _one(cp, th["C-H15"][r], th["C-H14"][r], th["C-H16"][r], ch, ez)
            return memo[S]
        full = v(frozenset(FACTORS))
        out["travel"][i], out["wait"][i] = full
        for f in FACTORS:
            rest = [g for g in FACTORS if g != f]
            phi = 0.0
            for m in range(k):
                wgt = factorial(m) * factorial(k - m - 1) / factorial(k)
                for S in combinations(rest, m):
                    S = frozenset(S)
                    phi += wgt * (sum(v(S | {f})) - sum(v(S)))
            out[f][i] = phi
        out.setdefault("baseline_minus", np.zeros(len(runs)))[i] = sum(v(frozenset()))   # 【中文】应为 0 / should be 0
    out["congestion"] = np.zeros(len(runs)) if congestion is None else np.asarray(congestion, float)[runs]
    return out
