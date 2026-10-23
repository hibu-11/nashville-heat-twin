"""
【中文】表格适配器：CSV / Parquet → 一张非空间标准表（couplings 或 dependencies）。
耦合参数（文献整理的 param_low / mid / high）和依赖边通常以表格形式整理，
列名可以通过 columns 映射到标准字段。模板见 templates/。

Table adapter: CSV / Parquet → one non-spatial standard table (couplings or
dependencies). Map source column names to standard fields with `columns`.
Templates live in templates/.
"""
from __future__ import annotations

import pandas as pd

from .base import AdapterResult, DatasetAdapter

TARGETS = ("couplings", "dependencies")


class TableAdapter(DatasetAdapter):
    kind = "table"

    def outputs(self):
        return []

    def extract(self):
        p = self.raw_path
        return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, comment="#")

    def transform(self, df: pd.DataFrame) -> AdapterResult:
        target = self.cfg.get("target_table")
        if target not in TARGETS:
            raise ValueError(f"target_table must be one of {TARGETS}, got {target!r}")
        df = df.rename(columns=self.cfg.get("columns", {}))
        df["source_id"] = self.id
        print(f"    {self.id}: {len(df)} rows → {target}")
        return AdapterResult(layer=None, tables={target: df})
