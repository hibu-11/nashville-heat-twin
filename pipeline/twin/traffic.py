"""
【中文】路网行程时间与可达性（docs/PIPELINE_SPEC.md M-28、M-29）。

    t_i(h) = t0_i · [1 + a · (v_i(h) / (φ_i · c_i))^b]          BPR 路段行程时间
    v_i(h) = AADT_i · η(h)                                       η 为 TMAS 工作日小时占比
    c_i    = lanes_i · c_lane(class_i)                            通行能力（双向合计）
    φ_i    = 1 − (1 − φ_dark) · P(信号降级_i)                       信号灯熄灭的期望通行能力折减
    τ(z)   = min_{f 可用} SP(z, f)                                多源 Dijkstra：到最近可用设施的时间

路网取 roads_lst（研究区内的 TIGER 路段）。地面道路之间在交点处打断（noding）；州际公路（S1100）和
匝道（S1630）只在端点相连，避免把立交当成平交路口。AADT、车道、限速取最近的 HPMS 路段（≤ 25 m），
缺失时按道路等级取占位值。路网为无向图（双向流量 / 双向车道）。

Network travel time and access (PIPELINE_SPEC M-28, M-29) on the roads_lst network; surface streets
are noded at crossings, interstates and ramps connect only at their ends.
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

GRADE_SEPARATED = ("S1100", "S1630")      # 【中文】州际公路与匝道 / interstates and ramps
# 【中文】HPMS 缺失时的占位值（按 TIGER MTFCC）/ fallbacks by TIGER class when HPMS has no value
DEFAULTS = {  # mtfcc: (AADT veh/day, lanes, speed mph, capacity class)
    "S1100": (90000, 6, 60, "fwy"), "S1630": (12000, 1, 40, "fwy"), "S1200": (15000, 4, 40, "art"),
    "S1400": (1500, 2, 30, "loc"), "S1730": (200, 1, 15, "loc"), "S1740": (300, 1, 20, "loc"),
    "S1640": (2000, 1, 30, "loc"), "S1750": (200, 1, 15, "loc"), "S1780": (200, 1, 10, "loc"),
}
OTHER = (500, 1, 25, "loc")
MPH = 0.44704


def hpms_class(f_system) -> str:
    """【中文】HPMS 功能等级 → 通行能力类别 / functional system → capacity class."""
    f = pd.to_numeric(f_system, errors="coerce")
    return np.where(f <= 2, "fwy", np.where(f <= 4, "art", "loc"))


def build_network(roads: gpd.GeoDataFrame, hpms: gpd.GeoDataFrame | None, snap_m: float = 25.0) -> dict:
    """【中文】由路段构建无向路网。返回边表（含 road_id、长度、AADT、车道、限速、类别）和节点坐标。
    Undirected network from road segments: edges with road id, length, AADT, lanes, speed, class."""
    a = roads["attributes"].map(json.loads)
    roads = roads.assign(mtfcc=a.map(lambda d: d.get("mtfcc")), name=a.map(lambda d: d.get("fullname")))
    roads = roads[roads["mtfcc"] != "S1500"].explode(index_parts=False).reset_index(drop=True)
    gs = roads["mtfcc"].isin(GRADE_SEPARATED)
    # 【中文】地面道路在交点处打断 / node surface streets at their crossings
    surface = shapely.union_all(roads.loc[~gs, "geometry"].values)
    pieces = list(shapely.get_parts(surface))
    edges = gpd.GeoDataFrame(geometry=pieces + list(roads.loc[gs, "geometry"]), crs=roads.crs)
    # 【中文】用每段中点找回所属原路段的属性 / recover the source road of each piece from its midpoint
    mid = edges.geometry.interpolate(0.5, normalized=True)
    tree = shapely.STRtree(roads.geometry.values)
    idx = tree.query_nearest(mid.values, return_distance=False, all_matches=False)[1]
    edges["road_id"] = roads["asset_id"].to_numpy()[idx]
    edges["mtfcc"] = roads["mtfcc"].to_numpy()[idx]
    edges["name"] = roads["name"].to_numpy()[idx]
    edges["length_m"] = edges.geometry.length
    edges = edges[edges["length_m"] > 0.5].reset_index(drop=True)

    # 【中文】节点：端点坐标按 1 m 取整合并 / nodes: endpoints merged on a 1 m grid
    start = shapely.get_point(edges.geometry.values, 0)
    end = shapely.get_point(edges.geometry.values, -1)
    key = lambda p: np.round(shapely.get_coordinates(p)).astype(np.int64)  # noqa: E731
    ks, ke = key(start), key(end)
    allk = np.vstack([ks, ke])
    uniq, inv = np.unique(allk, axis=0, return_inverse=True)
    edges["u"], edges["v"] = inv[: len(edges)], inv[len(edges):]

    # 【中文】HPMS 属性：中点最近的 HPMS 路段（≤ snap_m）/ HPMS attributes from the nearest section
    fallback = edges["mtfcc"].map(lambda m: DEFAULTS.get(m, OTHER))
    aadt = fallback.map(lambda d: d[0]).astype(float)
    lanes = fallback.map(lambda d: d[1]).astype(float)
    mph = fallback.map(lambda d: d[2]).astype(float)
    cls = fallback.map(lambda d: d[3]).astype(object)
    matched = np.zeros(len(edges), bool)
    if hpms is not None and len(hpms):
        h = hpms.to_crs(edges.crs).explode(index_parts=False).reset_index(drop=True)
        ha = pd.json_normalize(h["attributes"].map(json.loads))
        ht = shapely.STRtree(h.geometry.values)
        mid = edges.geometry.interpolate(0.5, normalized=True).values
        ei, hi = ht.query_nearest(mid, max_distance=snap_m, return_distance=False, all_matches=False)
        # 【中文】方向检查：路段与 HPMS 路段夹角 < 30°，避免交叉口附近的横向小路取到干道的流量
        # direction check (< 30°) so a cross street near an intersection does not take the arterial's volume
        keep = (_angle(edges.geometry.values[ei], h.geometry.values[hi]) < 30) | edges["mtfcc"].isin(GRADE_SEPARATED).to_numpy()[ei]
        ei, hi = ei[keep], hi[keep]
        v = pd.to_numeric(ha["aadt"], errors="coerce").to_numpy()[hi]
        ok = np.isfinite(v) & (v > 0)
        aadt.iloc[ei[ok]] = v[ok]
        matched[ei[ok]] = True
        ln = pd.to_numeric(ha["through_lanes"], errors="coerce").to_numpy()[hi]
        ok = np.isfinite(ln) & (ln > 0)
        lanes.iloc[ei[ok]] = ln[ok]
        sp = pd.to_numeric(ha["speed_limit"], errors="coerce").to_numpy()[hi]
        ok = np.isfinite(sp) & (sp > 0)
        mph.iloc[ei[ok]] = sp[ok]
        fc = hpms_class(ha["f_system"].to_numpy()[hi])
        cls.iloc[ei] = fc
    edges["aadt"], edges["lanes"], edges["speed_mph"], edges["cap_class"] = aadt, lanes, mph, cls
    edges["hpms_matched"] = matched
    edges["t0_min"] = edges["length_m"] / (edges["speed_mph"] * MPH) / 60.0
    ncomp, lab = connected_components(_adj(edges, np.ones(len(edges)), len(uniq)), directed=False)
    big = np.bincount(lab).argmax()
    stats = {"edges": int(len(edges)), "nodes": int(len(uniq)), "components": int(ncomp),
             "largest_component_node_share": round(float((lab == big).mean()), 3),
             "hpms_aadt_matched_share": round(float(matched.mean()), 3),
             "hpms_aadt_matched_length_share": round(float(edges.loc[matched, "length_m"].sum() / edges["length_m"].sum()), 3)}
    return {"edges": edges, "nodes": uniq.astype(float), "component": lab, "main": big, "stats": stats}


def _bearing(lines):
    a, b = shapely.get_coordinates(shapely.get_point(lines, 0)), shapely.get_coordinates(shapely.get_point(lines, -1))
    return np.degrees(np.arctan2(b[:, 1] - a[:, 1], b[:, 0] - a[:, 0])) % 180


def _angle(l1, l2):
    """【中文】两组线的无向夹角（0–90°）/ undirected angle between line pairs."""
    d = np.abs(_bearing(l1) - _bearing(l2)) % 180
    return np.minimum(d, 180 - d)


def _adj(edges, w, n):
    u, v = edges["u"].to_numpy(), edges["v"].to_numpy()
    m = coo_matrix((np.r_[w, w], (np.r_[u, v], np.r_[v, u])), shape=(n, n)).tocsr()
    return m


def hourly_profile(drivers: pd.DataFrame, tz: str) -> np.ndarray:
    """【中文】TMAS 工作日各小时占日流量的比例（各站平均），长度 24 / weekday hourly share of daily volume."""
    d = drivers[drivers["variable"] == "volume_vph"].copy()
    t = d["timestamp"].dt.tz_convert(tz)
    d = d.assign(day=t.dt.date, h=t.dt.hour, wd=t.dt.dayofweek < 5)
    d = d[d["wd"]]
    daily = d.groupby(["station_id", "day"])["value"].transform("sum")
    d = d.assign(share=d["value"] / daily)
    full = d.groupby(["station_id", "day"])["h"].transform("nunique") == 24
    prof = d[full].groupby("h")["share"].mean().reindex(range(24)).to_numpy()
    return prof / prof.sum()


def travel_time(edges: pd.DataFrame, eta_h: float, cap_lane: dict, a: float, b: float, phi=None) -> np.ndarray:
    """【中文】BPR 行程时间（分钟）/ BPR link travel time in minutes (M-28)."""
    cap = edges["lanes"].to_numpy(float) * edges["cap_class"].map(cap_lane).to_numpy(float)
    phi = np.ones(len(edges)) if phi is None else np.asarray(phi, float)
    vc = edges["aadt"].to_numpy(float) * eta_h / np.maximum(phi * cap, 1.0)
    return edges["t0_min"].to_numpy(float) * (1 + a * vc ** b)


def nearest_time(net: dict, w: np.ndarray, dest_nodes: list[int]) -> np.ndarray:
    """【中文】多源 Dijkstra：每个节点到最近目的地的时间（分钟），不可达为 inf。
    Multi-source Dijkstra: time from every node to the nearest destination."""
    if not len(dest_nodes):
        return np.full(len(net["nodes"]), np.inf)
    g = _adj(net["edges"], w, len(net["nodes"]))
    return dijkstra(g, directed=False, indices=dest_nodes, min_only=True)


def snap(net: dict, xy: np.ndarray, max_m: float = 500.0) -> np.ndarray:
    """【中文】点吸附到主连通分量中最近的节点；超过 max_m 记为 −1 / snap to the main component."""
    main = np.where(net["component"] == net["main"])[0]
    tree = shapely.STRtree(shapely.points(net["nodes"][main]))
    j = tree.query_nearest(shapely.points(xy), return_distance=False, all_matches=False)[1]
    out = main[j]
    dist = np.hypot(*(net["nodes"][out] - xy).T)
    out[dist > max_m] = -1
    return out
