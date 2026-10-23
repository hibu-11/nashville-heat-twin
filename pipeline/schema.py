"""
【中文】六张标准表的 schema 与自动校验（设计方案第 3、4 节）。
所有 adapter 的输出都要先过这里的检查，核心模型只读通过校验的标准表。
存储 CRS 统一为 EPSG:32616，只在导出网页文件时转为 EPSG:4326 / 3857。

Standard table schemas and automatic checks (design sections 3–4).
Storage CRS is EPSG:32616; only web exports are reprojected.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

STORE_CRS = 32616

# 【中文】列名 → (类型, 是否必填)。类型：str / float / time / geom
# column → (type, required). Extra columns are allowed and kept.
TABLES: dict[str, dict[str, tuple[str, bool]]] = {
    "assets": {
        "asset_id": ("str", True), "system": ("str", True), "asset_type": ("str", True),
        "geometry": ("geom", True), "attributes": ("str", False),
        "valid_from": ("time", False), "valid_to": ("time", False), "source_id": ("str", True),
    },
    "dependencies": {
        "from_asset": ("str", True), "to_asset": ("str", True), "dep_type": ("str", True),
        "coupling_id": ("str", False), "valid_from": ("time", False), "valid_to": ("time", False),
        "source_id": ("str", True),
    },
    "couplings": {
        "coupling_id": ("str", True), "driver": ("str", True), "response": ("str", True),
        "functional_form": ("str", True), "param_low": ("float", True), "param_mid": ("float", True),
        "param_high": ("float", True), "citation": ("str", True), "source_id": ("str", True),
    },
    "exposures": {
        # 【中文】time_end 为空表示瞬时值（逐小时）；合成期写起止时间
        # time_end empty = instantaneous (hourly); composites carry a start/end
        "asset_id": ("str", True), "timestamp": ("time", True), "time_end": ("time", False),
        "lst_mean": ("float", True), "lst_max": ("float", False), "lst_source": ("str", True),
        "quality_flag": ("str", True), "source_id": ("str", True),
    },
    "events": {
        "event_id": ("str", True), "asset_id": ("str", False), "geometry": ("geom", True),
        "event_type": ("str", True), "start_time": ("time", True), "end_time": ("time", False),
        "severity": ("float", False), "attributes": ("str", False), "source_id": ("str", True),
    },
    "sources": {
        "source_id": ("str", True), "name": ("str", True), "provider": ("str", False),
        "license": ("str", False), "version": ("str", False), "retrieved_date": ("str", False),
        "temporal_res": ("str", False), "spatial_res": ("str", False), "quality_rank": ("float", False),
    },
}
GEO_TABLES = {t for t, cols in TABLES.items() if "geometry" in cols}
ID_COLUMN = {"assets": "asset_id", "couplings": "coupling_id", "events": "event_id", "sources": "source_id"}
TIME_PAIRS = {"assets": ("valid_from", "valid_to"), "dependencies": ("valid_from", "valid_to"),
              "exposures": ("timestamp", "time_end"), "events": ("start_time", "end_time")}


def empty(table: str) -> pd.DataFrame:
    """【中文】按 schema 生成空表，保证六张表始终存在 / empty table with the right columns."""
    cols = {c: pd.Series(dtype=_dtype(t)) for c, (t, _) in TABLES[table].items() if t != "geom"}
    df = pd.DataFrame(cols)
    if table in GEO_TABLES:
        return gpd.GeoDataFrame(df, geometry=gpd.GeoSeries([], crs=STORE_CRS), crs=STORE_CRS)
    return df


def conform(table: str, df: pd.DataFrame) -> pd.DataFrame:
    """【中文】补齐缺失列、统一类型；不删除额外列 / add missing columns, coerce types, keep extras."""
    df = df.copy()
    for col, (typ, _) in TABLES[table].items():
        if typ == "geom":
            continue
        if col not in df:
            df[col] = pd.Series(index=df.index, dtype=_dtype(typ))
        elif typ == "time":
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
        elif typ == "float":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        else:
            df[col] = df[col].astype("string")
    order = [c for c in TABLES[table] if c in df] + [c for c in df.columns if c not in TABLES[table]]
    df = df[order]
    if table in GEO_TABLES:
        df = gpd.GeoDataFrame(df, geometry="geometry", crs=getattr(df, "crs", None))
    return df


def _dtype(typ: str):
    return {"str": "string", "float": "float64", "time": "datetime64[ns, UTC]"}[typ]


# ---------------------------------------------------------------------- checks
def validate(tables: dict[str, pd.DataFrame], time_range: tuple[str, str] | None = None) -> list[dict]:
    """【中文】自动校验：必填字段、CRS、几何有效性、时间范围、ID 重复、外键。
    返回问题列表，每条 {table, level, check, message, n}；level 为 error 或 warn。

    Checks required fields, CRS, geometry validity, time ranges, duplicate ids and
    foreign keys. Returns a list of issues."""
    issues: list[dict] = []

    def add(table, level, check, message, n):
        if n:
            issues.append({"table": table, "level": level, "check": check, "message": message, "n": int(n)})

    for name, df in tables.items():
        spec = TABLES[name]
        missing = [c for c in spec if c not in df.columns]
        add(name, "error", "columns", f"missing columns: {missing}", len(missing))
        for col, (typ, required) in spec.items():
            if required and col in df and typ != "geom":
                add(name, "error", "required", f"{col} is null", df[col].isna().sum())

        if name in GEO_TABLES and len(df):
            crs = df.crs.to_epsg() if df.crs else None
            add(name, "error", "crs", f"CRS should be EPSG:{STORE_CRS}, got {crs}", int(crs != STORE_CRS))
            geom = df.geometry
            add(name, "error", "geometry", "empty geometry", (geom.isna() | geom.is_empty).sum())
            add(name, "warn", "geometry", "invalid geometry", (~geom.is_valid).sum())

        if name in ID_COLUMN and ID_COLUMN[name] in df:
            add(name, "error", "unique", f"duplicate {ID_COLUMN[name]}",
                df[ID_COLUMN[name]].duplicated().sum())
        if name == "exposures" and len(df):
            key = ["asset_id", "timestamp", "lst_source"]
            add(name, "error", "unique", "duplicate (asset_id, timestamp, lst_source)", df.duplicated(key).sum())

        if name in TIME_PAIRS and len(df):
            a, b = TIME_PAIRS[name]
            if a in df and b in df:
                add(name, "error", "time", f"{b} before {a}", (df[b] < df[a]).sum())
            if time_range and a in df:
                lo, hi = (pd.Timestamp(t, tz="UTC") for t in time_range)
                add(name, "warn", "time", f"{a} outside project time range {time_range[0]}–{time_range[1]}",
                    ((df[a] < lo) | (df[a] > hi)).sum())

    # 【中文】外键 / foreign keys
    asset_ids = set(tables["assets"]["asset_id"].dropna()) if "assets" in tables else set()
    for name, cols in {"exposures": ["asset_id"], "events": ["asset_id"],
                       "dependencies": ["from_asset", "to_asset"]}.items():
        df = tables.get(name)
        for col in cols:
            if df is not None and col in df and len(df):
                v = df[col].dropna()
                add(name, "error", "foreign_key", f"{col} not found in assets", (~v.isin(asset_ids)).sum())
    dep, cpl = tables.get("dependencies"), tables.get("couplings")
    if dep is not None and cpl is not None and len(dep):
        v = dep["coupling_id"].dropna()
        add("dependencies", "error", "foreign_key", "coupling_id not found in couplings",
            (~v.isin(set(cpl["coupling_id"]))).sum())
    return issues
