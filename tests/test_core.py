"""
【中文】骨架模型的行为测试：用一个人工搭的小网络（4 座变电站、3 个分区）检查不变量，不需要标准表。
    .venv/bin/python -m pytest -q

Behaviour tests of the core model on a small synthetic network; no standard tables needed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import care
from pipeline.twin.core import CORE_PARAMS, KNOCKOUTS, fragility_from_ieee, simulate_core

H, N = 72, 40


class FakeNet:
    """【中文】最小网络：S0 为输电站，供 S1–S3；每个配电站一个分区 / one transmission station feeding three."""

    def __init__(self):
        self.sid = ["S0", "S1", "S2", "S3"]
        self.subs = pd.DataFrame({"serving": [False, True, True, True]})
        self.U = np.zeros((4, 4))
        self.U[0, 1:] = 1                       # 【中文】S0 → S1, S2, S3
        self.has_supply = self.U.sum(axis=0) > 0
        self.zone_id = ["Z1", "Z2", "Z3"]
        self.zone_sub = np.array([1, 2, 3])
        self.zone_pop = np.array([1000.0, 2000.0, 3000.0])
        self.zone_eld = self.zone_pop * 0.15
        self.zone_pov = self.zone_pop * 0.12
        self.hosp = ["H1", "H2"]
        self.plants, self.signals = ["W1"], ["G1", "G2"]
        self._feed = {"H1": 1, "H2": 2, "W1": 1, "G1": 2, "G2": 3}
        self.roads = ["r1", "r2"]
        self.M_sig_road = np.eye(2)
        self.has_storage = True

    def sub_of(self, ids):
        return np.array([self._feed[i] for i in ids], dtype=int)


def params(n=N, seed=1, hot=True):
    """【中文】中值附近的参数；hot=True 时让变电站容易热失效，以便出现停电。C-P11 只用于 power="fragility"。
    Parameters near mid values; hot=True makes thermal failures likely. C-P11 is only used with power="fragility"."""
    rng = np.random.default_rng(seed)
    base = {"C-P1": 0.024, "C-P1.T0": 75, "C-P1.Kd": 1.0 if hot else 0.6, "C-P1.Td": 93, "C-P2.dTOR": 55, "C-P2.dHR": 25,
            "C-P2.R": 4.5, "C-P2.n": 0.8, "C-P2.m": 0.8, "C-P2.tau": 3, "C-P3": 120 if hot else 160, "C-P3.sigma": 8,
            "C-P11": 34 if hot else 45, "C-P11.sigma": 2, "C-P11.tau": 3, "C-P11.w": 0.48, "C-P6": 3, "C-P9.avail": 0.9, "C-P9.imp": 4000, "C-H1": 0.05, "C-H2": 0.3, "C-W2": 0.05, "C-W3": 10,
            "C-T2": 0.9, "C-T5": 0.5, "C-T8": 0.0176, "C-T11": 395, "C-T12": 0.0056, "C-B1": 12, "C-B2": 4, "C-B3": 22.5, "C-B4": 0.94, "C-H10": 28,
            "C-H11": 4e-6, "C-H11.a": 0.0086, "C-H12": 2, "C-H13": 0.05, "C-H14": 0.75, "C-H15": 1000, "C-H16": 30, "C-H18": 4}
    assert set(base) >= set(CORE_PARAMS)
    return {k: np.full(n, float(v)) * (1 + 0.05 * rng.standard_normal(n) * (k in ("C-P1.Kd", "C-P3", "C-P11"))) for k, v in base.items()}


def run(off=frozenset(), seed=7, shed=None, lineb=True, hot=True, th=None, net=None, power="load", supply_dependency=False):
    net = net or FakeNet()
    t = np.arange(H)
    Ta = 30 + 6 * np.sin((t - 9) / 24 * 2 * np.pi)
    day = ((t % 24) >= 8) & ((t % 24) < 20)
    lb = {"zone_dep": np.array([10.0, 20.0, 30.0]), "day": t // 24} if lineb else None
    return simulate_core(net, Ta, th or params(hot=hot), np.random.default_rng(seed), day, shed=shed, off=frozenset(off), lineb=lb,
                         power=power, supply_dependency=supply_dependency)


def tot(r, k):
    return r["totals"][k]


def test_same_seed_same_result():
    a, b = run(), run()
    for k in a["totals"]:
        np.testing.assert_array_equal(tot(a, k), tot(b, k))


def test_hot_network_has_outages():
    assert tot(run(), "pop_hours").mean() > 0
    assert tot(run(hot=False), "pop_hours").mean() < tot(run(), "pop_hours").mean()


def test_no_thermal_failure_means_no_outage():
    r = run(off={"R04"})
    assert tot(r, "thermal").sum() == 0
    assert tot(r, "pop_hours").sum() == 0
    assert tot(r, "indoor_outage_pop_hours").sum() == 0
    assert tot(r, "dep_visits").sum() == 0


@pytest.mark.parametrize("ko, changed, unchanged", [
    ("R13", ["signal_dark_hours"], ["pop_hours", "hospital_hours", "indoor_outage_pop_hours"]),
    ("R11", ["hospital_hours"], ["pop_hours", "signal_dark_hours"]),
    ("R18", ["indoor_outage_pop_hours"], ["pop_hours", "hospital_hours", "indoor_no_ac_pop_hours"]),
    ("R24", ["dep_visits"], ["pop_hours", "heat_visits_excess"]),
    ("R21", ["heat_visits_excess"], ["pop_hours", "dep_visits"]),
])
def test_knockout_is_local(ko, changed, unchanged):
    """【中文】关掉一条关系只改变它下游的输出；公共随机数保证其余输出完全相同。"""
    base, k = run(), run(off={ko})
    for c in changed:
        assert tot(k, c).sum() < tot(base, c).sum() or tot(base, c).sum() == 0
    for u in unchanged:
        np.testing.assert_allclose(tot(k, u), tot(base, u))


def test_shortfall_draw_keeps_random_numbers_aligned():
    """【中文】给一个全为 0 的缺口序列，结果必须与不给缺口完全相同（随机数每小时都抽）。"""
    a = run(shed=None)
    b = run(shed=np.zeros((N, H)))
    np.testing.assert_array_equal(tot(a, "pop_hours"), tot(b, "pop_hours"))


def test_repair_one_hour_reduces_outage():
    assert tot(run(off={"R07"}), "pop_hours").mean() <= tot(run(), "pop_hours").mean()


def test_supply_dependency_propagates():
    """【中文】供电依赖（D13，默认关闭）打开后，输电站 S0 失效会使下游分区停电，停电人·小时不会减少。"""
    assert tot(run(supply_dependency=True), "pop_hours").mean() >= tot(run(), "pop_hours").mean()
    assert tot(run(supply_dependency=True, off={"R08"}), "pop_hours").mean() == tot(run(), "pop_hours").mean()


def test_every_knockout_is_handled():
    for ko in KNOCKOUTS:
        run(off={ko})                            # 【中文】每个开关都能运行 / every switch runs


def toy_care(nH=3, ncell=6):
    """【中文】6 个网格、3 家医院的小算例 / six cells, three hospitals."""
    T = np.array([[5, 10, 20], [6, 9, 18], [12, 4, 15], [14, 5, 11], [20, 12, 3], [18, 13, 4]], float)[:ncell, :nH]
    order = np.argsort(T, axis=1)
    pop = np.full(ncell, 100.0)
    share = pop / pop.sum()
    return {"T": T, "order": order, "Tsorted": np.take_along_axis(T, order, axis=1), "cz": np.array([0, 0, 1, 1, 2, 2])[:ncell],
            "pop": pop, "share": share, "zone_pop": np.array([200.0, 200.0, 200.0]),
            "L0": np.bincount(order[:, 0], weights=share, minlength=nH)}


def care_state(extra=0.0, closed=None, n=N, device=0.0, water=None):
    z = lambda x: np.full((n, 3), x / 3)  # noqa: E731
    cp_ = np.zeros((n, 3)) if closed is None else np.tile(closed, (n, 1)).astype(float)
    cw_ = np.zeros((n, 3)) if water is None else np.tile(water, (n, 1)).astype(float)
    return {"extra_heat_zone": z(extra), "extra_dep_zone": z(device), "extra_zone": z(extra) + z(device),
            "hosp_closed_power_h": cp_, "hosp_closed_water_h": cw_, "hosp_closed_h": cp_ + cw_}


def test_time_to_care_zero_at_baseline():
    out = care.ed_time(toy_care(), care_state(), params())
    np.testing.assert_allclose(out["time"], 0, atol=1e-9)


def test_time_to_care_grows_with_demand():
    th = params()
    t = [care.ed_time(toy_care(), care_state(x), th)["time"].mean() for x in (0, 20, 100, 400)]
    assert all(b >= a for a, b in zip(t, t[1:])) and t[-1] > 0


def test_closure_adds_travel():
    out = care.ed_time(toy_care(), care_state(closed=np.array([24.0, 0, 0])), params())
    assert out["travel"].mean() > 0
    off = care.ed_time(toy_care(), care_state(closed=np.array([24.0, 0, 0])), params(), off={"R17"})
    np.testing.assert_allclose(off["travel"], 0, atol=1e-9)


def test_no_waiting_effect_when_switched_off():
    out = care.ed_time(toy_care(), care_state(400), params(), off={"R22"})
    np.testing.assert_allclose(out["wait"], 0, atol=1e-9)


def test_decomposition_adds_up():
    """【中文】四个原因的 Shapley 分量之和等于路程 + 等待增量；没有的原因分到 0。"""
    th = params()
    st = care_state(extra=60, device=200, closed=np.array([12.0, 0, 0]))
    d = care.decompose(toy_care(), st, th, runs=range(5))
    parts = sum(d[f] for f in care.FACTORS)
    np.testing.assert_allclose(parts, d["travel"] + d["wait"], rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(d["water"], 0, atol=1e-12)
    assert (d["device"] > d["heat"]).all() and (d["power"] > 0).all()
    np.testing.assert_allclose(d["baseline_minus"], 0, atol=1e-9)


def test_hospital_water_loss():
    """【中文】断水超过院内储水时长后医院关闭；R12 关掉后不受断水影响。"""
    net = FakeNet()
    net.has_storage = False
    th = params()
    th["C-W2"] = np.ones(N)                  # 【中文】水厂备用电源总是失效 / plant backup always fails
    th["C-H18"] = np.zeros(N)
    th["C-H1"] = np.zeros(N)                 # 【中文】医院备用电源从不失效，只剩断水路径 / hospital power never fails
    a, b = run(th=th, net=net), run(th=th, net=net, off={"R12"})
    assert tot(a, "hospital_water_hours").sum() > 0 and tot(a, "hospital_power_hours").sum() == 0
    assert tot(b, "hospital_water_hours").sum() == 0


def test_line_b_outputs_present():
    r = run()
    for k in ("heat_visits_excess", "dep_visits", "peak_day_extra_visits", "peak_day_open_share", "peak_day_heat_visits",
              "peak_day_dep_visits"):
        assert k in r["totals"]
    assert r["care"]["extra_zone"].shape == (N, 3) and r["care"]["hosp_closed_h"].shape == (N, 2)
    np.testing.assert_allclose(r["care"]["extra_zone"], r["care"]["extra_heat_zone"] + r["care"]["extra_dep_zone"])
    assert (r["totals"]["peak_day_open_share"] <= 1).all() and (r["totals"]["peak_day_open_share"] >= 0).all()


def test_fragility_power_model_runs():
    """【中文】可选的气温脆弱性曲线（power="fragility"）可运行，热的参数下有停电；"ieee" 是负荷链的旧名。"""
    assert tot(run(power="fragility"), "pop_hours").mean() > 0
    assert tot(run(power="fragility", off={"R04"}), "pop_hours").sum() == 0
    np.testing.assert_array_equal(tot(run(power="ieee"), "pop_hours"), tot(run(), "pop_hours"))


def test_cooling_load_knockout():
    """【中文】制冷负荷不随气温（R02，只剩基础负荷）时热失效不会增加。"""
    assert tot(run(off={"R02"}), "thermal").sum() <= tot(run(), "thermal").sum()


def test_rutting_delay():
    """【中文】车辙增量 = rut_unit × k × ΔT × b × c；+0 °C 或关掉 R27 时为 0。"""
    from pipeline.core import time_to_care
    th = params()
    cp = toy_care() | {"rut_unit": 0.5}
    ed = lambda dT, off=frozenset(): time_to_care(cp, {"care": care_state()}, th, {"_congestion_hospital": np.zeros(N)},  # noqa: E731
                                                  off=off, dT=dT)
    np.testing.assert_allclose(ed(4.0)["rutting"], 0.5 * 4.0 * th["C-T8"] * th["C-T11"] * th["C-T12"])
    np.testing.assert_allclose(ed(4.0)["time"], ed(4.0)["rutting"], atol=1e-9)
    assert ed(0.0)["rutting"].sum() == 0 and ed(4.0, frozenset({"R27"}))["rutting"].sum() == 0


def test_fragility_mapping_from_ieee():
    """【中文】由 IEEE 参数换算的气温脆弱性：T50 在合理范围内，热的参数（设计负荷率高）门槛更低。"""
    hot, cold = (fragility_from_ieee(params(hot=h)) for h in (True, False))
    assert np.all((hot[0] > 0) & (hot[0] < cold[0]))
    assert np.all((hot[1] > 0) & (hot[2] > 0) & (hot[2] < 1))
