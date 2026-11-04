"""
【中文】变量登记表与关系分级表的一致性检查，并生成 docs/DATA_CATALOG.md（见 docs/PIPELINE_SPEC.md §7、§9）。
    python -m pipeline.registry                # 检查 + 生成目录
    python -m pipeline.registry --check-data   # 另外检查标准表中的数值是否在 valid_min / valid_max 内
有 error 时返回 1。

Checks twin/variables.csv and twin/relations.csv against datasets.yaml, twin/couplings.csv,
twin/references.yaml and the method ids defined in docs/PIPELINE_SPEC.md, then writes
docs/DATA_CATALOG.md. Exits 1 on errors.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

STATUS = ["in_model", "ingested", "derived", "on_drive", "public", "restricted", "placeholder", "planned"]
KINDS = {"driver", "attribute", "state", "parameter", "observation", "output", "control"}
# 【中文】有数据的状态：变量的数据来源必须登记在 datasets.yaml / statuses that need a registered dataset
HAS_DATA = {"in_model", "ingested"}
SYSTEMS = ["climate", "lst", "built_environment", "power", "water", "transportation", "health", "population", "model"]
SYSTEM_LABEL = {"climate": "Climate 气象气候", "lst": "Land surface temperature 地表温度",
                "built_environment": "Built environment 建成环境", "power": "Power 电力", "water": "Water 供水",
                "transportation": "Transportation 交通", "health": "Health 健康", "population": "Population 人口",
                "model": "Model controls 模型控制"}
MARK = {"in_model": "✅", "ingested": "✅", "derived": "✅", "on_drive": "🟡", "public": "🟡",
        "restricted": "🔒", "placeholder": "⬜", "planned": "⬜"}
METHOD_RE = re.compile(r"\b([MG]-\d+)\b")


def tokens(v) -> list[str]:
    """【中文】把 'a;b; c' 拆成列表，忽略空值和 '-' / split a ';' list, dropping blanks and '-'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    return [t.strip() for t in str(v).split(";") if t.strip() and t.strip() != "-"]


def load():
    read = lambda p: pd.read_csv(ROOT / p, comment="#", dtype=str, keep_default_na=False)
    cfg = yaml.safe_load((ROOT / "datasets.yaml").read_text(encoding="utf-8"))
    spec = (ROOT / "docs/PIPELINE_SPEC.md").read_text(encoding="utf-8")
    return {
        "vars": read("twin/variables.csv"),
        "rels": read("twin/relations.csv"),
        "couplings": set(read("twin/couplings.csv")["coupling_id"]),
        "basis": dict(zip(read("twin/couplings.csv")["coupling_id"], read("twin/couplings.csv")["basis"])),
        "cite": dict(zip(read("twin/couplings.csv")["coupling_id"], read("twin/couplings.csv")["citation"])),
        "placeholder": dict(zip(read("twin/couplings.csv")["coupling_id"], read("twin/couplings.csv")["placeholder"])),
        "datasets": {d["id"] for d in cfg["datasets"]},
        "refs": set(yaml.safe_load((ROOT / "twin/references.yaml").read_text(encoding="utf-8"))),
        # 【中文】规范中定义的方法：以 "#### M-n" 或 "### G-n" 开头的标题 / methods defined as headings
        "methods": set(re.findall(r"^#{3,4} ([MG]-\d+)\b", spec, flags=re.M)),
        "project": cfg.get("project", {}),
        "core": yaml.safe_load((ROOT / "twin/core.yaml").read_text(encoding="utf-8")) if (ROOT / "twin/core.yaml").exists() else None,
    }


def check(R: dict) -> list[dict]:
    issues = []

    def add(level, where, msg):
        issues.append({"level": level, "where": where, "message": msg})

    v, r = R["vars"], R["rels"]
    var_ids = set(v["var_id"])
    for vid in v.loc[v["var_id"].duplicated(), "var_id"]:
        add("error", vid, "duplicate var_id")
    for _, row in v.iterrows():
        vid = row["var_id"]
        if row["status"] not in STATUS:
            add("error", vid, f"unknown status '{row['status']}'")
        if row["kind"] not in KINDS:
            add("error", vid, f"unknown kind '{row['kind']}'")
        if row["system"] not in SYSTEMS:
            add("error", vid, f"unknown system '{row['system']}'")
        for ds in tokens(row["source_dataset"]):
            if ds not in R["datasets"]:
                add("error", vid, f"source_dataset '{ds}' not in datasets.yaml")
        if row["status"] in HAS_DATA and row["kind"] != "control" and not tokens(row["source_dataset"]):
            add("error", vid, f"status {row['status']} but no source_dataset")
        for c in tokens(row["coupling_id"]):
            if c not in R["couplings"]:
                lvl = "error" if row["status"] in HAS_DATA else "info"
                add(lvl, vid, f"coupling {c} not in couplings.csv" + ("" if lvl == "error" else " (planned)"))
        for m in METHOD_RE.findall(row["used_in"]):
            if m not in R["methods"]:
                add("error", vid, f"{m} is not defined in docs/PIPELINE_SPEC.md")
        lo, hi = pd.to_numeric(row["valid_min"], errors="coerce"), pd.to_numeric(row["valid_max"], errors="coerce")
        if pd.notna(lo) and pd.notna(hi) and lo > hi:
            add("error", vid, "valid_min > valid_max")

    for rid, g in r.groupby("relation_id"):
        n_cur = (g["current"] == "yes").sum()
        if n_cur != 1:
            add("error", rid, f"{n_cur} rows marked current = yes (need exactly 1)")
        for t in g.loc[g["tier"].duplicated(), "tier"]:
            add("error", rid, f"duplicate tier {t}")
    for _, row in r.iterrows():
        where = f"{row['relation_id']} tier {row['tier']}"
        if not re.fullmatch(r"[0-4]s?", row["tier"]):
            add("error", where, f"tier '{row['tier']}' should be 0–4 with optional 's'")
        if row["current"] == "yes" and row["status"] != "in_model":
            add("error", where, "current tier must have status in_model")
        for x in tokens(row["inputs"]):
            if x not in var_ids:
                add("error", where, f"input {x} not in variables.csv")
        for c in tokens(row["couplings"]):
            if c not in R["couplings"]:
                lvl = "error" if row["status"] == "in_model" else "info"
                add(lvl, where, f"coupling {c} not in couplings.csv" + ("" if lvl == "error" else " (planned)"))
        for ref in tokens(row["citation"]):
            if ref != "assumption" and ref not in R["refs"]:
                add("error", where, f"citation '{ref}' not in references.yaml")
        for m in METHOD_RE.findall(row["equations"]):
            if m not in R["methods"]:
                add("error", where, f"{m} is not defined in docs/PIPELINE_SPEC.md")
    return issues


def check_core(R: dict) -> list[dict]:
    """【中文】twin/core.yaml（骨架模型）中的关系级别、参数、文献和方法必须已登记。
    Every relation tier, coupling, citation and method named in twin/core.yaml must exist."""
    issues, core = [], R["core"]
    if not core:
        return issues
    # 【中文】变量表的 core 列只能写 core.yaml 中的编号、val、all 或 - / the variables "core" column
    ids = {i["id"] for i in core.get("links", []) + core.get("deferred", [])} | {"val", "all"}
    if "core" in R["vars"]:
        for _, row in R["vars"].iterrows():
            for t in tokens(row["core"]):
                if t not in ids:
                    issues.append({"level": "error", "where": row["var_id"], "message": f"core '{t}' is not a link or deferred id in twin/core.yaml"})
            if any(t.startswith("K") for t in tokens(row["core"])) and row["status"] in ("planned",):
                issues.append({"level": "warn", "where": row["var_id"], "message": "used by a core link but status is planned"})
        used = {t for v_ in R["vars"]["core"] for t in tokens(v_)}
        for i in core.get("links", []):
            if i["id"] not in used:
                issues.append({"level": "warn", "where": f"core {i['id']}", "message": "no variable in variables.csv is tagged with this link"})
    tiers = set(zip(R["rels"]["relation_id"], R["rels"]["tier"]))
    for item in core.get("links", []) + core.get("deferred", []):
        where = f"core {item['id']}"
        for rt in item.get("relations", []):
            rid, _, tier = rt.partition(":")
            if (rid, tier) not in tiers:
                issues.append({"level": "error", "where": where, "message": f"relation tier {rt} not in relations.csv"})
        for c in item.get("couplings", []):
            if c not in R["couplings"]:
                issues.append({"level": "error", "where": where, "message": f"coupling {c} not in couplings.csv"})
        for ref in item.get("citations", []):
            if ref not in R["refs"]:
                issues.append({"level": "error", "where": where, "message": f"citation '{ref}' not in references.yaml"})
        for m in item.get("methods", []):
            if m not in R["methods"]:
                issues.append({"level": "error", "where": where, "message": f"{m} is not defined in docs/PIPELINE_SPEC.md"})
    return issues


def check_data(R: dict) -> list[dict]:
    """【中文】标准表数值的值域检查（drivers 按 variable 列，exposures 按字段名）/ range checks on standard tables."""
    issues = []
    std = ROOT / R["project"].get("standard_dir", "data/standard")
    v = R["vars"]
    rng = lambda row: (pd.to_numeric(row["valid_min"], errors="coerce"), pd.to_numeric(row["valid_max"], errors="coerce"))
    drivers = std / "drivers.parquet"
    if drivers.exists():
        d = pd.read_parquet(drivers, columns=["variable", "value"])
        for _, row in v[v["std_table"] == "drivers"].iterrows():
            lo, hi = rng(row)
            for f in tokens(row["std_field"]):
                x = d.loc[d["variable"] == f, "value"]
                bad = ((x < lo) | (x > hi)).sum() if len(x) and pd.notna(lo) and pd.notna(hi) else 0
                if bad:
                    issues.append({"level": "warn", "where": row["var_id"], "message": f"drivers.{f}: {bad} values outside [{lo}, {hi}]"})
    expo = std / "exposures.parquet"
    if expo.exists():
        e = pd.read_parquet(expo, columns=["lst_mean", "lst_max"])
        for _, row in v[v["std_table"] == "exposures"].iterrows():
            lo, hi = rng(row)
            f = row["std_field"]
            if f in e and pd.notna(lo) and pd.notna(hi):
                bad = ((e[f] < lo) | (e[f] > hi)).sum()
                if bad:
                    issues.append({"level": "warn", "where": row["var_id"], "message": f"exposures.{f}: {bad} values outside [{lo}, {hi}]"})
    return issues


def coverage(v: pd.DataFrame) -> pd.DataFrame:
    t = pd.crosstab(v["system"], v["status"]).reindex(index=SYSTEMS, columns=STATUS, fill_value=0)
    t["total"] = t.sum(axis=1)
    return t


def md_cell(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ") if x not in ("", None) else "—"


HAVE = {"in_model", "ingested", "derived"}


def core_need(x, basis: dict, ph: dict | None = None) -> str:
    """【中文】骨架模型对该变量的数据需求：已有数据 / 假设值 / 占位 / 可获取 / 需合作。
    What the core still needs for this variable."""
    ph = ph or {}
    if x["status"] in HAVE:
        cs = [c for c in tokens(x["coupling_id"]) if c in basis]
        if x["kind"] in ("parameter", "attribute") and cs and all(basis[c] == "assumption" for c in cs):
            return "⬜ assumed value 假设值"
        if x["kind"] in ("parameter", "attribute") and cs and all(ph.get(c) == "yes" for c in cs):
            return "⬜ literature-informed placeholder 文献推断占位"
        return "✅ have 已有"
    return {"on_drive": "🟡 on Drive 在手", "public": "🟡 public 可公开获取", "restricted": "🔒 needs partner 需合作",
            "placeholder": "⬜ placeholder 占位", "planned": "⬜ planned 计划"}[x["status"]]


def core_section(R: dict, w) -> None:
    """【中文】2. 骨架模型所需变量：按主线环节 K1–K9 列出变量与数据需求。
    Section 2: variables needed by the core skeleton, grouped by link."""
    core, v = R.get("core"), R["vars"]
    if not core or "core" not in v:
        return
    w("## 2. 骨架模型所需变量 Core skeleton variables\n")
    w("【中文】按 [`twin/core.yaml`](../twin/core.yaml) 的主线环节 K1–K9 列出骨架模型用到的变量（变量表 `core` 列）。"
      "「假设值」表示参数已在模型中、但取值是占位假设，最需要用数据替换；一个变量可以属于多个环节。"
      "暂缓细节（D*）和只用于验证（val）的变量见第 3 节。\n")
    w("English: variables used by the core links K1–K9 of [`twin/core.yaml`](../twin/core.yaml) (the `core` column). "
      "\"Assumed value\" marks parameters that run in the model with placeholder values and are the first to replace with data. "
      "A variable can serve several links. Deferred (D*) and validation-only (val) variables are in section 3.\n")
    need = v.apply(lambda x: core_need(x, R["basis"], R["placeholder"]), axis=1)
    tagged = v[v["core"].map(lambda c: any(t.startswith("K") for t in tokens(c)))]
    cnt = need[tagged.index].map(lambda s: s.split(" ")[0]).value_counts()
    w("| 合计 Summary | ✅ have 已有 | ⬜ assumed / placeholder 假设或占位 | 🟡 obtainable 可获取 | 🔒 partner 需合作 |\n| --- | ---: | ---: | ---: | ---: |")
    w(f"| {len(tagged)} variables | {cnt.get('✅', 0)} | {cnt.get('⬜', 0)} | {cnt.get('🟡', 0)} | {cnt.get('🔒', 0)} |\n")
    for link in core["links"]:
        sub = v[v["core"].map(lambda c: link["id"] in tokens(c))]
        w(f"### {link['id']} {link['name_en']} / {link['name_zh']}\n")
        w("| Id | 变量 Variable | 类型 Kind | 状态 Status | 来源 Source | 骨架需求 Need | 目标来源 Target |\n| --- | --- | --- | --- | --- | --- | --- |")
        for i, x in sub.iterrows():
            src = x["source_dataset"] if tokens(x["source_dataset"]) else (x["fallback"] if tokens(x["fallback"]) else "")
            # 【中文】参数类变量：显示耦合参数的文献出处 / for coupling parameters, show the cited sources
            refs = sorted({k for c in tokens(x["coupling_id"]) for k in tokens(R["cite"].get(c, "")) if k != "assumption"})
            if src == "twin_couplings" and refs:
                src = "couplings: " + ", ".join(refs)
            w(f"| {x['var_id']} | {md_cell(x['name_en'])}<br>{md_cell(x['name_zh'])} | {x['kind']} | {MARK[x['status']]} {x['status']} | "
              f"{md_cell(src)} | {need[i]} | {md_cell(x['target_source'])} |")
        w("")
    gaps = v.loc[tagged.index][need[tagged.index].str.startswith(("⬜", "🟡", "🔒"))]
    if len(gaps):
        w("### 下一步要获取的数据 Data to obtain next\n")
        w("骨架模型中仍为假设、占位或缺失的变量，按优先级排序。Core variables still assumed, placeholder or missing, by priority.\n")
        w("| 优先级 Priority | Id | 变量 Variable | 环节 Links | 需求 Need | 目标来源 Target |\n| ---: | --- | --- | --- | --- | --- |")
        for i, x in gaps.sort_values(["priority", "var_id"]).iterrows():
            ks = ";".join(t for t in tokens(x["core"]) if t.startswith("K"))
            w(f"| {x['priority']} | {x['var_id']} | {md_cell(x['name_en'])}<br>{md_cell(x['name_zh'])} | {ks} | {need[i]} | {md_cell(x['target_source'])} |")
        w("")


def write_catalog(R: dict, issues: list[dict], path: Path) -> None:
    v, r = R["vars"], R["rels"]
    cov = coverage(v)
    L = []
    w = L.append
    w("# 数据与变量目录 Data and Variable Catalogue\n")
    w("> 【中文】本文件由 `python -m pipeline.registry` 从 `twin/variables.csv` 和 `twin/relations.csv` 自动生成，请勿手改。"
      "方法与公式见 [PIPELINE_SPEC.md](PIPELINE_SPEC.md)。\n>\n"
      "> Generated by `python -m pipeline.registry` from `twin/variables.csv` and `twin/relations.csv`; do not edit by hand. "
      "Methods and equations: [PIPELINE_SPEC.md](PIPELINE_SPEC.md).\n")
    n_err = sum(i["level"] == "error" for i in issues)
    n_plan = sum(i["level"] == "info" for i in issues)
    w(f"变量 {len(v)} 个 / {len(v)} variables · 关系 {r['relation_id'].nunique()} 条、方法等级 {len(r)} 行 / "
      f"{r['relation_id'].nunique()} relations, {len(r)} tier rows · 检查错误 {n_err} / errors {n_err} · "
      f"计划中的新参数引用 {n_plan} / references to planned parameters {n_plan}\n")

    w("## 1. 覆盖情况 Coverage\n")
    w("✅ 有数据 available · 🟡 在手或公开 in hand / public · 🔒 需合作 restricted · ⬜ 占位或计划 placeholder / planned\n")
    w("| 系统 System | " + " | ".join(f"{MARK[s]} {s}" for s in STATUS) + " | total |")
    w("| --- |" + " ---: |" * (len(STATUS) + 1))
    for sysname, row in cov.iterrows():
        w(f"| {SYSTEM_LABEL[sysname]} | " + " | ".join(str(row[s]) if row[s] else "·" for s in STATUS) + f" | {row['total']} |")
    tot = cov.sum()
    w("| **合计 Total** | " + " | ".join(f"**{tot[s]}**" for s in STATUS) + f" | **{tot['total']}** |\n")

    core_section(R, w)

    w("## 3. 变量 Variables\n")
    w("列说明 Columns：状态 status（见 PIPELINE_SPEC 开头）；来源 source = 数据集 id，缺数据时为占位方法 fallback；"
      "目标来源 target = 理想数据来源；用于 used in = 方程或方法编号。\n")
    for sysname in SYSTEMS:
        sub = v[v["system"] == sysname]
        if not len(sub):
            continue
        w(f"### {SYSTEM_LABEL[sysname]}\n")
        w("| Id | 变量 Variable | 符号 Symbol | 单位 Units | 分辨率 Resolution | 状态 Status | 来源 / 占位 Source / fallback | 目标来源 Target | 用于 Used in | 骨架 Core | 优先级 Priority |")
        w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: |")
        for _, x in sub.iterrows():
            src = x["source_dataset"] if tokens(x["source_dataset"]) else ""
            fb = x["fallback"] if tokens(x["fallback"]) else ""
            source = " · ".join(s for s in (f"`{src}`" if src else "", f"fallback: {fb}" if fb else "") if s)
            w(f"| {x['var_id']} | {md_cell(x['name_en'])}<br>{md_cell(x['name_zh'])} | `{md_cell(x['symbol'])}` | {md_cell(x['units'])} | "
              f"{md_cell(x['spatial_res'])}; {md_cell(x['temporal_res'])} | {MARK[x['status']]} {x['status']} | {md_cell(source)} | "
              f"{md_cell(x['target_source'])} | {md_cell(x['used_in'])} | {md_cell(x.get('core', ''))} | {x['priority']} |")
        notes = sub[(sub["note_en"] != "") | (sub["note_zh"] != "")]
        if len(notes):
            w("\n备注 Notes:\n")
            for _, x in notes.iterrows():
                w(f"- **{x['var_id']}** — {x['note_zh']} / {x['note_en']}")
        w("")

    w("## 4. 关系分级 Relation tiers\n")
    w("**当前** current = 现在模型使用的方法。等级定义见 PIPELINE_SPEC §6。Tier definitions in PIPELINE_SPEC §6.\n")
    w("| 关系 Relation | 等级 Tier | 当前 Current | 从 → 到 From → to | 门 Gate | 方法（中文） | Method (English) | 输入 Inputs | 参数 Couplings | 方程 Equations | 引用 Citation | 状态 Status |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for _, x in r.iterrows():
        cur = "**yes**" if x["current"] == "yes" else ""
        w(f"| {x['relation_id']} | {x['tier']} | {cur} | {md_cell(x['from_entity'])} → {md_cell(x['to_entity'])} | {x['gate']} | "
          f"{md_cell(x['method_zh'])} | {md_cell(x['method_en'])} | {md_cell(x['inputs'])} | {md_cell(x['couplings'])} | "
          f"{md_cell(x['equations'])} | {md_cell(x['citation'])} | {x['status']} |")
    w("")

    planned = sorted({i["message"].split()[1] for i in issues if i["level"] == "info"})
    if planned:
        w("## 5. 计划中的新参数 Planned parameters\n")
        w("这些参数编号已在变量表或关系表中引用，但尚未写入 `twin/couplings.csv`。实现对应方法时补上低 / 中 / 高值与来源。"
          "These ids are referenced but not yet in `twin/couplings.csv`; add ranges and sources when the method is implemented.\n")
        w(", ".join(f"`{p}`" for p in planned) + "\n")
    errs = [i for i in issues if i["level"] in ("error", "warn")]
    if errs:
        w("## 6. 检查问题 Issues\n")
        for i in errs:
            w(f"- **{i['level']}** {i['where']}: {i['message']}")
        w("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check the variable / relation registry and write docs/DATA_CATALOG.md")
    ap.add_argument("--check-data", action="store_true", help="range-check values in the standard tables")
    ap.add_argument("--out", default=str(ROOT / "docs/DATA_CATALOG.md"))
    a = ap.parse_args(argv)
    R = load()
    issues = check(R) + check_core(R)
    if a.check_data:
        issues += check_data(R)
    write_catalog(R, issues, Path(a.out))

    cov = coverage(R["vars"])
    print(cov.to_string())
    for lvl in ("error", "warn"):
        for i in (i for i in issues if i["level"] == lvl):
            print(f"{lvl:5s} {i['where']}: {i['message']}")
    n = {lvl: sum(i["level"] == lvl for i in issues) for lvl in ("error", "warn", "info")}
    print(f"\n{len(R['vars'])} variables, {R['rels']['relation_id'].nunique()} relations ({len(R['rels'])} tier rows); "
          f"{n['error']} errors, {n['warn']} warnings, {n['info']} references to planned parameters → {a.out}")
    return 1 if n["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
