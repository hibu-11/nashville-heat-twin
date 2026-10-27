"""
【中文】依赖规则 v0：由标准 assets 生成 dependencies 边和派生资产（供电分区）。
每条规则有编号（R-*），对应学术手册 §3.3；占位规则 placeholder = "yes"，质量等级较低。

门（gate）的含义 —— 描述上游失效如何传到下游：
    series     任一上游失效，下游即失效（串联需求，如 分区 → 设施）
    redundant  全部上游失效，下游才失效（冗余供给，如 多条进线的变电站、多个水厂）

Dependency rules v0 (handbook §3.3). gate = how upstream failures reach the
downstream asset: "series" fails if any upstream fails; "redundant" fails only
if all upstream fail.
"""
from __future__ import annotations

import json
from collections import deque

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box

from ..schema import STORE_CRS

# 【中文】直接为终端用户供电的变电站类型 / substation types that serve end customers
SERVING = {"distribution", "minor_distribution"}


def attrs(df: pd.DataFrame) -> pd.DataFrame:
    """【中文】展开 attributes JSON 列 / expand the attributes JSON column."""
    return pd.DataFrame([json.loads(a) if isinstance(a, str) else {} for a in df["attributes"]], index=df.index)


def kv_range(v) -> tuple[float, float]:
    """【中文】OSM voltage 如 "161000;69000" → (最高, 最低) kV / OSM voltage tag → (max, min) kV."""
    vals = [float(x) / 1000 for x in str(v).replace(",", ";").split(";") if x.strip().replace(".", "").isdigit()]
    return (max(vals), min(vals)) if vals else (np.nan, np.nan)


def edge(frm, to, dep_type, rule, coupling, gate, placeholder, quality, **extra):
    return {"from_asset": frm, "to_asset": to, "dep_type": dep_type, "rule_id": rule, "coupling_id": coupling,
            "gate": gate, "placeholder": "yes" if placeholder else "no", "quality_rank": float(quality), **extra}


# ---------------------------------------------------------------------- power
def substation_table(subs: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    a = attrs(subs)
    kv = a.get("voltage", pd.Series(index=subs.index, dtype=object)).map(kv_range)
    out = subs[["asset_id", "geometry"]].copy()
    out["name"] = a.get("name")
    out["stype"] = a.get("substation")
    out["kv_max"] = [k[0] for k in kv]
    out["kv_min"] = [k[1] for k in kv]
    # 【中文】类型缺失时，69 kV 及以下视为配电站 / untyped stations at ≤ 69 kV count as distribution
    out["serving"] = out["stype"].isin(SERVING) | (out["stype"].isna() & (out["kv_max"] <= 69))
    return out


def topology_edges(subs: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, snap_m: float) -> tuple[list, dict, dict]:
    """【中文】R-P1：沿 OSM 电力线找变电站之间的连接。
    把线的所有顶点做成图（1 m 取整合并重合点），落在变电站 snap_m 缓冲内的顶点归属该站；
    从每个站出发 BFS，遇到其他站即停止并记一条连接，不穿过第三个站。

    R-P1: substation adjacency along OSM power lines. Vertices within snap_m of a
    substation belong to it; a BFS from each substation stops at the first other
    substation it reaches, so connections never pass through a third station."""
    key = lambda x, y: (round(x), round(y))  # noqa: E731
    nbr: dict = {}
    for g in lines.geometry:
        parts = g.geoms if g.geom_type == "MultiLineString" else [g]
        for part in parts:
            pts = [key(x, y) for x, y in part.coords]
            for p, q in zip(pts, pts[1:]):
                if p != q:
                    nbr.setdefault(p, set()).add(q)
                    nbr.setdefault(q, set()).add(p)
    verts = np.array(list(nbr), dtype=float)
    owner: dict = {}
    if len(verts):
        tree = shapely.STRtree(shapely.points(verts))
        for sid, geom in zip(subs["asset_id"], subs.geometry.buffer(snap_m)):
            for i in tree.query(geom, predicate="contains"):
                owner.setdefault(tuple(verts[i]), sid)
    starts: dict = {}
    for v, sid in owner.items():
        starts.setdefault(sid, []).append(v)
    pairs, reach = set(), {}
    for sid, vs in starts.items():
        seen, dq = set(vs), deque(vs)
        while dq:
            v = dq.popleft()
            for w in nbr[v]:
                if w in seen:
                    continue
                seen.add(w)
                o = owner.get(w)
                if o and o != sid:
                    pairs.add(tuple(sorted((sid, o))))
                    reach.setdefault(sid, set()).add(o)
                    continue
                if o is None:
                    dq.append(w)
    return sorted(pairs), reach, {"vertices": len(nbr), "terminals": len(owner), "connected_substations": len(starts)}


def power_edges(subs: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, p: dict) -> tuple[list, dict]:
    """【中文】R-P1 只沿输电线 / 电缆（power=line|cable）推断站间连接；配电线路（minor_line）在 OSM 里
    连成网状（联络开关的分合状态没有记录），只用于 R-P1b：给尚无电源的配电站找最近的上级站。
    R-P1 uses transmission lines and cables only. Distribution lines form a mesh in
    OSM (switch states are not mapped), so they only feed R-P1b."""
    s = substation_table(subs).set_index("asset_id")
    snap = float(p.get("line_snap_m", 60))
    hv = lines[lines["asset_type"].isin(["line", "cable"])]
    mv = lines[lines["asset_type"] == "minor_line"]
    pairs, _, stats = topology_edges(subs, hv, snap)
    edges = []
    for a, b in pairs:
        ka, kb = s.at[a, "kv_max"], s.at[b, "kv_max"]
        if np.isnan(ka) or np.isnan(kb) or ka == kb:
            # 【中文】同电压等级：双向“对等”连接，只用于负荷转移 / peers: load transfer only
            edges += [edge(a, b, "power_peer", "R-P1", "C-P4", "redundant", False, 2),
                      edge(b, a, "power_peer", "R-P1", "C-P4", "redundant", False, 2)]
        else:
            hi, lo = (a, b) if ka > kb else (b, a)
            edges.append(edge(hi, lo, "power", "R-P1", "C-P5", "redundant", False, 2))

    # 【中文】R-P1b：沿配电线路能到达的、电压更高的站中，取距离最近的至多 2 座作为电源
    # R-P1b: up to two nearest higher-voltage stations reachable along distribution lines
    fed = {e["to_asset"] for e in edges if e["dep_type"] == "power"}
    cent = s.geometry.centroid
    _, reach_mv, st_mv = topology_edges(subs, mv, snap)
    n_p1b = 0
    for sid in s.index[s["serving"]]:
        if sid in fed:
            continue
        cand = [o for o in reach_mv.get(sid, ()) if s.at[o, "kv_max"] > s.at[sid, "kv_max"]]
        for o in sorted(cand, key=lambda o: cent[o].distance(cent[sid]))[: int(p.get("max_feeds", 2))]:
            edges.append(edge(o, sid, "power", "R-P1b", "C-P5", "redundant", False, 3))
            n_p1b += 1
    fed = {e["to_asset"] for e in edges if e["dep_type"] == "power"}

    # 【中文】R-P2（占位）：仍没有上级电源的配电站，接到最近的更高电压站
    # R-P2 (placeholder): serving stations still without a feed → nearest higher-voltage station
    max_d = float(p.get("placeholder_max_km", 12)) * 1000
    n_p2 = 0
    for sid in s.index[s["serving"]]:
        if sid in fed:
            continue
        cand = s[(s["kv_max"] > s.at[sid, "kv_max"]) & (s.index != sid)]
        if cand.empty:
            continue
        d = cent[cand.index].distance(cent[sid])
        if d.min() <= max_d:
            edges.append(edge(d.idxmin(), sid, "power", "R-P2", "C-P5", "redundant", True, 4,
                              distance_m=round(float(d.min()))))
            n_p2 += 1
    stats |= {"R-P1_pairs": len(pairs), "R-P1b_feeds": n_p1b, "R-P2_placeholder_feeds": n_p2,
              "mv_vertices": st_mv["vertices"]}
    return edges, stats


def service_zones(subs: gpd.GeoDataFrame, aoi_box, buildings: gpd.GeoDataFrame | None,
                  pop: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    """【中文】R-P3（占位）：以供电站为种子做 Voronoi 剖分，裁到 AOI，作为供电分区。
    分区负荷权重 = 分区内建筑占地面积；分区人口 = ZCTA 人口按面积叠加。

    R-P3 (placeholder): Voronoi service zones of serving substations, clipped to
    the AOI. Zone load weight = building footprint area; population by areal
    overlay of ZCTA counts."""
    s = substation_table(subs)
    seeds = s[s["serving"]].copy()
    seeds["pt"] = seeds.geometry.centroid
    cells = shapely.voronoi_polygons(shapely.multipoints(seeds["pt"].values), extend_to=aoi_box.buffer(20_000))
    cells = gpd.GeoDataFrame(geometry=list(cells.geoms), crs=STORE_CRS)
    hit = gpd.sjoin(gpd.GeoDataFrame(seeds[["asset_id"]], geometry=seeds["pt"], crs=STORE_CRS), cells,
                    predicate="within", how="left")
    zones = gpd.GeoDataFrame({"substation": hit["asset_id"].values, "name": seeds["name"].values},
                             geometry=cells.geometry.iloc[hit["index_right"].values].values, crs=STORE_CRS)
    zones["geometry"] = zones.geometry.intersection(aoi_box)
    zones = zones[~zones.geometry.is_empty & (zones.geometry.area > 1)].reset_index(drop=True)
    zones["asset_id"] = "twin_zone:" + zones["substation"].str.split(":").str[-1]

    zones["building_area_m2"] = 0.0
    if buildings is not None and len(buildings):
        b = gpd.GeoDataFrame({"area": buildings.geometry.area}, geometry=buildings.geometry.centroid, crs=STORE_CRS)
        j = gpd.sjoin(b, zones[["asset_id", "geometry"]], predicate="within")
        zones["building_area_m2"] = zones["asset_id"].map(j.groupby("asset_id")["area"].sum()).fillna(0).round(0)
    for col in ("pop_total", "pop_elderly", "pop_below_poverty"):
        zones[col] = 0.0
    if pop is not None and len(pop):
        pa = attrs(pop)
        pz = gpd.GeoDataFrame(pa[["pop_total", "pop_elderly", "pop_below_poverty"]].apply(pd.to_numeric, errors="coerce"),
                              geometry=pop.geometry.values, crs=STORE_CRS)
        pz["a0"] = pz.geometry.area
        ov = gpd.overlay(pz, zones[["asset_id", "geometry"]], how="intersection", keep_geom_type=True)
        frac = ov.geometry.area / ov["a0"]
        for col in ("pop_total", "pop_elderly", "pop_below_poverty"):
            zones[col] = zones["asset_id"].map((ov[col] * frac).groupby(ov["asset_id"]).sum()).fillna(0).round(0)
    return zones


def served_edges(zones: gpd.GeoDataFrame, subs: gpd.GeoDataFrame, served: gpd.GeoDataFrame,
                 coupling: str, dep_type: str = "power") -> list:
    """【中文】R-P4（占位）：资产由所在分区供电；分区外的资产接最近的供电站。
    R-P4 (placeholder): an asset is served by the zone it lies in, else by the nearest serving substation."""
    if served.empty:
        return []
    pts = gpd.GeoDataFrame(served[["asset_id"]], geometry=served.geometry.representative_point(), crs=STORE_CRS)
    j = gpd.sjoin(pts, zones[["asset_id", "geometry"]].rename(columns={"asset_id": "zone"}), predicate="within", how="left")
    j = j[~j.index.duplicated()]
    s = substation_table(subs)
    s = s[s["serving"]]
    out = []
    for idx, row in j.iterrows():
        if isinstance(row.get("zone"), str):
            out.append(edge(row["zone"], row["asset_id"], dep_type, "R-P4", coupling, "series", True, 4))
        else:
            d = s.geometry.distance(pts.geometry[idx])
            out.append(edge(s.loc[d.idxmin(), "asset_id"], row["asset_id"], dep_type, "R-P4b", coupling, "series",
                            True, 4, distance_m=round(float(d.min()))))
    return out


# ---------------------------------------------------------------------- water
def water_edges(water: gpd.GeoDataFrame, facilities: list[tuple[gpd.GeoDataFrame, str]]) -> list:
    """【中文】R-W1/R-W2（占位）：供水设施 → 健康设施。
    水厂（water_works）之间互为冗余（redundant）；水塔 / 有盖水库作为储水缓冲（C-W3）。
    R-W1/R-W2 (placeholder): water production (redundant across plants) and storage → facilities."""
    w = water.copy()
    w["mm"] = attrs(w).get("man_made")
    plants = w[w["mm"] == "water_works"]
    storage = w[w["mm"].isin(["water_tower", "reservoir_covered"])]
    out = []
    for fac, _ in facilities:
        for fid in fac["asset_id"]:
            out += [edge(pid, fid, "water", "R-W1", "C-W1", "redundant", True, 4) for pid in plants["asset_id"]]
            out += [edge(sid, fid, "water_storage", "R-W2", "C-W3", "redundant", True, 4) for sid in storage["asset_id"]]
    return out


# ---------------------------------------------------------------------- transport / access
def near_edges(src: gpd.GeoDataFrame, dst: gpd.GeoDataFrame, max_m: float, dep_type, rule, coupling,
               gate, quality, one_per_src=False) -> list:
    """【中文】按距离把 src 资产连到 dst 资产（真实空间关系）/ proximity edges src → dst."""
    if src.empty or dst.empty:
        return []
    a = gpd.GeoDataFrame(src[["asset_id"]].rename(columns={"asset_id": "frm"}), geometry=src.geometry.values, crs=STORE_CRS)
    b = gpd.GeoDataFrame(dst[["asset_id"]].rename(columns={"asset_id": "to"}), geometry=dst.geometry.values, crs=STORE_CRS)
    if one_per_src:
        j = gpd.sjoin_nearest(a, b, max_distance=max_m, distance_col="d")
        j = j[~j.index.duplicated()]
    else:
        j = gpd.sjoin(gpd.GeoDataFrame(a, geometry=a.buffer(max_m)), b, predicate="intersects")
    return [edge(r.frm, r.to, dep_type, rule, coupling, gate, False, quality) for r in j.itertuples()]


def build(ctx, cfg: dict) -> tuple[gpd.GeoDataFrame, pd.DataFrame, dict]:
    """【中文】按配置运行全部规则，返回（派生资产，依赖边，统计）/ run every rule."""
    p = cfg.get("params", {})
    load = lambda k: ctx.load_assets(cfg[k]).to_crs(STORE_CRS) if cfg.get(k) else None  # noqa: E731
    subs, lines, water = load("substations"), load("power_lines"), load("water")
    signals, roads, bridges = load("signals"), load("roads"), load("bridges")
    pop, buildings = load("population"), load("buildings")
    fac = [(ctx.load_assets(f["source"]).to_crs(STORE_CRS), f["coupling"]) for f in cfg.get("facilities", [])]
    aoi_box = box(*gpd.GeoSeries([box(*ctx.aoi)], crs=4326).to_crs(STORE_CRS).total_bounds)

    edges, stats = power_edges(subs, lines, p)
    zones = service_zones(subs, aoi_box, buildings, pop)
    edges += [edge(z.substation, z.asset_id, "power", "R-P3", "C-P5", "series", True, 4) for z in zones.itertuples()]
    for f, coupling in fac:
        edges += served_edges(zones, subs, f, coupling)
    plants = water[attrs(water).get("man_made").eq("water_works")] if water is not None else None
    if plants is not None:
        edges += served_edges(zones, subs, plants, "C-W2")
    if signals is not None:
        edges += served_edges(zones, subs, signals, "C-T2")
    if pop is not None:
        # 【中文】人口单元：分区 → ZCTA，按人口份额记权重 / zone → ZCTA with population share
        pz = gpd.overlay(gpd.GeoDataFrame(pop[["asset_id"]], geometry=pop.geometry.values, crs=STORE_CRS),
                         zones[["asset_id", "geometry"]].rename(columns={"asset_id": "zone"}), how="intersection")
        pz["share"] = pz.geometry.area / pz["asset_id"].map(pop.set_index("asset_id").geometry.area)
        edges += [edge(r.zone, r.asset_id, "power", "R-P4", "C-POP1", "series", True, 4, weight=round(r.share, 4))
                  for r in pz.itertuples() if r.share > 0.001]
    if water is not None:
        edges += water_edges(water, fac)
    if signals is not None and roads is not None:
        edges += near_edges(signals, roads, float(p.get("signal_road_m", 30)), "control", "R-T1", "C-T3", "series", 3)
    if bridges is not None and roads is not None:
        edges += near_edges(bridges, roads, float(p.get("bridge_road_m", 30)), "structural", "R-T2", "C-T4",
                            "series", 3, one_per_src=True)
    if roads is not None:
        for f, _ in fac:
            edges += _access_edges(roads, f)

    deps = pd.DataFrame(edges).drop_duplicates(["from_asset", "to_asset", "dep_type"])
    zones_assets = gpd.GeoDataFrame({
        "asset_id": zones["asset_id"], "system": "power", "asset_type": "service_zone",
        "attributes": zones.apply(lambda r: json.dumps({
            "substation": r.substation, "name": r["name"], "placeholder": True, "rule": "R-P3",
            "building_area_m2": r.building_area_m2, "pop_total": r.pop_total, "pop_elderly": r.pop_elderly,
            "pop_below_poverty": r.pop_below_poverty}, default=str), axis=1),
        "source_id": cfg["id"]}, geometry=zones.geometry, crs=STORE_CRS)
    stats |= {"zones": int(len(zones)), "edges": int(len(deps)),
              "by_rule": deps.groupby("rule_id").size().to_dict(),
              "placeholder_share": round(float((deps["placeholder"] == "yes").mean()), 3)}
    return zones_assets, deps, stats


def _access_edges(roads: gpd.GeoDataFrame, fac: gpd.GeoDataFrame) -> list:
    """【中文】R-A1：设施的出入通道 = 最近的道路路段（真实空间关系，v0 只记录不传播）。
    R-A1: a facility's access = its nearest road segment (recorded, not propagated in v0)."""
    a = gpd.GeoDataFrame(fac[["asset_id"]].rename(columns={"asset_id": "to"}), geometry=fac.geometry.representative_point().values, crs=STORE_CRS)
    b = gpd.GeoDataFrame(roads[["asset_id"]].rename(columns={"asset_id": "frm"}), geometry=roads.geometry.values, crs=STORE_CRS)
    j = gpd.sjoin_nearest(a, b, max_distance=300, distance_col="d")
    j = j[~j.index.duplicated()]
    return [edge(r.frm, r.to, "access", "R-A1", "C-A1", "series", False, 3) for r in j.itertuples()]
