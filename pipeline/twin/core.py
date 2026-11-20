"""
【中文】精简主线模型（骨架）。只保留文献中证据最强的一条链，见 docs/CORE_MODEL.md 和 twin/core.yaml：

    K1  城市气温场 θ_A(x,t)（背景气候与城市基础信息只作输入）  M-6
    K2  本地气温 → 制冷负荷；基础负荷不随气温（2026-11-20 拆分）  Eq. 2–3   C-P1
    K3  基础负荷 + 制冷负荷 → IEEE C57.91 热点温度 → 热失效    Eq. 4–7   C-P2, C-P3
    K5  失效的变电站 → 它自己供电的分区停电；固定修复时长（2026-11-20 起不沿拓扑传播，供电依赖暂缓 D13）
                                                              Eq. 10    C-P6
    K6  分区停电 → 水厂（备用）→ 储水耗尽 → 断水              Eq. 13    C-W2, C-W3
    K7  医院：分区停电且备用电源失效，或断水超过院内储水时长（2026-11-17 起医疗设施只保留医院）
                                                              Eq. 11    C-H1, C-H18
    K8  分区停电 → 信号灯熄灭 → 路段通行能力下降 → 到医院的行程时间
                                                              Eq. 11, 16, M-28, M-29  C-T2, C-T3, C-T5, C-T6.*
        （本函数记录每次运行降级路段最多的小时的状态；行程时间由 pipeline.core 调用 pipeline.access 计算）
    K9  停电 → 失去空调 → 室内温度（一阶 RC）→ 室内高温暴露    M-32, M-33 C-B1–B4, C-H10
    K10 B 线：高温暴露 → 热病症 → 就医需求；分区停电 → 呼吸机等设备用户 → 就医需求  M-47  C-H11–C-H16

与完整模型（pipeline/twin/cascade.py）相比去掉：同电压站之间的负荷转移与过载跳闸（C-P4，Motter–Lai）、
河温降额（M-18 供给侧）、路面模块（Eq. 15）、室外复合暴露阈值（C-POP2，由 K9 取代）。
K8 的可达性按每次运行的实际状态计算，而不是完整模型中的期望通行能力。
2026-11-20：用电负荷拆成基础负荷与制冷负荷，仍驱动 IEEE 热点模型（power="load"，默认）；power="fragility" 是同日做过对比的
两参数气温脆弱性曲线（M-48，CORE_MODEL §4.7）。系统缺口（原 K4）暂缓为 D12，只在 pipeline.core --shortfall 时计算；
供电依赖（沿拓扑向下游传播）暂缓为 D13，supply_dependency=True 时恢复。车辙 → 行程时间（K11）在 pipeline.core 中计算。

Core (skeleton) model: the main chain only. Compared with the full model it drops peer load transfer and
overload trips (C-P4), river derating, the pavement module and the outdoor compound threshold (replaced by K9).
Since 2026-11-20: load is split into base and cooling load, still driving the IEEE hot spot (power="load", default);
power="fragility" is the two-parameter air-temperature fragility compared that day. The system shortfall (D12) and
supply dependency along the topology (D13) are deferred; rutting → travel time (K11) is computed in pipeline.core.
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtr

from .cascade import Network, c_to_f

# 【中文】敲除实验（因果贡献）可关掉的关系，编号同关系图集 / relations that can be switched off
# for the knockout (causal contribution) analysis; ids follow the relation atlas.
KNOCKOUTS = {
    "R02": "cooling load does not respond to temperature (load = base load)",
    "R03a": "hot spot sees each station's period-mean ambient instead of the hourly value",
    "R03b": "hot spot sees each run's period-mean cooling load instead of the hourly load",
    "R04": "no thermal failures (p = 0)",
    "R07": "a failed station returns after one hour",
    "R09": "water plants never lose power",
    "R10": "no storage buffer: water is lost as soon as every plant stops",
    "R11": "hospitals never lose function from a zone outage",
    "R12": "hospitals ignore water loss",
    "R13": "signals never go dark",
    "R18": "homes with AC keep their set point during outages",
    "R19": "indoor equilibrium is not driven by outdoor temperature (held at the AC set point)",
    "R21": "heat exposure does not raise heat-illness visits (k = 0)",
    "R24": "ventilator and other device users make no visits during outages",
}
# 【中文】只在 power="fragility" 时有意义的敲除 / knockout that only applies with power="fragility"
FRAGILITY_KNOCKOUTS = {"R03": "heat stress sees each station's period-mean temperature instead of the hourly value"}

# 【中文】骨架模型用到的参数（敏感性分析只看这些）；车辙 C-T8、C-T11、C-T12 由 pipeline.core 使用
# parameters used by the core model; rutting C-T8, C-T11, C-T12 are used in pipeline.core
LOAD_PARAMS = ["C-P1", "C-P1.T0", "C-P1.Kd", "C-P1.Td", "C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m",
               "C-P2.tau", "C-P3", "C-P3.sigma"]
FRAGILITY_PARAMS = ["C-P11", "C-P11.sigma", "C-P11.tau", "C-P11.w"]
SHORTFALL_PARAMS = ["C-P9.avail", "C-P9.imp"]
CORE_PARAMS = LOAD_PARAMS + ["C-P6", "C-H1", "C-H18", "C-W2", "C-W3",
                             "C-T2", "C-T5", "C-T8", "C-T11", "C-T12", "C-B1", "C-B2", "C-B3", "C-B4", "C-H10",
                             "C-H11", "C-H11.a", "C-H12", "C-H13", "C-H14", "C-H15", "C-H16"]
IEEE_PARAMS = LOAD_PARAMS + SHORTFALL_PARAMS          # 【中文】兼容旧名 / former name

# 【中文】C-P11 的取值范围由下面的换算得到：把负荷与热点参数的三角分布换算成 T50、σ_T、w（2026-11-19 对比试验，
# 2,000 次运行中两种做法的就医时间逐次相关 0.99），见 docs/CORE_MODEL.md §4.7。
# The C-P11 ranges come from this mapping of the load and hot-spot draws (2026-11-19 comparison, CORE_MODEL §4.7).
FRAGILITY_ANCHOR = 2.33   # 【中文】Φ(−2.33) ≈ 1% / anchor of the tail linearisation


def _hot_spot_ss(T_c, th: dict, part: str = "all"):
    """【中文】稳态热点温度（K2–K3，所有站同一组参数）作为本地气温的函数；part="oil" 只取有滞后的顶油温升部分。
    Steady-state hot spot vs local air temperature; part="oil" returns only the lagged top-oil rise."""
    beta, T0, Kd, Td = (th[k][:, None] for k in ("C-P1", "C-P1.T0", "C-P1.Kd", "C-P1.Td"))
    dTOR, dHR, R, n_, m_ = (th[k][:, None] for k in ("C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m"))
    K = Kd * (1 + beta * np.maximum(0, c_to_f(T_c) - T0)) / (1 + beta * np.maximum(0, Td - T0))
    oil = dTOR * ((K ** 2 * R + 1) / (R + 1)) ** n_
    return oil if part == "oil" else T_c + oil + dHR * K ** (2 * m_)


def fragility_from_ieee(th: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """【中文】把 K2–K3 的参数换算成气温脆弱性曲线 p = Φ((T_eff − T50)/σ_T)：T50 是稳态热点温度达到 θ50 时的本地气温，
    σ_T = σ / (该处热点温度对气温的斜率)；w 是斜率中有滞后的顶油部分所占比例，
    T_eff = (1 − w)·当前气温 + w·按顶油时间常数滞后的气温。每次运行一组值，形状 (N, 1)。

    Maps the K2–K3 draws to an air-temperature fragility: T50 is the local air temperature at which the steady-state
    hot spot reaches theta_50, sigma_T = sigma divided by the hot spot's slope there, and w is the lagged (top-oil)
    share of that slope, so T_eff = (1 - w) T(t) + w EMA_tau(T)."""
    th50, sig = th["C-P3"][:, None], th["C-P3.sigma"][:, None]
    # 【中文】在曲线下尾（热点温度 = θ50 − ANCHOR·σ，每小时失效概率约 1%）做线性化，因为失效几乎都发生在这一段
    # linearise in the lower tail (hot spot = theta_50 - ANCHOR sigma), where almost all failures occur
    target = th50 - FRAGILITY_ANCHOR * sig
    lo, hi = np.full_like(th50, -20.0), np.full_like(th50, 120.0)
    for _ in range(60):                                   # 【中文】二分法 / bisection (hot spot rises with temperature)
        mid = (lo + hi) / 2
        above = _hot_spot_ss(mid, th) >= target
        hi, lo = np.where(above, mid, hi), np.where(above, lo, mid)
    Ta_ = (lo + hi) / 2
    d = lambda part: (_hot_spot_ss(Ta_ + 0.05, th, part) - _hot_spot_ss(Ta_ - 0.05, th, part)) / 0.1  # noqa: E731
    slope = np.maximum(d("all"), 1e-6)
    sigT = sig / slope
    return Ta_ + FRAGILITY_ANCHOR * sigT, sigT, np.clip(d("oil") / slope, 0, 1)


def simulate_core(net: Network, Ta_c: np.ndarray, th: dict, rng: np.random.Generator, day_mask: np.ndarray,
                  Ta_sub: np.ndarray | None = None, Ta_zone: np.ndarray | None = None,
                  shed: np.ndarray | None = None, off: frozenset = frozenset(), lineb: dict | None = None,
                  power: str = "load", supply_dependency: bool = False) -> dict:
    """【中文】主循环。Ta_c (H,)：BNA 逐小时气温；Ta_sub (H, S) / Ta_zone (H, Z)：本地气温（K1），不给时用 Ta_c；
    day_mask (H,)：当地 08:00–20:00 为 True（K9 白天得热）；shed (N, H)：系统缺口造成的轮流停电比例（K4）。

    Main loop. day_mask marks local 08:00–20:00 (daytime gains in K9); shed is the rotating-outage share (K4).
    off: relation ids from KNOCKOUTS to switch off (R01, R14–R17, R22, R27 are switched in pipeline.core).
    power: "load" (base + cooling load → IEEE hot spot; "ieee" is accepted as the former name) or "fragility" (M-48).
    supply_dependency: propagate outages down the supply topology (deferred D13 since 2026-11-20).
    lineb: line B inputs {"zone_dep": device users (ventilators and other electricity-dependent equipment) per zone,
    "day": day index per hour}; without it the line B outputs stay zero. With lineb the result also carries "care":
    peak-day extra visits per zone (heat illness and device users separately) and hospital hours closed that day
    (power and water separately), used by pipeline.care."""
    N, S, H, Z = len(th["C-P6"]), len(net.sid), len(Ta_c), len(net.zone_id)
    power = "load" if power == "ieee" else power
    col = lambda k: th[k][:, None]  # noqa: E731
    Ta_sub = np.repeat(np.asarray(Ta_c, float)[:, None], S, axis=1) if Ta_sub is None else np.asarray(Ta_sub, float)
    Ta_zone = np.repeat(np.asarray(Ta_c, float)[:, None], Z, axis=1) if Ta_zone is None else np.asarray(Ta_zone, float)
    serving = net.subs["serving"].to_numpy()

    rep = np.ones((N, 1), int) if "R07" in off else np.round(th["C-P6"]).astype(int)[:, None]
    repair = np.zeros((N, S), dtype=int)
    Ta_mean = Ta_sub.mean(0)[None, :]          # 【中文】R03 / R03a 敲除：整段时期的平均气温 / period-mean temperature
    if power == "fragility":
        # 【中文】K3（2026-11-20）：热应力 T_eff = (1 − w)·当前本地气温 + w·按时间常数 τ 滞后的本地气温，
        # 每小时失效概率 p = Φ((T_eff − T50)/σ_T)
        # K3 (2026-11-20): heat stress T_eff mixes the current and lagged local temperature; p = Φ((T_eff − T50)/σ_T)
        T50, sigT, w_lag, tau = col("C-P11"), col("C-P11.sigma"), col("C-P11.w"), col("C-P11.tau")
        T_lag = None
    elif power == "load":
        # 【中文】K2–K3：负荷 = 基础负荷（1）+ 制冷负荷 β·max(0, T − T0)，以设计温度 Td 时的总负荷归一为 K_design；
        # 再进 IEEE C57.91 热点模型。基础负荷在设计日所占比例为 1 / m(Td)。
        # K2–K3: load = base (1) + cooling beta max(0, T - T0), normalised to K_design at Td, then the IEEE hot spot
        TF = c_to_f(Ta_sub)
        beta, T0, Kd, Td = col("C-P1"), col("C-P1.T0"), col("C-P1.Kd"), col("C-P1.Td")
        dTOR, dHR, R, n_, m_, tau = (col(k) for k in ("C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m", "C-P2.tau"))
        th50, sig = col("C-P3"), col("C-P3.sigma")
        mTd = 1 + beta * np.maximum(0, Td - T0)
        dTO = None
        m_mean = None
        if "R03b" in off:
            m_mean = 1 + beta * np.stack([np.maximum(0, TF[:, s_] - T0).mean(1) for s_ in range(S)], axis=1)
    else:
        raise ValueError(f"power must be 'load' or 'fragility', not {power!r}")

    # K6–K8 下游资产 / downstream assets
    hs = net.sub_of(net.hosp)
    ps, gs = net.sub_of(net.plants), net.sub_of(net.signals)
    p_bh, p_bw = col("C-H1"), col("C-W2")
    no_batt = rng.random((N, len(gs))) < col("C-T2")
    B_h = np.zeros((N, len(hs)), bool); B_w = np.zeros((N, len(ps)), bool)
    prev_h = np.zeros_like(B_h); prev_w = np.zeros_like(B_w)
    storage_left = col("C-W3").astype(float)
    h_water = col("C-H18")                                  # 【中文】医院院内储水可维持的小时数 / hospital on-site water hours
    water_age = np.zeros((N, 1))

    # K9 室内温度：有空调住户（停电时自由升温）与无空调住户（始终自由升温）/ indoor temperature
    tau_b, gain, T_set, f_ac, T_thr = col("C-B1"), col("C-B2"), col("C-B3"), col("C-B4"), col("C-H10")
    decay = np.exp(-1.0 / tau_b)
    Tin_ac = np.repeat(T_set, Z, axis=1)                       # 【中文】起始：空调设定温度 / start at set point
    Tin_no = None
    zs = net.zone_sub
    pop, eld, pov = net.zone_pop[None, :], net.zone_eld[None, :], net.zone_pov[None, :]

    # B 线：热病症就诊、呼吸机等设备用户的就诊 / line B: heat illness and device users
    lb = lineb is not None
    if lb:
        zone_dep = np.asarray(lineb["zone_dep"], float)[None, :]
        dayi = np.asarray(lineb["day"], int)
        D_ = int(dayi.max()) + 1
        extra_day = np.zeros((N, D_))
        heat_zd = np.zeros((N, D_, Z), dtype=np.float32)     # 【中文】每天各分区热病症新增就诊 / heat-illness visits per day, zone
        dep_zd = np.zeros((N, D_, Z), dtype=np.float32)      # 【中文】每天各分区设备用户就诊 / device-user visits per day, zone
        hosp_pd = np.zeros((N, D_, len(hs)), dtype=np.float32)  # 【中文】每天各医院因停电关闭的小时 / closed by power
        hosp_wd = np.zeros((N, D_, len(hs)), dtype=np.float32)  # 【中文】每天各医院只因断水关闭的小时 / closed by water only
        k_heat = np.zeros((N, 1)) if "R21" in off else col("C-H11")
        hb, q = np.maximum(col("C-H12"), 1.0), col("C-H13")
        age = np.zeros((N, Z))

    out = {k: np.zeros((H, S)) for k in ("p_down", "p_thermal", "theta_h")}
    for k, w in (("hosp", len(hs)), ("water_out", 1), ("signals_dark", 1),
                 ("roads_degraded", 1), ("n_down", 1), ("roads_p", len(net.roads)), ("indoor_out_pop", 1),
                 ("indoor_ac_max_c", 1)):
        out[k] = np.zeros((H, w))
    pop_out = np.zeros((N, H))
    # 【中文】K8：每次运行降级路段最多的小时（−1 = 从未降级）及该小时的路段与设施状态
    # K8: per run, the hour with the most degraded segments and the state at that hour
    worst_h, worst_n = np.full(N, -1), np.zeros(N)
    snap_deg = np.zeros((N, len(net.roads)), bool)
    snap_h = np.zeros((N, len(hs)), bool)
    tot = {k: np.zeros(N) for k in ("thermal", "deenergised_hours", "pop_hours", "shed_station_hours", "hospital_hours",
                                    "hospital_power_hours", "hospital_water_hours", "water_out_hours", "signal_dark_hours",
                                    "max_subs_down", "ac_loss_pop_hours", "indoor_pop_hours",
                                    "indoor_outage_pop_hours", "indoor_outage_elderly_hours",
                                    "indoor_outage_poverty_hours", "indoor_no_ac_pop_hours",
                                    "dep_visits", "heat_visits_excess")}

    for h in range(H):
        if power == "fragility":
            Ta_h = np.broadcast_to(Ta_mean if ("R03" in off or "R03a" in off) else Ta_sub[h][None, :], (N, S))
            T_lag = Ta_h.copy() if T_lag is None else T_lag + (Ta_h - T_lag) * (1 - np.exp(-1.0 / tau))
            T_eff = (1 - w_lag) * Ta_h + w_lag * T_lag
            thetaH = T_eff
            p = np.zeros_like(thetaH) if "R04" in off else ndtr((T_eff - T50) / sigT)
        else:
            # K2：基础负荷 1 + 制冷负荷，按设计日归一的标幺负荷（无负荷转移）/ base + cooling load, per unit
            cool = np.zeros_like(beta) if "R02" in off else beta * np.maximum(0, TF[h] - T0)
            K = Kd * (m_mean if "R03b" in off else 1 + cool) / mTd
            # K3：顶油温升一阶滞后 + 热点温度 → 热失效 / top-oil lag, hot spot and thermal failure
            dTOU = dTOR * ((K ** 2 * R + 1) / (R + 1)) ** n_
            dTO = dTOU if dTO is None else dTO + (dTOU - dTO) * (1 - np.exp(-1.0 / tau))
            thetaH = (Ta_mean if ("R03" in off or "R03a" in off) else Ta_sub[h][None, :]) + dTO + dHR * K ** (2 * m_)
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

        # K5：失效或被切除的站停电；供电依赖（向下游传播）2026-11-20 起暂缓（D13），supply_dependency=True 时恢复
        # K5: failed or shed stations are out; propagation down the topology is deferred (D13)
        up = ~failed & ~shed_now
        for _ in range(S if (supply_dependency and "R08" not in off) else 0):
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

        # K6–K7：医院与水厂的备用电源（每次停电开始时抽样）与供水 / backup draws and water
        def backed(src_down, B, prev, pb):
            start = src_down & ~prev
            B = np.where(start, rng.random(B.shape) < pb, B)
            return src_down & B, B, src_down

        fac_down = np.zeros_like(down) if "R11" in off else down
        hl_p, B_h, prev_h = backed(fac_down[:, hs], B_h, prev_h, p_bh)
        wl, B_w, prev_w = backed((np.zeros_like(down) if "R09" in off else down)[:, ps], B_w, prev_w, p_bw)
        prod_lost = wl.all(1, keepdims=True) if len(ps) else np.zeros((N, 1), bool)
        storage_left = np.where(prod_lost, storage_left - 1, col("C-W3"))
        water_out = prod_lost & (storage_left < 0) if (net.has_storage and "R10" not in off) else prod_lost
        # 【中文】医院断水：断水持续超过院内储水时长后失去功能（全系统断水，对所有医院相同）
        # hospitals lose function once system water loss outlasts their on-site supply
        water_age = np.where(water_out, water_age + 1, 0)
        hl_w = np.repeat((water_age > h_water) & ("R12" not in off), len(hs), axis=1) & ~hl_p
        hl = hl_p | hl_w
        # K8：信号灯熄灭 → 所控路段降级（供 pipeline.access 使用）/ dark signals → degraded segments
        dark = down[:, gs] & no_batt & ("R13" not in off)
        deg = (dark.astype(float) @ net.M_sig_road) > 0

        out["hosp"][h] = hl.mean(0)
        out["water_out"][h] = water_out.mean(); out["signals_dark"][h] = dark.sum(1).mean()
        out["roads_degraded"][h] = deg.sum(1).mean(); out["roads_p"][h] = deg.mean(0)
        tot["hospital_hours"] += hl.sum(1); tot["hospital_power_hours"] += hl_p.sum(1); tot["hospital_water_hours"] += hl_w.sum(1)
        tot["water_out_hours"] += water_out[:, 0]; tot["signal_dark_hours"] += dark.sum(1)
        # 【中文】最坏小时：降级路段数 + 关闭的医院（每家记 500，使有医院关闭的小时优先）
        # worst hour: degraded segments plus closed hospitals (500 each, so closures come first)
        nd = deg.sum(1) + 500 * hl.sum(1)
        better = nd > worst_n
        if better.any():
            worst_h[better], worst_n[better] = h, nd[better]
            snap_deg[better], snap_h[better] = deg[better], hl[better]

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
            # 【中文】呼吸机等设备用户：停电持续到电池耗尽时，以概率 q 就医（每次停电一次）/ device users
            age_prev = age
            age = np.where(zdown, age + 1, 0)
            hit = zdown & (age_prev < hb) & (age >= hb)
            dep = np.zeros(N) if "R24" in off else (hit * zone_dep).sum(1) * q[:, 0]
            # 【中文】热病症就诊的超额部分 = k × 当小时高温暴露人·小时 / excess heat-illness visits
            expo_z = e_out * pop + (1 - f_ac) * hot_no * pop                   # 【中文】分区暴露 / exposure by zone
            heat_z = k_heat * expo_z
            dep_z = np.zeros((N, Z)) if "R24" in off else hit * zone_dep * q
            heat = heat_z.sum(1)
            extra_day[:, dayi[h]] += heat + dep
            heat_zd[:, dayi[h]] += heat_z.astype(np.float32)
            dep_zd[:, dayi[h]] += dep_z.astype(np.float32)
            hosp_pd[:, dayi[h]] += hl_p
            hosp_wd[:, dayi[h]] += hl_w
            tot["dep_visits"] += dep; tot["heat_visits_excess"] += heat
        out["indoor_ac_max_c"][h] = Tin_ac[zdown].max() if zdown.any() else np.nan
        repair = np.maximum(repair - 1, 0)

    tot["indoor_pop_hours"] = tot["indoor_outage_pop_hours"] + tot["indoor_no_ac_pop_hours"]
    if lb:
        pk = extra_day.argmax(1)
        ar = np.arange(N)
        tot["peak_day_extra_visits"] = extra_day[ar, pk]
        # 【中文】高峰日医院的平均可用比例（停电小时数折算）/ average open share of hospitals on the peak day
        cp_, cw_ = hosp_pd[ar, pk].astype(float), hosp_wd[ar, pk].astype(float)
        tot["peak_day_open_share"] = 1 - (cp_ + cw_).sum(1) / (24 * max(len(hs), 1))
        eh, ed_ = heat_zd[ar, pk].astype(float), dep_zd[ar, pk].astype(float)
        tot["peak_day_heat_visits"], tot["peak_day_dep_visits"] = eh.sum(1), ed_.sum(1)
        care = {"extra_heat_zone": eh, "extra_dep_zone": ed_, "extra_zone": eh + ed_,
                "hosp_closed_power_h": cp_, "hosp_closed_water_h": cw_, "hosp_closed_h": cp_ + cw_}
        tot["mean_day_extra_visits"] = extra_day.mean(1)
    return {"hourly": out, "pop_out": pop_out, "totals": tot,
            "worst": {"hour": worst_h, "roads": snap_deg, "hosp": snap_h},
            "care": care if lb else None}
