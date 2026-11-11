"""
【中文】就医时间（2026-11-11 定义）：按急诊就诊人次计算的"路程 + 等待"，以及受影响的透析次数。
- 路程：每个人口网格到各医院的正常路程（当地 17:00 的交通）；医院在高峰日停电的那部分时间，该网格的病人改去下一家
  开放的医院（按停电小时的比例分配）。信号灯熄灭造成的拥堵增量由 pipeline.core.access_runs 单独给出后加上。
- 等待：每家医院的日常就诊量 = 全县 D0 × 其服务范围的人口比例；利用率 ρ_h = ρ0 × 当天负荷 / (日常负荷 × 开放比例)，
  上限 0.95；等待 W_h = W0·ρ_h/(1−ρ_h)。
- 就医时间增量 = 高峰日每次急诊就诊的平均（路程 + 等待）− 正常日的平均。就诊包括日常就诊和 B 线新增就诊。
- 透析：营业时间（06–18）内停电的小时数 × 该中心每小时安排的透析次数（病人 × 3 次 / 周 ÷ 7 ÷ 12 小时）。
  病人数按透析位 × 2.54 估计（CMS：913 名病人 / 360 个透析位，T3）。

Time to care per ED visit (travel + waiting, per hospital) and dialysis sessions affected.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .twin import traffic

PATIENTS_PER_STATION = 913 / 360        # 【中文】CMS Davidson 汇总（医保为主，T3）/ CMS Davidson totals
RHO_MAX = 0.95
LOST_PENALTY_MIN = 30.0               # 【中文】同 pipeline.core / same assumption as pipeline.core


def prepare(ctx: dict, net, assets, hour_local: int = 17) -> dict:
    """【中文】网格 × 医院的正常路程矩阵、网格所属分区、透析中心的病人数 / travel matrix and facility sizes."""
    w = traffic.travel_time(ctx["edges"], ctx["eta"][hour_local], ctx["cap_lane"], ctx["A"], ctx["B"], None)
    d = ctx["dest"]["hospital"]
    node_of = dict(zip(d["ids"], d["nodes"]))
    cells = ctx["cells"]
    T = np.full((len(cells), len(net.hosp)), np.inf)
    for j, h in enumerate(net.hosp):
        n = node_of.get(h, -1)
        if n >= 0:
            T[:, j] = traffic.nearest_time(ctx["net"], w, [n])[ctx["cell_nodes"]]
    zidx = {z: i for i, z in enumerate(net.zone_id)}
    cz = np.array([zidx.get(z, -1) for z in cells.get("zone", pd.Series([None] * len(cells)))])
    pop = ctx["pop"].astype(float)
    reach = np.isfinite(T).any(1) & (cz >= 0)
    dial = assets[assets["asset_id"].isin(net.dial)].set_index("asset_id")["attributes"]
    st = dial.map(lambda a: pd.to_numeric((json.loads(a) if isinstance(a, str) else (a or {})).get("# of Dialysis Stations"),
                                          errors="coerce"))
    stations = np.array([float(st.get(i)) if pd.notna(st.get(i)) else np.nan for i in net.dial])
    stations = np.where(np.isnan(stations), np.nanmedian(stations) if np.isfinite(stations).any() else 12.0, stations)
    zone_pop = np.bincount(cz[reach], weights=pop[reach], minlength=len(net.zone_id))
    return {"T": T[reach], "order": np.argsort(T[reach], axis=1), "cz": cz[reach], "pop": pop[reach],
            "zone_pop": zone_pop, "stations": stations, "patients": stations * PATIENTS_PER_STATION}


def ed_time(cp: dict, care: dict, th: dict, congestion: np.ndarray | None = None, off=frozenset()) -> dict:
    """【中文】每次运行：高峰日每次急诊就诊的平均路程与等待增量（分钟）/ per-run added travel and waiting per ED visit."""
    T, order, cz, pop = cp["T"], cp["order"], cp["cz"], cp["pop"]
    N = len(th["C-H14"])
    nH = T.shape[1]
    Tsorted = np.take_along_axis(T, order, axis=1)
    near = order[:, 0]
    share = pop / pop.sum()
    L0 = np.bincount(near, weights=share, minlength=nH)              # 【中文】日常负荷比例 / normal load share
    out = {k: np.zeros(N) for k in ("travel", "wait", "time", "peak_extra")}
    for r in range(N):
        D0, rho0, W0 = th["C-H15"][r], th["C-H14"][r], th["C-H16"][r]
        o = np.clip(1 - care["hosp_closed_h"][r] / 24.0, 0, 1) if "R17" not in off else np.ones(nH)
        O = o[order]
        stay = np.cumprod(np.c_[np.ones(len(O)), 1 - O[:, :-1]], axis=1)
        wgt = O * stay
        tot = wgt.sum(1, keepdims=True)
        wgt = np.where(tot > 0, wgt / np.maximum(tot, 1e-12), 0.0)
        ez = care["extra_zone"][r]
        extra = ez[cz] * pop / np.maximum(cp["zone_pop"][cz], 1e-9)   # 【中文】分区新增就诊按人口分到网格
        dem = D0 * share + extra
        load = np.bincount(order.ravel(), weights=(wgt * dem[:, None]).ravel(), minlength=nH)
        cap = D0 * L0 / rho0 * o
        rho = np.where(cap > 0, np.minimum(RHO_MAX, load / np.maximum(cap, 1e-12)), RHO_MAX)
        W = W0 * rho / (1 - rho)
        if "R22" in off:                                              # 【中文】需求不增加等待 / demand does not lengthen waiting
            W = np.where(cap > 0, W0 * rho0 / (1 - rho0), W)
        Wk = W[order]
        # 【中文】每位就诊者与自己的正常情况比较（避免新增就诊者的来源构成影响平均值）
        # each visitor is compared with their own normal trip and wait, so the mix of extra visitors does not bias it
        lost = tot[:, 0] <= 0                                        # 【中文】当天没有可去的医院 / no hospital open
        d_trav = np.where(lost, LOST_PENALTY_MIN, (wgt * Tsorted).sum(1) - Tsorted[:, 0])
        d_wait = np.where(lost, 0.0, (wgt * Wk).sum(1) - W0 * rho0 / (1 - rho0))
        out["travel"][r] = (dem * d_trav).sum() / dem.sum()
        out["wait"][r] = (dem * d_wait).sum() / dem.sum()
        out["time"][r] = out["travel"][r] + out["wait"][r]
        out["peak_extra"][r] = extra.sum()
    if congestion is not None:
        out["congestion"] = np.asarray(congestion, float)
        out["time"] = out["time"] + out["congestion"]
    return out


def dialysis_sessions(cp: dict, care: dict) -> np.ndarray:
    """【中文】受影响的透析次数（取消或改到别处）/ dialysis sessions affected (cancelled or moved)."""
    per_hour = cp["patients"] * 3 / 7 / 12
    return (care["dial_closed_op_h"] * per_hour[None, :]).sum(1)
