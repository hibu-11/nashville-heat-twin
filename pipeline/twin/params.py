"""
【中文】耦合参数：从标准表 couplings 读取 low / mid / high，按三角分布抽样（学术手册 Eq. 12）。
Coupling parameters from the standard couplings table; triangular sampling (handbook Eq. 12).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class Params:
    def __init__(self, couplings: pd.DataFrame):
        c = couplings.set_index("coupling_id")
        self.table = c
        self.low = c["param_low"].astype(float).to_dict()
        self.mid = c["param_mid"].astype(float).to_dict()
        self.high = c["param_high"].astype(float).to_dict()

    def sample(self, n: int, rng: np.random.Generator, mode: str = "mc") -> dict[str, np.ndarray]:
        """【中文】每个参数抽 n 个值；mode = "mid" 时全部取中值（确定性基准情景）。
        Draw n values per parameter: triangular(low, mid, high); "mid" = deterministic baseline.

            θ ~ Tri(a = low, c = mid, b = high)          (Eq. 12)
        """
        out = {}
        for k in self.mid:
            a, c, b = self.low[k], self.mid[k], self.high[k]
            if mode == "mid" or a == b:
                out[k] = np.full(n, c)
            else:
                out[k] = rng.triangular(a, c, b, size=n)
        return out

    def __getitem__(self, k):
        return self.mid[k]
