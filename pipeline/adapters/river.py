"""
【中文】河水温度与火电冷却适配器（kind: river_thermal，方法见 pipeline/twin/river.py 与 PIPELINE_SPEC M-18）。
构建时做与参数无关的部分：拟合河温模型、找出直流冷却电厂、整理逐小时的河温 / 流量 / TVA 负荷。
与参数有关的降额和轮流停电（C-P9.*）在级联模拟里按每次运行的抽样计算。输出：
    data/standard/river/<id>_hourly.parquet   timestamp (UTC), ta7_c, tw_c, q_cfs, load_mw
    data/standard/river/<id>_model.json       河温模型、电厂清单、系统容量、数据覆盖
    site/data/twin/river.json                 网页用的日序列

River-temperature / thermal-cooling adapter. Builds the parameter-free inputs of M-18; the
parameter-dependent derate and load shed are computed per run in the cascade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..twin import river
from .base import AdapterResult, DatasetAdapter, write_json


class RiverThermalAdapter(DatasetAdapter):
    kind = "river_thermal"
    code_modules = (river,)

    def input_files(self):
        c = self.cfg
        return [self.ctx.raw_dir / c[k] for k in ("tdec_file", "usgs_file", "asos_file", "eia860_file", "eia930_file")]

    def outputs(self):
        return [self.standard_path("river", "_hourly.parquet"), self.standard_path("river", "_model.json"),
                self.ctx.site_data_dir / "twin" / "river.json"]

    def extract(self):
        return None

    def transform(self, _) -> AdapterResult:
        c, raw = self.cfg, self.ctx.raw_dir
        tz = self.ctx.project.get("timezone", "UTC")
        hourly_f, model_f, web_f = self.outputs()

        # 【中文】1) 河温模型：TDEC 干流采样 × BNA 前 7 天平均气温 / stream-temperature model
        s = river.tdec_mainstem(raw / c["tdec_file"], c.get("river", "Cumberland River"))
        s = s[s["county"].isin(c["counties"])]
        asos = pd.read_csv(raw / c["asos_file"], usecols=["valid", "tmpf"], na_values="M")
        ta_d = river.daily_air(asos, tz)
        model = river.fit_stream_temperature(s, ta_d, int(c.get("window_days", 7)))
        print(f"    {self.id}: stream temperature fit on {model['n_samples']} samples, RMSE {model['rmse_c']:.2f} °C, "
              f"R² {model['r2']:.2f}, asymptote {model['alpha']:.1f} °C")

        # 【中文】2) 电厂与系统容量（EIA-860）/ plants and system capacity
        plants, c_sys = river.eia860_plants(raw / c["eia860_file"], c.get("balancing_authority", "TVA"),
                                            c.get("water_body", "Cumberland"))
        print(f"    {self.id}: {len(plants)} once-through plants on the river, {plants['summer_capacity_mw'].sum():,.0f} MW "
              f"of {c_sys:,.0f} MW {c.get('balancing_authority', 'TVA')} summer capacity")

        # 【中文】3) 逐小时序列：日河温与日流量按当地日期展开到小时，负荷用 EIA-930（小时末 → 小时初）
        # hourly series: daily values spread over local hours; EIA-930 hour-ending → hour-beginning
        q = river.read_usgs_rdb(raw / c["usgs_file"])
        ta7 = ta_d.sort_index().rolling(model["window_days"], min_periods=model["window_days"] - 1).mean()
        e = pd.read_csv(raw / c["eia930_file"])
        t_end = pd.to_datetime(e["UTC Time at End of Hour"], format="mixed").dt.tz_localize("UTC")
        load = pd.Series(pd.to_numeric(e["Demand (MW)"], errors="coerce").to_numpy(), index=t_end - pd.Timedelta(hours=1))
        load = load[~load.index.duplicated()].sort_index()
        # 【中文】EIA-930 偶有异常值：超出 [0.3, 1.5] × 当日中位数的小时视为缺测 / drop implausible spikes
        med = load.groupby(load.index.date).transform("median")
        load = load.where((load > 0.3 * med) & (load < 1.5 * med))
        lo, hi = c.get("period", ["2014-01-01", "2025-12-31"])
        hours = pd.date_range(pd.Timestamp(lo, tz=tz), pd.Timestamp(hi, tz=tz) + pd.Timedelta(hours=23), freq="h").tz_convert("UTC")
        day = hours.tz_convert(tz).date
        hourly = pd.DataFrame({"timestamp": hours,
                               "ta7_c": pd.Series(day).map(ta7).to_numpy(),
                               "tw_c": river.mohseni(pd.Series(day).map(ta7).to_numpy(float), model["mu"], model["alpha"],
                                                     model["beta"], model["gamma"]),
                               "q_cfs": pd.Series(day).map(q).to_numpy(float),
                               "load_mw": load.reindex(hours).to_numpy(float)})
        hourly.to_parquet(hourly_f)

        summer = hourly[hourly["timestamp"].dt.tz_convert(tz).dt.month.isin([6, 7, 8])]
        yr = summer["timestamp"].dt.tz_convert(tz).dt.year
        by_year = {int(y): {"tw_max_c": round(float(g["tw_c"].max()), 2), "q_min_cfs": float(g["q_cfs"].min()),
                            "load_peak_mw": None if g["load_mw"].isna().all() else float(g["load_mw"].max())}
                   for y, g in summer.groupby(yr)}
        meta = {"id": self.id, "method": "PIPELINE_SPEC M-18 (Mohseni et al. 1998 stream temperature)",
                "stream_model": model, "counties": c["counties"], "excluded_note": c.get("excluded_note"),
                "plants": plants.to_dict(orient="records"),
                "plant_capacity_mw": float(plants["summer_capacity_mw"].sum()), "system_capacity_mw": c_sys,
                "summer_by_year": by_year,
                "coverage": {"load_hours": int(hourly["load_mw"].notna().sum()), "flow_days": int(q.size)}}
        write_json(model_f, meta)

        dly = hourly.assign(day=day).groupby("day").agg(tw_c=("tw_c", "first"), q_cfs=("q_cfs", "first"),
                                                       load_peak_mw=("load_mw", "max"))
        write_json(web_f, {"start": str(dly.index[0]), "n": len(dly), "tw_c": np.round(dly["tw_c"], 2).tolist(),
                           "q_cfs": dly["q_cfs"].tolist(), "load_peak_mw": dly["load_peak_mw"].tolist(),
                           "plants": meta["plants"], "plant_capacity_mw": meta["plant_capacity_mw"],
                           "system_capacity_mw": c_sys, "stream_model": {k: model[k] for k in ("mu", "alpha", "beta", "gamma",
                                                                                           "rmse_c", "r2", "n_samples")}})
        return AdapterResult(layer=None)
