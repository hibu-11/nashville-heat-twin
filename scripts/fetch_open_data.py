"""
【中文】下载孪生关系链需要的公开数据到 raw/（可重复运行，结果写明来源与下载时间）：
    1) OpenStreetMap（Overpass API）：变电站、输电线、水厂 / 泵站 / 水塔、信号灯、消防 / 急救站
    2) Iowa Environmental Mesonet：Nashville 机场 ASOS（BNA）逐小时气象，默认 2014–2025（多年校准用）
    3) USGS NWIS：Cumberland 河 Nashville 站（03431500）日均流量
    4) 栅格（城市气温场 M-6 的预测因子）：USGS 3DEP 高程、NLCD 2021 不透水面与土地覆盖
    5) EIA-930：TVA 平衡区逐小时负荷与发电（半年批量文件，只保留 TVA 行）
用法：python scripts/fetch_open_data.py [--start 2014-01-01 --end 2025-12-31] [--only osm,asos,usgs,grids,eia930]

Downloads the open data used by the dependency model into raw/: OSM features, hourly BNA ASOS,
USGS daily discharge and the predictor grids for the urban air-temperature field.
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
    "osm_fire_stations": 'nwr["amenity"="fire_station"]({b});',
}
KEEP_TAGS = ["name", "operator", "power", "substation", "voltage", "frequency", "cables", "circuits",
             "line", "location", "man_made", "highway", "ref", "start_date", "amenity", "emergency"]


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


def fetch_osm(layers=None):
    meta = {}
    for name, body in QUERIES.items():
        if layers and name not in layers:
            continue
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
    params = {"station": "BNA", "data": ["tmpf", "dwpf", "relh", "sknt", "wxcodes", "p01i", "alti", "skyc1"], "tz": "Etc/UTC",
              "format": "onlycomma", "latlon": "no", "missing": "M", "trace": "T", "report_type": "3",
              "year1": s.year, "month1": s.month, "day1": s.day, "year2": e.year, "month2": e.month, "day2": e.day}
    url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?" + urllib.parse.urlencode(params, doseq=True)
    print("[asos] BNA hourly …")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r:
        text = r.read().decode()
    out = RAW / "asos_bna_hourly.csv"
    out.write_text(text, encoding="utf-8")
    print(f"      {text.count(chr(10)) - 1} rows → {out.relative_to(ROOT)}")
    return {"url": url, "rows": text.count("\n") - 1}


def fetch_usgs(start: str, end: str, site: str = "03431500"):
    """【中文】USGS 日均流量（参数 00060，cfs）。该站没有水温（00010），水温用 TDEC 采样数据。
    Daily discharge; this gauge has no water temperature, which comes from TDEC samples instead."""
    url = ("https://waterservices.usgs.gov/nwis/dv/?" +
           urllib.parse.urlencode({"format": "rdb", "sites": site, "parameterCd": "00060", "startDT": start, "endDT": end}))
    print(f"[usgs] {site} daily discharge …")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        text = r.read().decode()
    out = RAW / "usgs" / f"usgs_{site}_dv.rdb"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    rows = sum(1 for ln in text.splitlines() if ln.startswith("USGS"))
    print(f"      {rows} days → {out.relative_to(ROOT)}")
    return {"url": url, "rows": rows}


# 【中文】城市气温场的预测因子栅格，范围同电力资产（AOI 外扩约 4 km）
# predictor grids for the urban air-temperature field, over the wide (power) box
GRIDS = {
    "dem_3dep": ("https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?" +
                 urllib.parse.urlencode({"bbox": f"{WIDE[1]},{WIDE[0]},{WIDE[3]},{WIDE[2]}", "bboxSR": 4326,
                                         "imageSR": 32616, "size": "600,630", "format": "tiff", "pixelType": "F32",
                                         "interpolation": "RSP_BilinearInterpolation", "f": "image"})),
    **{name: ("https://www.mrlc.gov/geoserver/mrlc_download/wcs?" + urllib.parse.urlencode(
        [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("coverageid", cov),
         ("subset", f"Lat({WIDE[0] - 0.02},{WIDE[2] + 0.02})"), ("subset", f"Long({WIDE[1] - 0.02},{WIDE[3] + 0.02})"),
         ("subsettingcrs", "http://www.opengis.net/def/crs/EPSG/0/4326"), ("format", "image/geotiff")]))
       for name, cov in (("nlcd2021_impervious", "mrlc_download__NLCD_2021_Impervious_L48"),
                         ("nlcd2021_landcover", "mrlc_download__NLCD_2021_Land_Cover_L48"))},
}


def fetch_grids():
    meta = {}
    for name, url in GRIDS.items():
        print(f"[grid] {name} …")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
        if not data[:4] in (b"II*\x00", b"MM\x00*"):
            raise RuntimeError(f"{name}: response is not a GeoTIFF ({data[:120]!r})")
        out = RAW / "grids" / f"{name}.tif"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        meta[name] = {"url": url, "bytes": len(data)}
        print(f"      {len(data) / 1e6:.1f} MB → {out.relative_to(ROOT)}")
    return meta


EIA930 = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_BALANCE_{y}_{half}.csv"
EIA930_COLS = ["Balancing Authority", "UTC Time at End of Hour", "Demand (MW)", "Demand (MW) (Adjusted)",
               "Net Generation (MW)", "Total Interchange (MW)"]


def fetch_eia930(start: str, end: str, ba: str = "TVA"):
    """【中文】EIA-930 半年批量文件（每个 30–45 MB），逐个下载并只保留一个平衡区。数据从 2015 年 7 月开始。
    EIA-930 six-month bulk files, one at a time, keeping one balancing authority (data start July 2015)."""
    import io

    import pandas as pd

    y0, y1 = max(int(start[:4]), 2015), int(end[:4])
    parts, meta = [], []
    for y in range(y0, y1 + 1):
        for half in ("Jan_Jun", "Jul_Dec"):
            if (y, half) == (2015, "Jan_Jun"):
                continue
            url = EIA930.format(y=y, half=half)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=600) as r:
                    raw = r.read()
            except Exception as e:  # noqa: BLE001
                print(f"[eia930] {y} {half}: {e}")
                continue
            df = pd.read_csv(io.BytesIO(raw), usecols=lambda c: c in EIA930_COLS, thousands=",", low_memory=False)
            df = df[df["Balancing Authority"] == ba]
            parts.append(df)
            meta.append({"url": url, "rows": len(df)})
            print(f"[eia930] {y} {half}: {len(df)} hours", flush=True)
    out = RAW / "eia" / f"eia930_{ba.lower()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(parts, ignore_index=True).to_csv(out, index=False)
    print(f"      → {out.relative_to(ROOT)}")
    return {"files": meta, "balancing_authority": ba}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[-1])
    ap.add_argument("--start", default="2014-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--only", default="osm,asos,usgs,grids", help="comma list of parts to fetch")
    # 【中文】只重取部分 OSM 图层（重取变电站 / 线路会改变电网拓扑）/ re-fetching power layers changes the graph
    ap.add_argument("--osm-layers", default="", help="comma list of OSM layers, e.g. osm_fire_stations")
    args = ap.parse_args()
    parts = set(args.only.split(","))
    mf = RAW / "open_data_manifest.json"
    # 【中文】只更新本次下载的部分，保留其他部分的记录 / keep manifest entries of parts not re-fetched
    meta = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    meta["retrieved_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    meta["license"] = {"osm": "ODbL 1.0 (© OpenStreetMap contributors)", "asos": "Iowa Environmental Mesonet / NOAA, public",
                       "usgs": "USGS, public domain", "grids": "USGS 3DEP and MRLC NLCD, public domain"}
    if "osm" in parts:
        layers = [x for x in args.osm_layers.split(",") if x]
        meta["osm"] = {**meta.get("osm", {}), **fetch_osm(layers)}
    if "asos" in parts:
        meta["asos"] = fetch_asos(args.start, args.end)
    if "usgs" in parts:
        meta["usgs"] = fetch_usgs(args.start, args.end)
    if "grids" in parts:
        meta["grids"] = fetch_grids()
    if "eia930" in parts:
        meta["eia930"] = fetch_eia930(args.start, args.end)
    mf.write_text(json.dumps(meta, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
