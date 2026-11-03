"""
【中文】精简主线模型（骨架）。只保留文献中证据最强的一条链，见 docs/CORE_MODEL.md 和 twin/core.yaml：

    K1  城市气温场 θ_A(x,t)                                  M-6
    K2  气温 → 负荷倍数 → 标幺负荷 K                         Eq. 2–3   C-P1
    K3  IEEE C57.91 热点温度 → 热失效                         Eq. 4–7   C-P2, C-P3
    K4  系统供需缺口 → 轮流停电                               M-18（只含负荷侧）C-P9.avail, C-P9.imp
    K5  供电依赖（拓扑）→ 分区停电；固定修复时长              Eq. 9–10  C-P5, C-P6
    K6  分区停电 → 水厂（备用）→ 储水耗尽 → 断水              Eq. 13    C-W2, C-W3
    K7  分区停电 → 医院 / 养老院（备用）、透析（电 ∨ 水）     Eq. 11    C-H1, C-H2, C-H3
    K8  分区停电 → 信号灯熄灭 → 路段通行能力下降 → 到医院 / 透析 / 急救站的行程时间
                                                              Eq. 11, 16, M-28, M-29  C-T2, C-T3, C-T5, C-T6.*
        （本函数记录每次运行降级路段最多的小时的状态；行程时间由 pipeline.core 调用 pipeline.access 计算）
    K9  停电 → 失去空调 → 室内温度（一阶 RC）→ 室内高温暴露    M-32, M-33 C-B1–B4, C-H10

与完整模型（pipeline/twin/cascade.py）相比去掉：同电压站之间的负荷转移与过载跳闸（C-P4，Motter–Lai）、
河温降额（M-18 供给侧）、路面模块（Eq. 15）、室外复合暴露阈值（C-POP2，由 K9 取代）。
K8 的可达性按每次运行的实际状态计算，而不是完整模型中的期望通行能力。

Core (skeleton) model: the main chain only. Compared with the full model it drops peer load transfer and
overload trips (C-P4), river derating, the pavement module and the outdoor compound threshold (replaced by K9).
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtr

from .cascade import Network, c_to_f

# 【中文】骨架模型用到的参数（敏感性分析只看这些）/ parameters used by the core model
CORE_PARAMS = ["C-P1", "C-P1.T0", "C-P1.Kd", "C-P1.Td", "C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m",
               "C-P2.tau", "C-P3", "C-P3.sigma", "C-P6", "C-P9.avail", "C-P9.imp", "C-H1", "C-H2", "C-W2", "C-W3",
               "C-T2", "C-T5", "C-B1", "C-B2", "C-B3", "C-B4", "C-H10"]


def simulate_core(net: Network, Ta_c: np.ndarray, th: dict, rng: np.random.Generator, day_mask: np.ndarray,
                  Ta_sub: np.ndarray | None = None, Ta_zone: np.ndarray | None = None,
                  shed: np.ndarray | None = None) -> dict:
    """【中文】主循环。Ta_c (H,)：BNA 逐小时气温；Ta_sub (H, S) / Ta_zone (H, Z)：本地气温（K1），不给时用 Ta_c；
    day_mask (H,)：当地 08:00–20:00 为 True（K9 白天得热）；shed (N, H)：系统缺口造成的轮流停电比例（K4）。

    Main loop. day_mask marks local 08:00–20:00 (daytime gains in K9); shed is the rotating-outage share (K4)."""
    N, S, H, Z = len(th["C-P1"]), len(net.sid), len(Ta_c), len(net.zone_id)
    col = lambda k: th[k][:, None]  # noqa: E731
    Ta_sub = np.repeat(np.asarray(Ta_c, float)[:, None], S, axis=1) if Ta_sub is None else np.asarray(Ta_sub, float)
    Ta_zone = np.repeat(np.asarray(Ta_c, float)[:, None], Z, axis=1) if Ta_zone is None else np.asarray(Ta_zone, float)
    TF = c_to_f(Ta_sub)
    serving = net.subs["serving"].to_numpy()

    # K2–K3 参数 / load and transformer parameters
    beta, T0, Kd, Td = col("C-P1"), col("C-P1.T0"), col("C-P1.Kd"), col("C-P1.Td")
    dTOR, dHR, R, n_, m_, tau = (col(k) for k in ("C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m", "C-P2.tau"))
    th50, sig = col("C-P3"), col("C-P3.sigma")
    rep = np.round(th["C-P6"]).astype(int)[:, None]
    mTd = 1 + beta * np.maximum(0, Td - T0)
    repair = np.zeros((N, S), dtype=int)
    dTO = None

    # K6–K8 下游资产 / downstream assets
    hs, ns, ds = net.sub_of(net.hosp), net.sub_of(net.nurs), net.sub_of(net.dial)
    ps, gs = net.sub_of(net.plants), net.sub_of(net.signals)
    p_bh, p_bn, p_bw = col("C-H1"), col("C-H2"), col("C-W2")
    no_batt = rng.random((N, len(gs))) < col("C-T2")
    B_h = np.zeros((N, len(hs)), bool); B_n = np.zeros((N, len(ns)), bool); B_w = np.zeros((N, len(ps)), bool)
    prev_h = np.zeros_like(B_h); prev_n = np.zeros_like(B_n); prev_w = np.zeros_like(B_w)
    storage_left = col("C-W3").astype(float)

    # K9 室内温度：有空调住户（停电时自由升温）与无空调住户（始终自由升温）/ indoor temperature
    tau_b, gain, T_set, f_ac, T_thr = col("C-B1"), col("C-B2"), col("C-B3"), col("C-B4"), col("C-H10")
    decay = np.exp(-1.0 / tau_b)
    Tin_ac = np.repeat(T_set, Z, axis=1)                       # 【中文】起始：空调设定温度 / start at set point
    Tin_no = None
    zs = net.zone_sub
    pop, eld, pov = net.zone_pop[None, :], net.zone_eld[None, :], net.zone_pov[None, :]

    out = {k: np.zeros((H, S)) for k in ("p_down", "p_thermal", "theta_h")}
    for k, w in (("hosp", len(hs)), ("nurs", len(ns)), ("dial", len(ds)), ("water_out", 1), ("signals_dark", 1),
                 ("roads_degraded", 1), ("n_down", 1), ("roads_p", len(net.roads)), ("indoor_out_pop", 1),
                 ("indoor_ac_max_c", 1)):
        out[k] = np.zeros((H, w))
    pop_out = np.zeros((N, H))
    # 【中文】K8：每次运行降级路段最多的小时（−1 = 从未降级）及该小时的路段与设施状态
    # K8: per run, the hour with the most degraded segments and the state at that hour
    worst_h, worst_n = np.full(N, -1), np.zeros(N)
    snap_deg = np.zeros((N, len(net.roads)), bool)
    snap_h, snap_d = np.zeros((N, len(hs)), bool), np.zeros((N, len(ds)), bool)
    tot = {k: np.zeros(N) for k in ("thermal", "deenergised_hours", "pop_hours", "shed_station_hours", "hospital_hours",
                                    "nursing_hours", "dialysis_hours", "water_out_hours", "signal_dark_hours",
                                    "max_subs_down", "ac_loss_pop_hours", "indoor_pop_hours",
                                    "indoor_outage_pop_hours", "indoor_outage_elderly_hours",
                                    "indoor_outage_poverty_hours", "indoor_no_ac_pop_hours")}

    for h in range(H):
        # K2：负荷倍数与标幺负荷（无负荷转移）/ load multiplier and per-unit load (no transfer)
        m = 1 + beta * np.maximum(0, TF[h] - T0)
        K = Kd * m / mTd
        # K3：顶油温升一阶滞后 + 热点温度 → 热失效 / top-oil lag, hot spot and thermal failure
        dTOU = dTOR * ((K ** 2 * R + 1) / (R + 1)) ** n_
        dTO = dTOU if dTO is None else dTO + (dTOU - dTO) * (1 - np.exp(-1.0 / tau))
        thetaH = Ta_sub[h][None, :] + dTO + dHR * K ** (2 * m_)
        p = ndtr((thetaH - th50) / sig)
        failed = repair > 0
        new_t = ~failed & (rng.random((N, S)) < p)
        repair = np.where(new_t, rep, repair)
        failed |= new_t
        tot["thermal"] += new_t.sum(1)

        # K4：系统缺口 → 按比例轮流切除供电站 / rotating outages from a system shortfall
        shed_now = np.zeros((N, S), bool)
        if shed is not None and np.any(shed[:, h] > 0):
            shed_now = (rng.random((N, S)) < shed[:, h][:, None]) & serving[None, :]

        # K5：供电依赖，自上而下传播到不动点 / supply dependency to a fixed point
        up = ~failed & ~shed_now
        for _ in range(S):
            nxt = up & (~net.has_supply[None, :] | ((up.astype(float) @ net.U) > 0))
            if (nxt == up).all():
                break
            up = nxt
        down = ~up

        out["p_down"][h] = down.mean(0)
        out["p_thermal"][h] = p.mean(0)
        out["theta_h"][h] = thetaH.mean(0)
        out["n_down"][h] = down.sum(1).mean()
        tot["deenergised_hours"] += (down & ~failed).sum(1)
        tot["max_subs_down"] = np.maximum(tot["max_subs_down"], down.sum(1))
        tot["shed_station_hours"] += shed_now.sum(1)
        zdown = np.where(zs[None, :] >= 0, down[:, np.maximum(zs, 0)], False)
        po = zdown.astype(float) @ net.zone_pop
        pop_out[:, h] = po
        tot["pop_hours"] += po

        # K6–K7：设施备用电源（每次停电开始时抽样）与供水 / backup draws and water
        def backed(src_down, B, prev, pb):
            start = src_down & ~prev
            B = np.where(start, rng.random(B.shape) < pb, B)
            return src_down & B, B, src_down

        hl, B_h, prev_h = backed(down[:, hs], B_h, prev_h, p_bh)
        nl, B_n, prev_n = backed(down[:, ns], B_n, prev_n, p_bn)
        wl, B_w, prev_w = backed(down[:, ps], B_w, prev_w, p_bw)
        prod_lost = wl.all(1, keepdims=True) if len(ps) else np.zeros((N, 1), bool)
        storage_left = np.where(prod_lost, storage_left - 1, col("C-W3"))
        water_out = prod_lost & (storage_left < 0) if net.has_storage else prod_lost
        dl = down[:, ds] | water_out
        # K8：信号灯熄灭 → 所控路段降级（供 pipeline.access 使用）/ dark signals → degraded segments
        dark = down[:, gs] & no_batt
        deg = (dark.astype(float) @ net.M_sig_road) > 0

        out["hosp"][h] = hl.mean(0); out["nurs"][h] = nl.mean(0); out["dial"][h] = dl.mean(0)
        out["water_out"][h] = water_out.mean(); out["signals_dark"][h] = dark.sum(1).mean()
        out["roads_degraded"][h] = deg.sum(1).mean(); out["roads_p"][h] = deg.mean(0)
        tot["hospital_hours"] += hl.sum(1); tot["nursing_hours"] += nl.sum(1); tot["dialysis_hours"] += dl.sum(1)
        tot["water_out_hours"] += water_out[:, 0]; tot["signal_dark_hours"] += dark.sum(1)
        nd = deg.sum(1)
        better = nd > worst_n
        if better.any():
            worst_h[better], worst_n[better] = h, nd[better]
            snap_deg[better], snap_h[better], snap_d[better] = deg[better], hl[better], dl[better]

        # K9：室内温度 T_in = T_eq + (T_in − T_eq)·e^(−1/τ_b)，T_eq = θ_A + 得热温升 / indoor RC step
        Teq = Ta_zone[h][None, :] + np.where(day_mask[h], gain, 1.0)
        Tin_no = Teq if Tin_no is None else Teq + (Tin_no - Teq) * decay
        Tin_ac = np.where(zdown, Teq + (Tin_ac - Teq) * decay, T_set)
        hot_ac = zdown & (Tin_ac >= T_thr)                 # 【中文】有空调住户只在停电时可能超阈值
        hot_no = Tin_no >= T_thr
        e_out = f_ac * hot_ac
        tot["ac_loss_pop_hours"] += f_ac[:, 0] * po
        tot["indoor_outage_pop_hours"] += (e_out * pop).sum(1)
        tot["indoor_outage_elderly_hours"] += (e_out * eld).sum(1)
        tot["indoor_outage_poverty_hours"] += (e_out * pov).sum(1)
        tot["indoor_no_ac_pop_hours"] += ((1 - f_ac) * hot_no * pop).sum(1)
        out["indoor_out_pop"][h] = (e_out * pop).sum(1).mean()
        out["indoor_ac_max_c"][h] = Tin_ac[zdown].max() if zdown.any() else np.nan
        repair = np.maximum(repair - 1, 0)

    tot["indoor_pop_hours"] = tot["indoor_outage_pop_hours"] + tot["indoor_no_ac_pop_hours"]
    return {"hourly": out, "pop_out": pop_out, "totals": tot,
            "worst": {"hour": worst_h, "roads": snap_deg, "hosp": snap_h, "dial": snap_d}}
