"""
【中文】定时抓取 NES 停电地图背后的公开 JSON（DataCapable 托管），积累 Nashville 本地的停电记录。
每次请求一次事件列表，按时间戳写入 raw/nes_outages/YYYY-MM/events_<UTC>.json；不带任何个人信息，默认 15 分钟一次。
这是对外部服务的定时访问：运行前需征得项目负责人同意，并保持低频率。
    .venv/bin/python scripts/nes_outage_poll.py --once           # 抓一次
    .venv/bin/python scripts/nes_outage_poll.py --every 900      # 每 15 分钟一次，直到中断

Polls the public NES outage-map event feed and stores timestamped snapshots under raw/nes_outages/.
Undocumented endpoint found in the map's JavaScript (2026-11-10); poll politely and stop if asked.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

URL = "https://utilisocial.io/datacapable/v2/p/NES/map/events"
UA = "nashville-heat-twin research (contact@example.org)"


def snapshot(out_dir: Path) -> Path:
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    now = dt.datetime.now(dt.timezone.utc)
    p = out_dir / now.strftime("%Y-%m") / f"events_{now:%Y%m%dT%H%M%SZ}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))
    return p


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="raw/nes_outages")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=int, default=900, help="seconds between requests (minimum 300)")
    a = ap.parse_args(argv)
    every = max(300, a.every)
    while True:
        try:
            print("saved", snapshot(Path(a.out)))
        except Exception as e:  # 【中文】网络错误时记录后继续 / log and continue on network errors
            print("failed:", e)
        if a.once:
            break
        time.sleep(every)


if __name__ == "__main__":
    main()
