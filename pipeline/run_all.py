"""
【中文】一条命令跑完骨架模型的全部结果，按依赖顺序执行，失败即停，记录每步耗时，日志写到 data/logs/。
    python -m pipeline.run_all                 # 全部（约 2–2.5 小时）
    python -m pipeline.run_all --quick         # 每步少量运行，检查流程（约 15 分钟）
    python -m pipeline.run_all --from report   # 从某一步开始（前面的结果已在）
    python -m pipeline.run_all --only core extremes

步骤：tests → core → extremes → (contrib、variants、heatwaves 可两两并行) → report → registry → atlas。
core 之后的三个模拟步骤互不依赖，--jobs 2（默认）时同时跑两个；内存 8 GB 时不建议超过 2。

Runs every stage of the core results in dependency order; stops on the first failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from .build import ROOT

# 【中文】实际热浪：BNA 每年 5 日平均最高气温最高的一段，前后各加一天 / observed heat waves (hottest 5 days ± 1 day)
HEATWAVES = {"hw2024aug": ("2024-08-25", "2024-08-31", "2024 Aug 26–30"),
             "hw2022jun": ("2022-06-20", "2022-06-26", "2022 Jun 21–25"),
             "hw2025aug": ("2025-08-14", "2025-08-20", "2025 Aug 15–19"),
             "hw2023aug": ("2023-08-21", "2023-08-27", "2023 Aug 22–26")}


def stages(quick: bool) -> dict:
    n = (lambda full, q: str(q if quick else full))  # noqa: E731
    py = [sys.executable, "-u", "-m"]
    hw = [py + ["pipeline.core", "--runs", n(1000, 60), "--scenarios", "0,2", "--start", a, "--end", b, "--tag", tag]
          for tag, (a, b, _) in HEATWAVES.items()]
    return {
        "tests": [py + ["pytest", "-q", "tests"]],
        "core": [py + ["pipeline.core", "--runs", n(2000, 100)]],
        "extremes": [py + ["pipeline.extremes", "--boot", n(500, 50)]],
        "contrib": [py + ["pipeline.contrib", "--runs", n(500, 40), "--scenarios", "2,4"]],
        "variants": [py + ["pipeline.contrib", "--variants", "--runs", n(300, 40), "--scenarios", "4"]],
        "heatwaves": hw,
        "report": [py + ["pipeline.report"]],
        "registry": [py + ["pipeline.registry"]],
        "atlas": [[sys.executable, str(ROOT / "scripts/build_atlas.py")]],
    }


ORDER = ["tests", "core", "extremes", ("contrib", "variants", "heatwaves"), "report", "registry", "atlas"]


def run_stage(name: str, cmds: list, log) -> float:
    t0 = time.time()
    for c in cmds:
        log.write(f"\n$ {' '.join(c)}\n")
        log.flush()
        p = subprocess.run(c, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if p.returncode != 0:
            raise SystemExit(f"[run_all] {name} failed (exit {p.returncode}); see the log")
    return time.time() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run every stage of the core model results")
    ap.add_argument("--quick", action="store_true", help="few runs per stage, to check the workflow")
    ap.add_argument("--from", dest="start", help="start at this stage")
    ap.add_argument("--only", nargs="+", help="run only these stages")
    ap.add_argument("--jobs", type=int, default=2, help="parallel simulation stages after core (default 2)")
    args = ap.parse_args(argv)
    S = stages(args.quick)
    flat = [s for g in ORDER for s in (g if isinstance(g, tuple) else (g,))]
    want = set(args.only) if args.only else set(flat[flat.index(args.start):] if args.start else flat)
    bad = want - set(flat)
    if bad:
        raise SystemExit(f"unknown stages {sorted(bad)}; choose from {flat}")
    logdir = ROOT / "data/logs"
    logdir.mkdir(parents=True, exist_ok=True)
    path = logdir / f"run_all_{dt.datetime.now():%Y%m%dT%H%M%S}{'_quick' if args.quick else ''}.log"
    print(f"[run_all] log: {path}")
    t_all = time.time()
    with open(path, "w", encoding="utf-8") as log:
        for g in ORDER:
            group = [s for s in (g if isinstance(g, tuple) else (g,)) if s in want]
            if not group:
                continue
            print(f"[run_all] {' + '.join(group)} …", flush=True)
            if len(group) == 1 or args.jobs < 2:
                for s in group:
                    print(f"[run_all] {s} done in {run_stage(s, S[s], log) / 60:.1f} min", flush=True)
            else:
                # 【中文】各并行步骤写各自的日志，结束后并入总日志 / separate logs per parallel stage, merged afterwards
                parts = {s: path.with_name(f"{path.stem}_{s}.log") for s in group}
                with ThreadPoolExecutor(max_workers=args.jobs) as ex:
                    fut = {s: ex.submit(lambda s=s: run_stage(s, S[s], open(parts[s], "w", encoding="utf-8"))) for s in group}
                    for s, f in fut.items():
                        print(f"[run_all] {s} done in {f.result() / 60:.1f} min", flush=True)
                for s, p in parts.items():
                    log.write(f"\n===== {s} =====\n" + p.read_text(encoding="utf-8"))
                    p.unlink()
    print(f"[run_all] all done in {(time.time() - t_all) / 60:.1f} min")


if __name__ == "__main__":
    main()
