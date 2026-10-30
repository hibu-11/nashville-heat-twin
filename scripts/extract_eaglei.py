"""
【中文】从 Drive 上逐年的 EAGLE-I 全国文件（每个约 0.1–1.4 GB）中提取一个县，合并成一个小 CSV。
本机磁盘有限：每年先复制到本地临时目录（直接读云端文件可能读坏），提取后立即删除副本。
    python scripts/extract_eaglei.py --src "<Drive>/cascading-heat_data/02_power/power_outage" \
        --fips 47037 --years 2014-2025 --out raw/eaglei/eaglei_davidson_2014_2025.csv

Extracts one county from the yearly EAGLE-I national files, one year at a time, into a small CSV.
Each file is copied locally first (streamed reads from Drive can corrupt) and deleted after use.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from pathlib import Path

import pandas as pd


def years(spec: str) -> list[int]:
    a, _, b = spec.partition("-")
    return list(range(int(a), int(b or a) + 1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="folder with eaglei_outages_<year>.csv")
    ap.add_argument("--fips", type=int, default=47037)
    ap.add_argument("--years", default="2014-2025")
    ap.add_argument("--out", default="raw/eaglei/eaglei_davidson_2014_2025.csv")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    with tempfile.TemporaryDirectory() as tmp:
        for y in years(a.years):
            src = Path(a.src) / f"eaglei_outages_{y}.csv"
            if not src.exists():
                print(f"[eaglei] {y}: missing {src.name}")
                continue
            t0 = time.time()
            local = Path(tmp) / src.name
            shutil.copyfile(src, local)
            head = pd.read_csv(local, nrows=0).columns
            # 【中文】2023 年文件的停电列名是 sum，其他年份是 customers_out / the 2023 file names the column "sum"
            col = "customers_out" if "customers_out" in head else "sum"
            kept = []
            for chunk in pd.read_csv(local, usecols=["fips_code", col, "run_start_time"], chunksize=2_000_000):
                kept.append(chunk[chunk["fips_code"] == a.fips])
            local.unlink()
            df = pd.concat(kept, ignore_index=True).rename(columns={col: "customers_out"})
            parts.append(df)
            print(f"[eaglei] {y}: {len(df):,} rows for {a.fips} ({time.time() - t0:.0f} s)", flush=True)
    res = pd.concat(parts, ignore_index=True)[["fips_code", "customers_out", "run_start_time"]]
    res.to_csv(out, index=False)
    print(f"[eaglei] wrote {out} ({len(res):,} rows)")


if __name__ == "__main__":
    main()
