"""
【中文】所有数据集适配器的基类。每个 adapter 负责一个数据集：
    extract()  读取原始数据
    transform() 转换成标准表 / 网页静态文件
新增数据类型时，继承 DatasetAdapter 并在 pipeline/adapters/__init__.py 里注册。

Base class for dataset adapters. Each adapter handles one dataset:
    extract()   reads the raw input
    transform() writes standard tables and static web files
To support a new kind of data, subclass DatasetAdapter and register it.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
from matplotlib import colormaps
from matplotlib.colors import to_hex


@dataclass
class BuildContext:
    """【中文】构建时共享的路径与项目配置 / shared paths and project config."""
    root: Path
    aoi: list[float]                      # [west, south, east, north] in EPSG:4326
    raw_dir: Path
    standard_dir: Path
    site_data_dir: Path
    project: dict = field(default_factory=dict)
    force: bool = False
    fingerprints: dict = field(default_factory=dict)   # dataset id → fingerprint of its last build

    def load_assets(self, source_id: str) -> gpd.GeoDataFrame:
        """【中文】读取上游数据集写出的 assets 表 / read the assets written by an upstream dataset."""
        f = self.standard_dir / "assets" / f"{source_id}.parquet"
        if not f.exists():
            raise FileNotFoundError(f"upstream dataset '{source_id}' has no assets yet; build it first")
        return gpd.read_parquet(f)


@dataclass
class AdapterResult:
    """【中文】adapter 的输出：网页图层配置 + 标准表行。tables 的键是标准表名。
    Layer config + standard table rows; `tables` maps a table name
    (assets / exposures / events / dependencies / couplings) to a DataFrame."""
    layer: dict | None = None                       # entry for site/data/layers.json
    tables: dict = field(default_factory=dict)


class DatasetAdapter:
    kind: str = ""

    def __init__(self, cfg: dict, ctx: BuildContext):
        self.cfg = cfg
        self.ctx = ctx
        self.id = cfg["id"]

    # ------------------------------------------------------------------ paths
    @property
    def raw_path(self) -> Path:
        return self.ctx.raw_dir / self.cfg["file"]

    def input_files(self) -> list[Path]:
        """【中文】原始输入文件；多文件数据集（如逐小时序列）覆盖这里 / raw input files."""
        p = self.raw_path
        if p.suffix == ".shp":  # 【中文】shapefile 的配套文件也算输入 / sidecar files count too
            return sorted(f for f in p.parent.glob(p.stem + ".*") if f.suffix != ".fix")
        return [p]

    def has_inputs(self) -> bool:
        files = self.input_files()
        return bool(files) and all(f.exists() for f in files)

    def upstream(self) -> list[str]:
        """【中文】依赖的上游数据集 id（读取它们的 assets）/ upstream dataset ids."""
        return []

    def site_path(self, sub: str, suffix: str) -> Path:
        p = self.ctx.site_data_dir / sub / f"{self.id}{suffix}"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def standard_path(self, sub: str, suffix: str) -> Path:
        p = self.ctx.standard_dir / sub / f"{self.id}{suffix}"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def fingerprint(self) -> str:
        """【中文】输入指纹 = 本条配置 + 原始文件（大小、修改时间）+ adapter 代码 + 上游指纹。
        指纹不变就跳过；上游数据集重建后，下游自动重算（设计方案第 4 节第 6 步）。

        Fingerprint of this dataset's config, raw files, adapter code and upstream
        fingerprints. Unchanged → skip; a rebuilt upstream triggers a rebuild here."""
        h = hashlib.sha256()
        h.update(json.dumps(self.cfg, sort_keys=True, default=str).encode())
        h.update(json.dumps(self.ctx.project, sort_keys=True, default=str).encode())
        for f in self.input_files():
            st = f.stat()
            h.update(f"{f.name}:{st.st_size}:{int(st.st_mtime)}".encode())
        # 【中文】adapter 所在模块（含基类）的源码也算输入 / adapter module code counts too
        files = {inspect.getsourcefile(c) for c in type(self).__mro__ if c.__module__.startswith("pipeline.")}
        # 【中文】adapter 调用的其他模块（如 twin/rules.py）在 code_modules 里声明 / extra modules it calls
        files |= {inspect.getsourcefile(m) for m in getattr(self, "code_modules", ())}
        for path in sorted(files):
            h.update(Path(path).read_bytes())
        for up in self.upstream():
            h.update(f"{up}:{self.ctx.fingerprints.get(up, 'missing')}".encode())
        return h.hexdigest()[:16]

    def is_up_to_date(self, outputs: list[Path], cached_fingerprint: str | None) -> bool:
        """【中文】指纹相同且输出都在就跳过（增量构建）/ skip when nothing changed."""
        if self.ctx.force or not all(o.exists() for o in outputs):
            return False
        return cached_fingerprint == self.fingerprint()

    # ------------------------------------------------------------------ API
    def extract(self):
        raise NotImplementedError

    def transform(self, raw) -> AdapterResult:
        raise NotImplementedError

    def run(self) -> AdapterResult:
        return self.transform(self.extract())

    # ------------------------------------------------------------------ shared
    def base_layer(self) -> dict:
        """【中文】所有图层共有的字段 / fields every layer entry has."""
        c = self.cfg
        return {
            "id": self.id,
            "kind": self.kind,
            "title": c.get("title", self.id),
            "group": c.get("group", "Other"),
            "visible": bool(c.get("visible", False)),
            "opacity": float(c.get("opacity", 1.0)),
            "source_id": self.id,
        }


def ramp_stops(cmap_name: str, n: int = 9) -> list[str]:
    """【中文】把 matplotlib 色带取样成 n 个 hex 颜色 / sample a colormap into n hex colors."""
    cmap = colormaps[cmap_name]
    return [to_hex(cmap(i / (n - 1))) for i in range(n)]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 【中文】NaN / Inf 不是合法 JSON，统一写成 null / NaN and Inf become null (valid JSON)
    path.write_text(json.dumps(_clean(obj), ensure_ascii=False, indent=1, default=_json_default, allow_nan=False),
                    encoding="utf-8")


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    return o


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    raise TypeError(type(o))
