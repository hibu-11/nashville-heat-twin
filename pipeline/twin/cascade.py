"""
【中文】级联模拟 v0（设计方案阶段 B + C 的雏形）。逐小时推进，N 次蒙特卡洛运行一起向量化计算。
每一步的公式编号对应 docs/HANDBOOK.md §4：

    Eq. 2–3   气温 → 负荷倍数 → 变压器标幺负荷 K
    Eq. 4–6   IEEE C57.91 顶油温升（一阶滞后）与热点温度 θH
    Eq. 7     θH → 每小时热失效概率（正态脆弱性曲线）
    Eq. 8     失效站负荷平均转移给同电压等级的在运对等站；超过 (1+α)·L_d 即过载跳闸（Motter–Lai）
    Eq. 9     供电依赖：所有上级电源都停运时，下级站失电（Buldyrev 等 2010 的功能依赖）
    Eq. 10    热失效 / 过载跳闸后停运 R 小时
    Eq. 11    设施 / 信号灯：分区失电 ∧ 备用失效
    Eq. 13    供水：全部水厂失电后，储水 h 小时耗尽，设施断水
    Eq. 14    人口：失电人口；热浪 + 停电复合暴露（人·小时）
    Eq. 16    信号灯失灵 → 所控路段控制降级

Cascade simulation v0: hourly steps, N Monte Carlo runs vectorised together.
Equation numbers refer to docs/HANDBOOK.md §4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import ndtr

from .rules import attrs, substation_table


def c_to_f(c):
    return np.asarray(c) * 9.0 / 5.0 + 32.0


class Network:
    """【中文】从标准表组装模型需要的矩阵 / matrices assembled from the standard tables."""

    def __init__(self, assets: pd.DataFrame, deps: pd.DataFrame, cfg: dict):
        subs = substation_table(assets[assets["source_id"] == cfg["substations"]])
        self.subs = subs.reset_index(drop=True)
        self.sid = list(self.subs["asset_id"])
        idx = {s: i for i, s in enumerate(self.sid)}
        S = len(self.sid)

        power = deps[deps["dep_type"] == "power"]
        peer = deps[deps["dep_type"] == "power_peer"]
        # 【中文】U[u, s] = 1：u 给 s 供电；P：对等（同电压）连接 / supply and peer matrices
        self.U = np.zeros((S, S))
        for f, t in zip(power["from_asset"], power["to_asset"]):
            if f in idx and t in idx:
                self.U[idx[f], idx[t]] = 1
        self.P = np.zeros((S, S))
        for f, t in zip(peer["from_asset"], peer["to_asset"]):
            if f in idx and t in idx:
                self.P[idx[f], idx[t]] = self.P[idx[t], idx[f]] = 1
        self.has_supply = self.U.sum(axis=0) > 0

        zones = assets[assets["asset_type"] == "service_zone"].reset_index(drop=True)
        za = attrs(zones)
        self.zone_id = list(zones["asset_id"])
        self.zone_sub = np.array([idx.get(s, -1) for s in za["substation"]])
        self.zone_pop = pd.to_numeric(za["pop_total"], errors="coerce").fillna(0).to_numpy()
        self.zone_eld = pd.to_numeric(za["pop_elderly"], errors="coerce").fillna(0).to_numpy()
        self.zone_pov = pd.to_numeric(za["pop_below_poverty"], errors="coerce").fillna(0).to_numpy()
        area = pd.to_numeric(za["building_area_m2"], errors="coerce").fillna(0).to_numpy()

        # 【中文】设计负荷 L_d（相对单位）：有分区的供电站 = 分区建筑面积；无分区的供电站 = 中位数；
        # 不直接供电的站 = 其直接下级站 L_d 之和（A-P3）/ design load in relative units (assumption A-P3)
        Ld = np.full(S, np.nan)
        for z, s in enumerate(self.zone_sub):
            if s >= 0:
                Ld[s] = np.nansum([Ld[s], area[z]]) if not np.isnan(Ld[s]) else area[z]
        med = np.nanmedian(Ld[Ld > 0]) if np.any(Ld > 0) else 1.0
        serving = self.subs["serving"].to_numpy()
        Ld[serving & (np.isnan(Ld) | (Ld <= 0))] = med
        for _ in range(4):   # 【中文】自下而上累加 / accumulate bottom-up through the hierarchy
            for s in np.where(~serving)[0]:
                kids = np.where(self.U[s] > 0)[0]
                Ld[s] = np.nansum(Ld[kids]) if len(kids) else med
        self.Ld = np.where(np.isnan(Ld) | (Ld <= 0), med, Ld) / med   # 【中文】以中位数归一 / normalised

        # 【中文】下游资产 → 电源（分区或变电站）的索引 / downstream asset → feeding substation index
        zone_to_sub = dict(zip(self.zone_id, self.zone_sub))
        feed = deps[deps["rule_id"].isin(["R-P4", "R-P4b"])]
        self.feed = {}
        for f, t, c in zip(feed["from_asset"], feed["to_asset"], feed["coupling_id"]):
            s = zone_to_sub.get(f, idx.get(f, -1))
            if s >= 0:
                self.feed[t] = (s, c)

        def ids_with(coupling):
            return [a for a, (_, c) in self.feed.items() if c == coupling]

        self.hosp, self.nurs, self.dial = ids_with("C-H1"), ids_with("C-H2"), ids_with("C-H3")
        self.plants, self.signals = ids_with("C-W2"), ids_with("C-T2")
        ctl = deps[deps["dep_type"] == "control"]
        sig_idx = {s: i for i, s in enumerate(self.signals)}
        self.roads = sorted(set(ctl["to_asset"]))
        road_idx = {r: i for i, r in enumerate(self.roads)}
        self.M_sig_road = np.zeros((len(self.signals), len(self.roads)))
        for f, t in zip(ctl["from_asset"], ctl["to_asset"]):
            if f in sig_idx:
                self.M_sig_road[sig_idx[f], road_idx[t]] = 1
        self.has_storage = (deps["dep_type"] == "water_storage").any()

    def sub_of(self, ids):
        return np.array([self.feed[a][0] for a in ids], dtype=int)


def simulate(net: Network, Ta_c: np.ndarray, th: dict, rng: np.random.Generator, record_runs=False,
             Ta_sub: np.ndarray | None = None, Ta_zone: np.ndarray | None = None, shed: np.ndarray | None = None) -> dict:
    """【中文】主循环。Ta_c：逐小时气温（°C），th：每个参数长度为 N 的抽样数组。
    Ta_sub (H, S) / Ta_zone (H, Z)：各变电站 / 分区的逐小时气温（城市气温场 M-6）；不给时全城用 Ta_c（假设 A-D4）。
    shed (H,) 或 (N, H)：系统供电缺口导致的轮流停电比例（M-18 / R-P0），只在 shed > 0 的小时抽随机数，
    因此 shed 全为 0 时结果与不给 shed 完全相同。

    Main loop. Ta_c: hourly air temperature (°C); th: sampled parameters (length N each).
    Ta_sub / Ta_zone: local temperatures from the urban field (M-6); default is Ta_c everywhere (A-D4).
    shed: share of serving stations shed per hour by a system supply shortfall (M-18)."""
    N, S, H = len(th["C-P1"]), len(net.sid), len(Ta_c)
    col = lambda k: th[k][:, None]  # noqa: E731
    Ta_sub = np.repeat(np.asarray(Ta_c, float)[:, None], S, axis=1) if Ta_sub is None else np.asarray(Ta_sub, float)
    Z = len(net.zone_id)
    Ta_zone = np.repeat(np.asarray(Ta_c, float)[:, None], Z, axis=1) if Ta_zone is None else np.asarray(Ta_zone, float)
    TF = c_to_f(Ta_sub)
    serving_mask = net.subs["serving"].to_numpy()

    beta, T0, Kd, Td = col("C-P1"), col("C-P1.T0"), col("C-P1.Kd"), col("C-P1.Td")
    dTOR, dHR, R, n_, m_, tau = (col(k) for k in ("C-P2.dTOR", "C-P2.dHR", "C-P2.R", "C-P2.n", "C-P2.m", "C-P2.tau"))
    th50, sig, alpha = col("C-P3"), col("C-P3.sigma"), col("C-P4")
    rep = np.round(th["C-P6"]).astype(int)[:, None]

    Ld = net.Ld[None, :]
    Lr = Ld / Kd                                   # 【中文】额定负荷 / rated load (K = 1)
    cap = (1 + alpha) * Ld                         # Eq. 8 capacity
    mTd = 1 + beta * np.maximum(0, Td - T0)

    repair = np.zeros((N, S), dtype=int)
    dTO = None
    dL_prev = np.zeros((N, S))

    # 【中文】下游资产 / downstream assets
    hs, ns, ds = net.sub_of(net.hosp), net.sub_of(net.nurs), net.sub_of(net.dial)
    ps, gs = net.sub_of(net.plants), net.sub_of(net.signals)
    p_bh, p_bn, p_bw = col("C-H1"), col("C-H2"), col("C-W2")
    no_batt = rng.random((N, len(gs))) < col("C-T2")          # Eq. 11, static per run
    B_h = np.zeros((N, len(hs)), bool); B_n = np.zeros((N, len(ns)), bool); B_w = np.zeros((N, len(ps)), bool)
    prev_h = np.zeros_like(B_h); prev_n = np.zeros_like(B_n); prev_w = np.zeros_like(B_w)
    storage_left = np.repeat(col("C-W3"), 1, axis=1).astype(float)
    T_heat = th["C-POP2"]

    zs = net.zone_sub
    out = {k: np.zeros((H, S)) for k in ("p_down", "p_thermal", "theta_h")}
    for k, w in (("hosp", len(hs)), ("nurs", len(ns)), ("dial", len(ds)), ("water_out", 1), ("signals_dark", 1),
                 ("roads_degraded", 1), ("n_down", 1), ("roads_p", len(net.roads))):
        out[k] = np.zeros((H, w))
    pop_out = np.zeros((N, H))
    tot = {k: np.zeros(N) for k in ("thermal", "overload", "deenergised_hours", "pop_hours", "compound_pop_hours",
                                    "compound_elderly_hours", "compound_poverty_hours", "dialysis_hours",
                                    "hospital_hours", "water_out_hours", "max_subs_down", "shed_station_hours")}
    road_deg_hours = np.zeros(len(net.roads))

    for h in range(H):
        # Eq. 2–3：负荷倍数与标幺负荷 / load multiplier and per-unit load
        m = 1 + beta * np.maximum(0, TF[h] - T0)
        L = Ld * (m / mTd)
        K = (L + dL_prev) / Lr
        # Eq. 4–6：顶油温升一阶滞后 + 热点温度 / top-oil lag and hot spot
        dTOU = dTOR * ((K ** 2 * R + 1) / (R + 1)) ** n_
        dTO = dTOU if dTO is None else dTO + (dTOU - dTO) * (1 - np.exp(-1.0 / tau))
        thetaH = Ta_sub[h][None, :] + dTO + dHR * K ** (2 * m_)
        # Eq. 7：热失效 / thermal failure
        p = ndtr((thetaH - th50) / sig)
        failed = repair > 0
        new_t = ~failed & (rng.random((N, S)) < p)
        repair = np.where(new_t, rep, repair)
        failed |= new_t
        tot["thermal"] += new_t.sum(1)

        # M-18 / R-P0：系统缺电时按比例轮流切除供电站（不算失效，不进修复）/ rotating load shed
        shed_now = np.zeros((N, S), bool)
        sh = None if shed is None else (shed[:, h] if np.ndim(shed) == 2 else np.full(N, shed[h]))
        if sh is not None and np.any(sh > 0):
            shed_now = (rng.random((N, S)) < sh[:, None]) & serving_mask[None, :]

        # Eq. 8–9：供电依赖 + 负荷转移，迭代到稳定 / supply dependency and load transfer to a fixed point
        for _ in range(40):
            up = ~failed & ~shed_now
            for _ in range(S):
                sup_ok = (up.astype(float) @ net.U) > 0
                nxt = ~failed & ~shed_now & (~net.has_supply[None, :] | sup_ok)
                if (nxt == up).all():
                    break
                up = nxt
            down = ~up
            n_up = up.astype(float) @ net.P
            share = np.where(down & (n_up > 0), L / np.maximum(n_up, 1), 0.0)
            dL = (share @ net.P) * up
            over = up & (L + dL > cap)
            if not over.any():
                break
            repair = np.where(over, rep, repair)
            failed |= over
            tot["overload"] += over.sum(1)
        dL_prev = dL

        # 【中文】记录电力状态 / record power state
        out["p_down"][h] = down.mean(0)
        out["p_thermal"][h] = p.mean(0)
        out["theta_h"][h] = thetaH.mean(0)
        out["n_down"][h] = down.sum(1).mean()
        tot["deenergised_hours"] += (down & ~failed).sum(1)
        tot["max_subs_down"] = np.maximum(tot["max_subs_down"], down.sum(1))
        zdown = np.where(zs[None, :] >= 0, down[:, np.maximum(zs, 0)], False)
        po = zdown.astype(float) @ net.zone_pop
        pop_out[:, h] = po
        tot["pop_hours"] += po
        # 【中文】复合暴露按分区本地气温判断 / compound exposure uses each zone's local temperature
        zhot = (zdown & (Ta_zone[h][None, :] >= T_heat[:, None])).astype(float)
        tot["compound_pop_hours"] += zhot @ net.zone_pop
        tot["compound_elderly_hours"] += zhot @ net.zone_eld
        tot["compound_poverty_hours"] += zhot @ net.zone_pov
        tot["shed_station_hours"] += shed_now.sum(1)

        # Eq. 11：设施备用电源，按停电事件抽样 / backup draw at the start of each outage episode
        def backed(src_down, B, prev, pb):
            start = src_down & ~prev
            B = np.where(start, rng.random(B.shape) < pb, B)
            return src_down & B, B, src_down

        hl, B_h, prev_h = backed(down[:, hs], B_h, prev_h, p_bh)
        nl, B_n, prev_n = backed(down[:, ns], B_n, prev_n, p_bn)
        wl, B_w, prev_w = backed(down[:, ps], B_w, prev_w, p_bw)
        # Eq. 13：全部水厂失电 → 消耗储水 / storage drains once every plant is down
        prod_lost = wl.all(1, keepdims=True) if len(ps) else np.zeros((N, 1), bool)
        storage_left = np.where(prod_lost, storage_left - 1, np.repeat(col("C-W3"), 1, axis=1))
        water_out = prod_lost & (storage_left < 0) if net.has_storage else prod_lost
        dl = down[:, ds] | water_out                                     # C-H3 dialysis: series
        dark = down[:, gs] & no_batt
        deg = (dark.astype(float) @ net.M_sig_road) > 0                  # Eq. 16

        out["hosp"][h] = hl.mean(0); out["nurs"][h] = nl.mean(0); out["dial"][h] = dl.mean(0)
        out["water_out"][h] = water_out.mean(); out["signals_dark"][h] = dark.sum(1).mean()
        out["roads_degraded"][h] = deg.sum(1).mean()
        out["roads_p"][h] = deg.mean(0)
        road_deg_hours += deg.mean(0)
        tot["dialysis_hours"] += dl.sum(1); tot["hospital_hours"] += hl.sum(1)
        tot["water_out_hours"] += water_out[:, 0]
        repair = np.maximum(repair - 1, 0)

    res = {"hourly": out, "pop_out": pop_out, "totals": tot, "road_degraded_hours": road_deg_hours}
    return res


def pavement(exp: pd.DataFrame, th: dict, tz: str) -> pd.DataFrame:
    """【中文】Eq. 15：路面热损伤。仿照 PG 分级的“7 天平均最高路面温度”定义：
    先取每段路每天的最高 LST（排除 suspect 帧），再取连续 7 个有数据日的滑动平均的最大值 T7，
        p_i = Φ((T7_i − x50) / σ)
    对参数抽样取平均。/ Eq. 15: the maximum 7-day running mean of daily-max LST, compared
    with the PG high grade through a normal fragility, averaged over parameter draws."""
    e = exp[exp["quality_flag"] == "ok"].copy()
    e["day"] = e["timestamp"].dt.tz_convert(tz).dt.date
    dmax = e.groupby(["asset_id", "day"])["lst_max"].max().unstack().sort_index(axis=1)
    t7 = dmax.T.rolling(7, min_periods=5).mean().T.max(axis=1)
    x50, sg = th["C-T1"][:, None], th["C-T1.sigma"][:, None]
    p = ndtr((t7.to_numpy()[None, :] - x50) / sg)
    return pd.DataFrame({"asset_id": dmax.index, "lst_daymax_peak": dmax.max(axis=1).to_numpy(),
                         "lst_t7_max": t7.round(2).to_numpy(), "p_exceed": np.nan_to_num(p.mean(0)),
                         "days_with_lst": np.isfinite(dmax.to_numpy()).sum(1)})
