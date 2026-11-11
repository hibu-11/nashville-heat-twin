"""
【中文】骨架模型的行为测试：用一个人工搭的小网络（4 座变电站、3 个分区）检查不变量，不需要标准表。
    .venv/bin/python -m pytest -q

Behaviour tests of the core model on a small synthetic network; no standard tables needed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.core import waiting
from pipeline.twin.core import CORE_PARAMS, KNOCKOUTS, simulate_core

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
        self.hosp, self.nurs, self.dial = ["H1", "H2"], ["N1"], ["D1"]
        self.plants, self.signals = ["W1"], ["G1", "G2"]
        self._feed = {"H1": 1, "H2": 2, "N1": 3, "D1": 2, "W1": 1, "G1": 2, "G2": 3}
        self.roads = ["r1", "r2"]
        self.M_sig_road = np.eye(2)
        self.has_storage = True

    def sub_of(self, ids):
        return np.array([self._feed[i] for i in ids], dtype=int)


def params(n=N, seed=1, hot=True):
    """【中文】中值附近的参数；hot=True 时让变压器容易过热，以便出现停电 / parameters near mid values."""
    rng = np.random.default_rng(seed)
    base = {"C-P1": 0.024, "C-P1.T0": 75, "C-P1.Kd": 1.0 if hot else 0.6, "C-P1.Td": 93, "C-P2.dTOR": 55, "C-P2.dHR": 25,
            "C-P2.R": 4.5, "C-P2.n": 0.8, "C-P2.m": 0.8, "C-P2.tau": 3, "C-P3": 120 if hot else 160, "C-P3.sigma": 8,
            "C-P6": 3, "C-P9.avail": 0.9, "C-P9.imp": 4000, "C-H1": 0.05, "C-H2": 0.3, "C-W2": 0.05, "C-W3": 10,
            "C-T2": 0.9, "C-T5": 0.5, "C-B1": 12, "C-B2": 4, "C-B3": 22.5, "C-B4": 0.94, "C-H10": 28,
            "C-H11": 4e-6, "C-H11.a": 0.0086, "C-H12": 2, "C-H13": 0.05, "C-H14": 0.75, "C-H15": 1000, "C-H16": 30, "C-H17": 26}
    assert set(base) >= set(CORE_PARAMS)
    return {k: np.full(n, float(v)) * (1 + 0.05 * rng.standard_normal(n) * (k in ("C-P1.Kd", "C-P3"))) for k, v in base.items()}


def run(off=frozenset(), seed=7, shed=None, lineb=True, hot=True):
    net = FakeNet()
    t = np.arange(H)
    Ta = 30 + 6 * np.sin((t - 9) / 24 * 2 * np.pi)
    day = ((t % 24) >= 8) & ((t % 24) < 20)
    lb = {"nh_res": np.array([100.0]), "zone_dep": np.array([10.0, 20.0, 30.0]), "day": t // 24} if lineb else None
    return simulate_core(net, Ta, params(hot=hot), np.random.default_rng(seed), day, shed=shed, off=frozenset(off), lineb=lb)


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
    ("R11", ["hospital_hours", "nursing_hours"], ["pop_hours", "signal_dark_hours"]),
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
    """【中文】关掉供电依赖后，只有自身失效的站停电，停电人·小时不会增加。"""
    assert tot(run(off={"R08"}), "pop_hours").mean() <= tot(run(), "pop_hours").mean()


def test_every_knockout_is_handled():
    for ko in KNOCKOUTS:
        run(off={ko})                            # 【中文】每个开关都能运行 / every switch runs


def test_waiting_monotonic_and_zero_at_baseline():
    th = params()
    base = {"totals": {"peak_day_extra_visits": np.zeros(N), "peak_day_open_share": np.ones(N)}}
    np.testing.assert_allclose(waiting(base, th), 0, atol=1e-9)
    w = [waiting({"totals": {"peak_day_extra_visits": np.full(N, x), "peak_day_open_share": np.ones(N)}}, th).mean()
         for x in (0, 10, 50, 200)]
    assert all(b >= a for a, b in zip(w, w[1:]))
    assert waiting(base, th, off={"R22"}).sum() == 0


def test_line_b_outputs_present():
    r = run()
    for k in ("heat_visits_excess", "dep_visits", "nh_exposed_hours", "peak_day_extra_visits", "peak_day_open_share"):
        assert k in r["totals"]
    assert (r["totals"]["peak_day_open_share"] <= 1).all() and (r["totals"]["peak_day_open_share"] >= 0).all()
