"""
【中文】时间序列适配器：
    station_series  气象站观测（IEM ASOS CSV）→ 辅助表 drivers（逐小时），网页输出逐小时数组
    outage_series   EAGLE-I 县级停电用户数（15 分钟）→ events（逐小时最大值，asset_id 为空，几何为县界）
二者都是孪生的外部驱动 / 观测，不对应某个具体资产。

Time-series adapters: station observations → drivers (hourly); EAGLE-I county
outage counts → hourly events with an empty asset_id and the county geometry.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from ..schema import STORE_CRS
from .base import AdapterResult, DatasetAdapter, write_json

F_TO_C = lambda f: (f - 32.0) * 5.0 / 9.0  # noqa: E731
KNOT_TO_MS = 0.514444


class StationSeriesAdapter(DatasetAdapter):
    """【中文】IEM ASOS 导出（onlycomma 格式）→ 逐小时 drivers / hourly drivers from an IEM ASOS export."""
    kind = "station_series"

    def outputs(self):
        return [self.site_path("drivers", ".json")]

    def extract(self):
        return pd.read_csv(self.raw_path, na_values=["M", "T"], low_memory=False)

    def transform(self, df: pd.DataFrame) -> AdapterResult:
        c = self.cfg
        (web_f,) = self.outputs()
        df = df.assign(valid=pd.to_datetime(df["valid"], utc=True))
        # 【中文】例行观测在 :53 分，归到最近的整点 / routine METARs at :53 → nearest whole hour
        df["hour"] = df["valid"].dt.round("h")
        num = {"air_temp_c": F_TO_C(pd.to_numeric(df["tmpf"], errors="coerce")),
               "dewpoint_c": F_TO_C(pd.to_numeric(df["dwpf"], errors="coerce")),
               "rh_pct": pd.to_numeric(df.get("relh"), errors="coerce"),
               "wind_ms": pd.to_numeric(df.get("sknt"), errors="coerce") * KNOT_TO_MS}
        # 【中文】天气现象含 TS（雷暴）记为 1，用于区分风暴型停电 / thunder flag to separate storm outages
        wx = df.get("wxcodes", pd.Series("", index=df.index)).fillna("").astype(str)
        num["thunder"] = wx.str.contains("TS").astype(float)
        hourly = pd.DataFrame(num).assign(hour=df["hour"]).groupby("hour").agg(
            {"air_temp_c": "mean", "dewpoint_c": "mean", "rh_pct": "mean", "wind_ms": "mean", "thunder": "max"})
        full = pd.date_range(hourly.index.min(), hourly.index.max(), freq="h", tz="UTC")
        hourly = hourly.reindex(full)
        # 【中文】短缺口（≤ 3 小时）线性插值，并记录插值数 / fill gaps ≤ 3 h linearly
        n_missing = int(hourly["air_temp_c"].isna().sum())
        hourly[["air_temp_c", "dewpoint_c", "rh_pct", "wind_ms"]] = hourly[
            ["air_temp_c", "dewpoint_c", "rh_pct", "wind_ms"]].interpolate(limit=3)
        hourly["thunder"] = hourly["thunder"].fillna(0)
        print(f"    {self.id}: {len(hourly)} hours, {n_missing} hours interpolated or missing")

        units = {"air_temp_c": "degC", "dewpoint_c": "degC", "rh_pct": "%", "wind_ms": "m/s", "thunder": "flag"}
        long = (hourly.rename_axis("timestamp").reset_index()
                .melt(id_vars="timestamp", var_name="variable", value_name="value").dropna(subset=["value"]))
        long = long.assign(station_id=c.get("station_id", "BNA"), units=long["variable"].map(units), source_id=self.id)

        write_json(web_f, {"station": c.get("station_id", "BNA"), "start": full[0].strftime("%Y-%m-%dT%H:%MZ"),
                           "step_hours": 1, "n": len(full),
                           **{k: [None if pd.isna(v) else round(float(v), 2) for v in hourly[k]] for k in units}})
        return AdapterResult(layer=None, tables={"drivers": long})


class OutageSeriesAdapter(DatasetAdapter):
    """【中文】EAGLE-I 县级停电用户数 → 逐小时 events / EAGLE-I county outages → hourly events."""
    kind = "outage_series"

    def input_files(self):
        return [self.raw_path, self.ctx.raw_dir / self.cfg["region_file"]]

    def outputs(self):
        return [self.site_path("events", "_hourly.json")]

    def extract(self):
        c = self.cfg
        parts = []
        # 【中文】全国文件约 1.2 GB，分块读取并只保留目标县；停电列在 2023 年文件里叫 sum，其他年份 / 提取文件叫 customers_out
        # read in chunks, keep one county; the outage column is "sum" in the 2023 national file, "customers_out" elsewhere
        col = "customers_out" if "customers_out" in pd.read_csv(self.raw_path, nrows=0).columns else "sum"
        for chunk in pd.read_csv(self.raw_path, usecols=["fips_code", col, "run_start_time"], chunksize=2_000_000):
            parts.append(chunk[chunk["fips_code"] == int(c["fips"])])
        return pd.concat(parts, ignore_index=True).rename(columns={col: "sum"})

    def transform(self, df: pd.DataFrame) -> AdapterResult:
        c = self.cfg
        (web_f,) = self.outputs()
        # 【中文】EAGLE-I 时间按 UTC 处理（见学术手册 §2.2 的假设 A-D1）/ treated as UTC (assumption A-D1)
        t = pd.to_datetime(df["run_start_time"], utc=True)
        s = df.assign(hour=t.dt.floor("h")).groupby("hour")["sum"].max()
        lo, hi = c.get("period", [str(s.index.min().date()), str(s.index.max().date())])
        full = pd.date_range(pd.Timestamp(lo, tz="UTC"), pd.Timestamp(hi, tz="UTC") + pd.Timedelta(hours=23), freq="h")
        s = s.reindex(full)
        print(f"    {self.id}: {int(s.notna().sum())} of {len(full)} hours have outage reports, "
              f"peak {int(s.max())} customers")

        region = gpd.read_parquet(self.ctx.raw_dir / c["region_file"]).to_crs(STORE_CRS)
        geom = region.geometry.union_all() if hasattr(region.geometry, "union_all") else region.unary_union
        rep = s.dropna()
        ev = gpd.GeoDataFrame({
            "event_id": [f"{self.id}:{h:%Y%m%dT%H}" for h in rep.index],
            "asset_id": pd.Series(pd.NA, index=range(len(rep)), dtype="string"),
            "event_type": c.get("event_type", "power_outage_customers"),
            "start_time": rep.index, "end_time": rep.index + pd.Timedelta(hours=1),
            "severity": rep.values.astype(float),
            "attributes": f'{{"fips": "{c["fips"]}", "metric": "max customers out in hour"}}',
            "source_id": self.id,
        }, geometry=[geom] * len(rep), crs=STORE_CRS)

        write_json(web_f, {"fips": str(c["fips"]), "start": full[0].strftime("%Y-%m-%dT%H:%MZ"), "step_hours": 1,
                           "n": len(full), "customers_out": [None if pd.isna(v) else int(v) for v in s.values],
                           "customers_total": c.get("customers_total")})
        return AdapterResult(layer=None, tables={"events": ev})


class TrafficCountAdapter(DatasetAdapter):
    """【中文】FHWA TMAS 逐小时计数（twin_demo 的长表：按站 / 方向 / 车道）→ drivers，
    每站每小时合计为双向总流量 volume_vph（veh/h）。station_id = TMAS 站号。
    FHWA TMAS hourly counts → drivers; lanes and directions summed per station and hour."""
    kind = "traffic_counts"

    def outputs(self):
        return [self.site_path("drivers", ".json")]

    def extract(self):
        return pd.read_parquet(self.raw_path)

    def transform(self, df: pd.DataFrame) -> AdapterResult:
        (web_f,) = self.outputs()
        df = df[df["metric"] == "hourly_volume"]
        v = df.groupby(["system_id", "time_utc"])["value"].sum().reset_index()
        drv = pd.DataFrame({"station_id": v["system_id"], "timestamp": pd.to_datetime(v["time_utc"], utc=True),
                            "variable": "volume_vph", "value": v["value"].astype(float), "units": "veh/h",
                            "source_id": self.id})
        print(f"    {self.id}: {drv['station_id'].nunique()} stations, {len(drv):,} station-hours")
        prof = (drv.assign(h=drv["timestamp"].dt.tz_convert(self.ctx.project.get("timezone", "UTC")).dt.hour)
                .groupby(["station_id", "h"])["value"].mean().unstack())
        write_json(web_f, {"stations": list(prof.index), "mean_by_local_hour": prof.round(1).values.tolist()})
        return AdapterResult(layer=None, tables={"drivers": drv})
