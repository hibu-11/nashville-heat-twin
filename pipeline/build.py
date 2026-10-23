"""
【中文】构建入口：读取 datasets.yaml → 逐个运行 adapter → 生成
    data/standard/   六张标准表（GeoParquet，EPSG:32616）+ 标准栅格 + 校验报告 + run 清单
    site/data/       网站静态文件 + layers.json + sources.json + build.json
增量构建：数据集的输入指纹（配置、原始文件、adapter 代码、上游指纹）不变就跳过；
上游重建后下游自动重算；缺少原始文件的数据集保留上次结果。

Build entry point. Usage:
    python -m pipeline.build [--force] [--strict] [--only ID [ID ...]] [--config datasets.yaml]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
import traceback
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

from . import schema
from .adapters import REGISTRY
from .adapters.base import BuildContext, write_json
from .analysis import chain_check

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIELDS = ["provider", "license", "version", "temporal_res", "spatial_res", "quality_rank",
                 "system", "coverage", "drive_url"]
PRIVATE_FIELDS = {"drive_url"}   # 【中文】公开网站不暴露私有 Drive 链接 / never published
PACKAGES = ["numpy", "pandas", "geopandas", "shapely", "rasterio", "pyarrow", "pillow", "matplotlib", "pyyaml"]


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    ids = [d["id"] for d in cfg["datasets"]]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"duplicate dataset ids in datasets.yaml: {dupes}")
    for d in cfg["datasets"]:
        if d.get("kind") not in REGISTRY:
            sys.exit(f"{d['id']}: unknown kind '{d.get('kind')}', expected one of {list(REGISTRY)}")
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Nashville heat twin data")
    ap.add_argument("--config", default=str(ROOT / "datasets.yaml"))
    ap.add_argument("--only", nargs="+", help="build only these dataset ids")
    ap.add_argument("--force", action="store_true", help="ignore the cache and rebuild everything")
    ap.add_argument("--strict", action="store_true", help="exit with status 1 when validation finds errors")
    args = ap.parse_args(argv)

    config_path = Path(args.config)
    cfg = load_config(config_path)
    p = cfg["project"]
    ctx = BuildContext(
        root=ROOT, aoi=p["aoi"], force=args.force, project=p,
        raw_dir=ROOT / p.get("raw_dir", "raw"),
        standard_dir=ROOT / p.get("standard_dir", "data/standard"),
        site_data_dir=ROOT / p.get("site_data_dir", "site/data"),
    )
    cache = ctx.standard_dir / "_cache"
    cache.mkdir(parents=True, exist_ok=True)

    layers, sources, statuses = {}, {}, {}
    for d in build_order(cfg["datasets"], ctx):
        did = d["id"]
        adapter = REGISTRY[d["kind"]](d, ctx)
        cache_f = cache / f"{did}.json"
        prev = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
        ctx.fingerprints[did] = prev.get("fingerprint")
        table_files = [ctx.standard_dir / t / f"{did}.parquet" for t in prev.get("tables", [])]
        # 【中文】上次失败且输入没变就不重试 / don't retry a failure whose inputs have not changed
        fail_f = cache / f"{did}.failed.json"
        failed = json.loads(fail_f.read_text(encoding="utf-8")) if fail_f.exists() else {}

        if args.only and did not in args.only:
            status = "cached"
        elif not adapter.has_inputs():
            print(f"[missing] {did}: input not found under {adapter.raw_path.relative_to(ROOT)}")
            if d.get("drive_url"):
                print(f"          download it into raw/ from: {d['drive_url']}")
            status = "missing"
        elif adapter.is_up_to_date(adapter.outputs() + table_files, prev.get("fingerprint")):
            print(f"[skip]    {did}: up to date")
            status = "cached"
        elif not args.force and failed.get("fingerprint") == adapter.fingerprint():
            print(f"[failed]  {did}: {failed['error']} (inputs unchanged since the last attempt; --force retries)")
            status = "failed"
        else:
            print(f"[build]   {did} ({d['kind']}) …")
            try:
                fp = adapter.fingerprint()
                res = adapter.run()
                written = write_tables(ctx, did, res.tables)
                prev = {"fingerprint": fp, "layer": res.layer, "tables": written,
                        "built_at": dt.datetime.now().isoformat(timespec="seconds")}
                write_json(cache_f, prev)
                fail_f.unlink(missing_ok=True)
                ctx.fingerprints[did] = fp
                print(f"          done ({', '.join(f'{t}: {n:,}' for t, n in written.items()) or 'no tables'})")
                status = "built"
            except Exception as e:  # noqa: BLE001 — keep building the rest
                traceback.print_exc()
                print(f"[failed]  {did}: {e}")
                write_json(fail_f, {"fingerprint": adapter.fingerprint(), "error": str(e),
                                    "at": dt.datetime.now().isoformat(timespec="seconds")})
                status = "failed"

        if not prev.get("fingerprint") and status != "failed":
            status = "not built" if status == "cached" else status
        statuses[did] = status
        if prev.get("layer"):
            layers[did] = prev["layer"]
        sources[did] = source_row(d, adapter, status, prev)

    # 【中文】图层面板和来源表按登记顺序 / panel and sources follow registry order
    ids = [d["id"] for d in cfg["datasets"]]
    layers = [layers[i] for i in ids if i in layers]
    sources = [sources[i] for i in ids]

    # ---------------------------------------------------- combined standard tables
    tables = {t: combine(ctx, t, ids) for t in schema.TABLES if t != "sources"}
    tables["sources"] = schema.conform("sources", pd.DataFrame(sources))
    for t, df in tables.items():
        df.to_parquet(ctx.standard_dir / f"{t}.parquet")

    issues = schema.validate(tables, tuple(p["time_range"]) if p.get("time_range") else None)
    n_err = sum(i["level"] == "error" for i in issues)
    n_warn = sum(i["level"] == "warn" for i in issues)
    print("\nvalidation:", "no issues" if not issues else f"{n_err} error(s), {n_warn} warning(s)")
    for i in issues:
        print(f"  [{i['level']}] {i['table']}.{i['check']}: {i['message']} ({i['n']:,} rows)")

    chain = chain_check(tables, p)
    if chain is not None:
        write_json(ctx.site_data_dir / "analysis" / "chain_check.json", chain)

    # ---------------------------------------------------- run manifest / 可复现记录
    built_at = dt.datetime.now(dt.timezone.utc)
    counts = {t: int(len(df)) for t, df in tables.items()}
    run = {
        "built_at": built_at.isoformat(timespec="seconds"),
        "code_version": code_version(),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest()[:16],
        "python": platform.python_version(),
        "packages": {k: pkg_version(k) for k in PACKAGES},
        "datasets": {d["id"]: {"status": statuses[d["id"]], "fingerprint": ctx.fingerprints.get(d["id"])}
                     for d in cfg["datasets"]},
        "tables": counts,
        "validation": {"errors": n_err, "warnings": n_warn, "issues": issues},
        "chain_check": bool(chain and chain.get("ok")),
    }
    run_hash = hashlib.sha256(json.dumps([run["code_version"], run["config_sha256"], run["datasets"]],
                                         sort_keys=True).encode()).hexdigest()[:8]
    run["run_id"] = f"{built_at:%Y%m%dT%H%M%SZ}-{run_hash}"
    private = run | {"inputs": input_hashes(cache, cfg, ctx)}
    write_json(ctx.standard_dir / "runs" / f"{run['run_id']}.json", private)
    write_json(ctx.standard_dir / "validation.json", {"run_id": run["run_id"], "issues": issues})

    # ---------------------------------------------------- site manifests
    stamp = built_at.isoformat(timespec="minutes")
    write_json(ctx.site_data_dir / "layers.json",
               {"project": p["name"], "aoi": p["aoi"], "built_at": stamp, "run_id": run["run_id"],
                "timezone": p.get("timezone", "UTC"), "heatwave": p.get("heatwave"),
                "baseline": p.get("baseline"), "layers": layers})
    public = [{k: v for k, v in s.items() if k not in PRIVATE_FIELDS} for s in sources]
    write_json(ctx.site_data_dir / "sources.json", {"built_at": stamp, "run_id": run["run_id"], "sources": public})
    write_json(ctx.site_data_dir / "build.json", run)

    print(f"\nrun {run['run_id']} · layers: {len(layers)} · "
          + " · ".join(f"{t}: {n:,}" for t, n in counts.items()))
    unfinished = [s for s, st in statuses.items() if st in ("missing", "failed", "not built")]
    if unfinished:
        print(f"not built: {', '.join(unfinished)}")
    if args.strict and n_err:
        sys.exit(1)


# ---------------------------------------------------------------------- helpers
def build_order(datasets: list[dict], ctx: BuildContext) -> list[dict]:
    """【中文】按依赖排序（上游先建），其余保持登记顺序 / upstream first, otherwise registry order."""
    by_id = {d["id"]: d for d in datasets}
    ups = {d["id"]: REGISTRY[d["kind"]](d, ctx).upstream() for d in datasets}
    for did, us in ups.items():
        for u in us:
            if u not in by_id:
                sys.exit(f"{did} depends on '{u}', which is not in datasets.yaml")
    order, state = [], {}

    def visit(did, path):
        if state.get(did) == "done":
            return
        if state.get(did) == "visiting":
            sys.exit(f"dependency cycle: {' → '.join(path + [did])}")
        state[did] = "visiting"
        for u in ups[did]:
            visit(u, path + [did])
        state[did] = "done"
        order.append(by_id[did])

    for d in datasets:
        visit(d["id"], [])
    return order


def write_tables(ctx: BuildContext, did: str, produced: dict) -> dict:
    """【中文】写出本数据集的标准表分片，删除不再产出的旧分片 / write this dataset's table parts."""
    written = {}
    for t in schema.TABLES:
        f = ctx.standard_dir / t / f"{did}.parquet"
        df = produced.get(t)
        if df is None or len(df) == 0:
            f.unlink(missing_ok=True)
            continue
        df = schema.conform(t, df)
        if t in schema.GEO_TABLES and df.crs is not None and df.crs.to_epsg() != schema.STORE_CRS:
            df = df.to_crs(schema.STORE_CRS)
        f.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(f)
        written[t] = int(len(df))
    return written


def combine(ctx: BuildContext, table: str, ids: list[str]) -> pd.DataFrame:
    """【中文】合并当前登记的数据集的分片；没有分片时返回空表 / concat parts of listed datasets."""
    parts = [ctx.standard_dir / table / f"{i}.parquet" for i in ids]
    parts = [f for f in parts if f.exists()]
    if not parts:
        return schema.empty(table)
    geo = table in schema.GEO_TABLES
    frames = [gpd.read_parquet(f) if geo else pd.read_parquet(f) for f in parts]
    if geo:
        frames = [g.to_crs(schema.STORE_CRS) for g in frames]
    df = pd.concat(frames, ignore_index=True)
    if geo:
        df = gpd.GeoDataFrame(df, geometry="geometry", crs=schema.STORE_CRS)
    return schema.conform(table, df)


def source_row(d: dict, adapter, status: str, prev: dict) -> dict:
    """【中文】sources 表的一行（设计方案第 3 节）/ one row of the sources table."""
    files = [f for f in adapter.input_files() if f.exists()] if adapter.has_inputs() else []
    file_date = dt.date.fromtimestamp(max(f.stat().st_mtime for f in files)).isoformat() if files else None
    row = {
        "source_id": d["id"], "name": d.get("title", d["id"]), "kind": d["kind"],
        "target_tables": ",".join(prev.get("tables", {})) or None,
        "file": d.get("file") or d.get("dir"), "n_files": len(files),
        "retrieved_date": str(d["retrieved_date"]) if d.get("retrieved_date") else file_date,
        "status": status, "built_at": prev.get("built_at"),
    }
    for k in SOURCE_FIELDS:
        v = d.get(k)
        row[k] = v if k == "quality_rank" or v is None else str(v)
    return row


def code_version() -> str:
    """【中文】项目是 git 仓库时用 commit，否则用 pipeline 源码哈希 / git commit, else a source hash."""
    try:
        top = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
        if Path(top).resolve() == ROOT:
            sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, check=True).stdout.strip()
            dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "pipeline"],
                                   capture_output=True, text=True).stdout.strip()
            return f"git:{sha}{'-dirty' if dirty else ''}"
    except (OSError, subprocess.CalledProcessError):
        pass
    h = hashlib.sha256()
    for f in sorted((ROOT / "pipeline").rglob("*.py")):
        h.update(f.read_bytes())
    return f"src:{h.hexdigest()[:12]}"


def pkg_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def input_hashes(cache: Path, cfg: dict, ctx: BuildContext) -> dict:
    """【中文】原始文件 sha256（按大小+修改时间缓存）/ sha256 of raw inputs, cached by size + mtime."""
    store_f = cache / "hashes.json"
    known = json.loads(store_f.read_text(encoding="utf-8")) if store_f.exists() else {}
    out = {}
    for d in cfg["datasets"]:
        adapter = REGISTRY[d["kind"]](d, ctx)
        rows = []
        for f in adapter.input_files():
            if not f.exists():
                continue
            st = f.stat()
            key = f"{f}:{st.st_size}:{int(st.st_mtime)}"
            if key not in known:
                known[key] = hashlib.sha256(f.read_bytes()).hexdigest()
            rows.append({"file": f.name, "bytes": st.st_size, "sha256": known[key]})
        out[d["id"]] = rows
    write_json(store_f, known)
    return out


if __name__ == "__main__":
    main()
