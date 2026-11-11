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

# 【中文】敲除实验（因果贡献）可关掉的关系，编号同关系图集 R01–R19 / relations that can be switched off
# for the knockout (causal contribution) analysis; ids follow the relation atlas.
KNOCKOUTS = {
    "R02": "load does not respond to temperature (m = 1)",
    "R03a": "hot spot sees each station's period-mean ambient instead of the hourly value",
    "R03b": "hot spot sees each run's period-mean load instead of the hourly load",
    "R04": "no thermal failures (p = 0)",
    "R07": "a failed station returns after one hour",
    "R08": "no upstream propagation: a station is out only if it failed or was shed itself",
    "R09": "water plants never lose power",
    "R10": "no storage buffer: water is lost as soon as every plant stops",
    "R11": "facilities never lose function from a zone outage",
    "R12": "dialysis ignores water loss",
    "R13": "signals never go dark",
    "R18": "homes with AC keep their set point during outages",
    "R19": "indoor equilibrium is not driven by outdoor temperature (held at the AC set point)",
    "R21": "heat exposure does not raise heat-illness visits (k = 0)",
    "R23": "nursing-home residents are not exposed when cooling is lost",
    "R24": "electricity-dependent residents make no visits during outages",
}

# 【中文】骨架模型用到的参数（敏感性分析只看这些）/ parameters used by the core model
CORE_PARAMS = ["C-P1", "C-P1.T0", "C-P1.Kd", "C-P1.Td", "C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m",
               "C-P2.tau", "C-P3", "C-P3.sigma", "C-P6", "C-P9.avail", "C-P9.imp", "C-H1", "C-H2", "C-W2", "C-W3",
               "C-T2", "C-T5", "C-B1", "C-B2", "C-B3", "C-B4", "C-H10",
               "C-H11", "C-H11.a", "C-H12", "C-H13", "C-H14", "C-H15", "C-H16", "C-H17"]


def simulate_core(net: Network, Ta_c: np.ndarray, th: dict, rng: np.random.Generator, day_mask: np.ndarray,
                  Ta_sub: np.ndarray | None = None, Ta_zone: np.ndarray | None = None,
                  shed: np.ndarray | None = None, off: frozenset = frozenset(), lineb: dict | None = None) -> dict:
    """【中文】主循环。Ta_c (H,)：BNA 逐小时气温；Ta_sub (H, S) / Ta_zone (H, Z)：本地气温（K1），不给时用 Ta_c；
    day_mask (H,)：当地 08:00–20:00 为 True（K9 白天得热）；shed (N, H)：系统缺口造成的轮流停电比例（K4）。

    Main loop. day_mask marks local 08:00–20:00 (daytime gains in K9); shed is the rotating-outage share (K4).
    off: relation ids from KNOCKOUTS to switch off (R01, R05, R06, R14–R17, R22 are switched in pipeline.core).
    lineb: line B inputs {"nh_res": residents per nursing home, "zone_dep": electricity-dependent residents per zone,
    "day": day index per hour}; without it the line B outputs stay zero."""
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
    rep = np.ones((N, 1), int) if "R07" in off else np.round(th["C-P6"]).astype(int)[:, None]
    mTd = 1 + beta * np.maximum(0, Td - T0)
    repair = np.zeros((N, S), dtype=int)
    dTO = None
    # 【中文】R03a / R03b 敲除：用整段时期的平均环境气温或平均负荷倍数 / period means for R03a / R03b
    Ta_mean = Ta_sub.mean(0)[None, :]
    m_mean = None
    if "R03b" in off:
        m_mean = 1 + beta * np.stack([np.maximum(0, TF[:, s_] - T0).mean(1) for s_ in range(S)], axis=1)

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

    # B 线第一版：养老院住户暴露、依赖电力设备的居民、热病症就诊 / line B v1
    lb = lineb is not None
    if lb:
        nh_res = np.asarray(lineb["nh_res"], float)[None, :]
        zone_dep = np.asarray(lineb["zone_dep"], float)[None, :]
        dayi = np.asarray(lineb["day"], int)
        extra_day = np.zeros((N, int(dayi.max()) + 1))
        hosp_day = np.zeros_like(extra_day)                 # 【中文】每天医院停电的小时数 / hospital-hours closed per day
        k_heat = np.zeros((N, 1)) if "R21" in off else col("C-H11")
        hb, q, T_nh = np.maximum(col("C-H12"), 1.0), col("C-H13"), col("C-H17")
        Tin_nh = np.repeat(T_set, len(ns), axis=1)
        age = np.zeros((N, Z))

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
                                    "indoor_outage_poverty_hours", "indoor_no_ac_pop_hours", "nh_exposed_hours",
                                    "dep_visits", "heat_visits_excess")}

    for h in range(H):
        # K2：负荷倍数与标幺负荷（无负荷转移）/ load multiplier and per-unit load (no transfer)
        m = np.ones_like(beta) if "R02" in off else 1 + beta * np.maximum(0, TF[h] - T0)
        K = Kd * (m_mean if "R03b" in off else m) / mTd
        # K3：顶油温升一阶滞后 + 热点温度 → 热失效 / top-oil lag, hot spot and thermal failure
        dTOU = dTOR * ((K ** 2 * R + 1) / (R + 1)) ** n_
        dTO = dTOU if dTO is None else dTO + (dTOU - dTO) * (1 - np.exp(-1.0 / tau))
        thetaH = (Ta_mean if "R03a" in off else Ta_sub[h][None, :]) + dTO + dHR * K ** (2 * m_)
        p = np.zeros_like(thetaH) if "R04" in off else ndtr((thetaH - th50) / sig)
        failed = repair > 0
        new_t = ~failed & (rng.random((N, S)) < p)
        repair = np.where(new_t, rep, repair)
        failed |= new_t
        tot["thermal"] += new_t.sum(1)

        # K4：系统缺口 → 按比例轮流切除供电站 / rotating outages from a system shortfall
        # 【中文】每小时都抽一次随机数，保证敲除实验之间的公共随机数对齐 / always drawn, so knockouts share random numbers
        u_shed = rng.random((N, S))
        shed_now = (u_shed < shed[:, h][:, None]) & serving[None, :] if shed is not None else np.zeros((N, S), bool)

        # K5：供电依赖，自上而下传播到不动点 / supply dependency to a fixed point
        up = ~failed & ~shed_now
        for _ in range(0 if "R08" in off else S):
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

        fac_down = np.zeros_like(down) if "R11" in off else down
        hl, B_h, prev_h = backed(fac_down[:, hs], B_h, prev_h, p_bh)
        nl, B_n, prev_n = backed(fac_down[:, ns], B_n, prev_n, p_bn)
        wl, B_w, prev_w = backed((np.zeros_like(down) if "R09" in off else down)[:, ps], B_w, prev_w, p_bw)
        prod_lost = wl.all(1, keepdims=True) if len(ps) else np.zeros((N, 1), bool)
        storage_left = np.where(prod_lost, storage_left - 1, col("C-W3"))
        water_out = prod_lost & (storage_left < 0) if (net.has_storage and "R10" not in off) else prod_lost
        dl = fac_down[:, ds] | (False if "R12" in off else water_out)
        # K8：信号灯熄灭 → 所控路段降级（供 pipeline.access 使用）/ dark signals → degraded segments
        dark = down[:, gs] & no_batt & ("R13" not in off)
        deg = (dark.astype(float) @ net.M_sig_road) > 0

        out["hosp"][h] = hl.mean(0); out["nurs"][h] = nl.mean(0); out["dial"][h] = dl.mean(0)
        out["water_out"][h] = water_out.mean(); out["signals_dark"][h] = dark.sum(1).mean()
        out["roads_degraded"][h] = deg.sum(1).mean(); out["roads_p"][h] = deg.mean(0)
        tot["hospital_hours"] += hl.sum(1); tot["nursing_hours"] += nl.sum(1); tot["dialysis_hours"] += dl.sum(1)
        tot["water_out_hours"] += water_out[:, 0]; tot["signal_dark_hours"] += dark.sum(1)
        # 【中文】最坏小时：降级路段数 + 关闭的医院与透析中心（每家记 500，使有设施关闭的小时优先）
        # worst hour: degraded segments plus closed hospitals and dialysis centres (500 each, so closures come first)
        nd = deg.sum(1) + 500 * (hl.sum(1) + dl.sum(1))
        better = nd > worst_n
        if better.any():
            worst_h[better], worst_n[better] = h, nd[better]
            snap_deg[better], snap_h[better], snap_d[better] = deg[better], hl[better], dl[better]

        # K9：室内温度 T_in = T_eq + (T_in − T_eq)·e^(−1/τ_b)，T_eq = θ_A + 得热温升 / indoor RC step
        Teq = np.repeat(T_set, Z, axis=1) if "R19" in off else Ta_zone[h][None, :] + np.where(day_mask[h], gain, 1.0)
        Tin_no = Teq if Tin_no is None else Teq + (Tin_no - Teq) * decay
        Tin_ac = np.where(zdown & ("R18" not in off), Teq + (Tin_ac - Teq) * decay, T_set)
        hot_ac = zdown & (Tin_ac >= T_thr)                 # 【中文】有空调住户只在停电时可能超阈值
        hot_no = Tin_no >= T_thr
        e_out = f_ac * hot_ac
        tot["ac_loss_pop_hours"] += f_ac[:, 0] * po
        tot["indoor_outage_pop_hours"] += (e_out * pop).sum(1)
        tot["indoor_outage_elderly_hours"] += (e_out * eld).sum(1)
        tot["indoor_outage_poverty_hours"] += (e_out * pov).sum(1)
        tot["indoor_no_ac_pop_hours"] += ((1 - f_ac) * hot_no * pop).sum(1)
        out["indoor_out_pop"][h] = (e_out * pop).sum(1).mean()
        if lb:
            # 【中文】养老院：失去制冷后按同一热响应升温，超过老年人阈值的住户·小时 / nursing homes losing cooling
            Teq_nh = Ta_sub[h][ns][None, :] + np.where(day_mask[h], gain, 1.0)
            Tin_nh = np.where(nl & ("R23" not in off), Teq_nh + (Tin_nh - Teq_nh) * decay, T_set)
            nh_exp = ((nl & (Tin_nh >= T_nh)) * nh_res).sum(1)
            # 【中文】依赖电力设备的居民：停电持续到电池耗尽时，以概率 q 就医（每次停电一次）/ device users
            age_prev = age
            age = np.where(zdown, age + 1, 0)
            hit = zdown & (age_prev < hb) & (age >= hb)
            dep = np.zeros(N) if "R24" in off else (hit * zone_dep).sum(1) * q[:, 0]
            # 【中文】热病症就诊的超额部分 = k × 当小时高温暴露人·小时 / excess heat-illness visits
            expo = (e_out * pop).sum(1) + ((1 - f_ac) * hot_no * pop).sum(1) + nh_exp
            heat = k_heat[:, 0] * expo
            extra_day[:, dayi[h]] += heat + dep
            hosp_day[:, dayi[h]] += hl.sum(1)
            tot["nh_exposed_hours"] += nh_exp; tot["dep_visits"] += dep; tot["heat_visits_excess"] += heat
        out["indoor_ac_max_c"][h] = Tin_ac[zdown].max() if zdown.any() else np.nan
        repair = np.maximum(repair - 1, 0)

    tot["indoor_pop_hours"] = tot["indoor_outage_pop_hours"] + tot["indoor_no_ac_pop_hours"]
    if lb:
        pk = extra_day.argmax(1)
        tot["peak_day_extra_visits"] = extra_day[np.arange(N), pk]
        # 【中文】高峰日医院的平均可用比例（停电小时数折算）/ average open share of hospitals on the peak day
        tot["peak_day_open_share"] = 1 - hosp_day[np.arange(N), pk] / (24 * max(len(hs), 1))
        tot["mean_day_extra_visits"] = extra_day.mean(1)
    return {"hourly": out, "pop_out": pop_out, "totals": tot,
            "worst": {"hour": worst_h, "roads": snap_deg, "hosp": snap_h, "dial": snap_d}}
