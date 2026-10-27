"""
【中文】下载孪生关系链需要的公开数据到 raw/（可重复运行，结果写明来源与下载时间）：
    1) OpenStreetMap（Overpass API）：变电站、输电线、水厂 / 泵站 / 水塔、信号灯
    2) Iowa Environmental Mesonet：Nashville 机场 ASOS（BNA）逐小时气温
用法：python scripts/fetch_open_data.py [--start 2023-06-01 --end 2023-08-31]

Downloads the open data used by the dependency model into raw/:
OSM power / water / traffic-signal features and hourly BNA ASOS air temperature.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
UA = "nashville-heat-twin/0.2 (academic research prototype; github.com/hibu-11/nashville-heat-twin)"
OVERPASS = "https://overpass-api.de/api/interpreter"
# 【中文】电力与水务取 AOI 外扩约 4 km 的范围，保证 AOI 边缘的供电分区正确；信号灯只取 AOI
# power/water use the AOI plus ~4 km so service areas near the AOI edge are right
WIDE = (36.08, -86.88, 36.25, -86.68)      # south, west, north, east
AOI = (36.118, -86.837, 36.208, -86.727)

QUERIES = {
    "osm_substations": 'nwr["power"="substation"]({b});',
    "osm_power_lines": 'way["power"~"^(line|minor_line|cable)$"]({b});',
    "osm_water": 'nwr["man_made"~"^(water_works|pumping_station|water_tower|reservoir_covered|wastewater_plant)$"]({b});',
    "osm_traffic_signals": 'node["highway"="traffic_signals"]({a});',
}
KEEP_TAGS = ["name", "operator", "power", "substation", "voltage", "frequency", "cables", "circuits",
             "line", "location", "man_made", "highway", "ref", "start_date"]


def overpass(body: str) -> dict:
    q = f"[out:json][timeout:120];({body});out geom tags;"
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"  overpass attempt {attempt + 1} failed: {e}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("Overpass request failed")


def to_feature(el: dict) -> dict | None:
    """【中文】Overpass 元素 → GeoJSON：节点为点，闭合 way 为面，其余 way 为线；relation 取外环中心点。"""
    tags = {k: v for k, v in el.get("tags", {}).items() if k in KEEP_TAGS}
    props = {"osm_id": f"{el['type'][0]}{el['id']}", **tags}
    if el["type"] == "node":
        geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
    elif el["type"] == "way" and el.get("geometry"):
        coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
        closed = len(coords) >= 4 and coords[0] == coords[-1]
        is_area = closed and tags.get("power") != "line" and tags.get("power") != "minor_line"
        geom = {"type": "Polygon", "coordinates": [coords]} if is_area else {"type": "LineString", "coordinates": coords}
    elif el["type"] == "relation" and el.get("bounds"):
        b = el["bounds"]
        geom = {"type": "Point", "coordinates": [(b["minlon"] + b["maxlon"]) / 2, (b["minlat"] + b["maxlat"]) / 2]}
    else:
        return None
    return {"type": "Feature", "properties": props, "geometry": geom}


def fetch_osm():
    meta = {}
    for name, body in QUERIES.items():
        q = body.format(b=",".join(map(str, WIDE)), a=",".join(map(str, AOI)))
        print(f"[osm] {name} …")
        res = overpass(q)
        feats = [f for f in (to_feature(e) for e in res["elements"]) if f]
        out = RAW / "osm" / f"{name}.geojson"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
        meta[name] = {"features": len(feats), "query": q, "osm_base": res.get("osm3s", {}).get("timestamp_osm_base")}
        print(f"      {len(feats)} features → {out.relative_to(ROOT)}")
        time.sleep(5)   # 【中文】对公共 Overpass 服务友好一点 / be polite to the public server
    return meta


def fetch_asos(start: str, end: str):
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end) + dt.timedelta(days=1)
    params = {"station": "BNA", "data": ["tmpf", "dwpf", "relh", "sknt", "wxcodes"], "tz": "Etc/UTC",
              "format": "onlycomma", "latlon": "no", "missing": "M", "trace": "T", "report_type": "3",
              "year1": s.year, "month1": s.month, "day1": s.day, "year2": e.year, "month2": e.month, "day2": e.day}
    url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?" + urllib.parse.urlencode(params, doseq=True)
    print("[asos] BNA hourly …")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        text = r.read().decode()
    out = RAW / "asos_bna_hourly.csv"
    out.write_text(text, encoding="utf-8")
    print(f"      {text.count(chr(10)) - 1} rows → {out.relative_to(ROOT)}")
    return {"url": url, "rows": text.count("\n") - 1}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[-1])
    ap.add_argument("--start", default="2023-06-01")
    ap.add_argument("--end", default="2023-08-31")
    ap.add_argument("--skip-osm", action="store_true")
    args = ap.parse_args()
    meta = {"retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "license": {"osm": "ODbL 1.0 (© OpenStreetMap contributors)", "asos": "Iowa Environmental Mesonet / NOAA, public"}}
    if not args.skip_osm:
        meta["osm"] = fetch_osm()
    meta["asos"] = fetch_asos(args.start, args.end)
    (RAW / "open_data_manifest.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
