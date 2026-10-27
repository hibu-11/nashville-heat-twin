"""
【中文】依赖规则适配器：读取上游资产，按 pipeline/twin/rules.py 的规则生成
    1) 标准表 dependencies（每条边带 rule_id、coupling_id、gate、placeholder、quality_rank）
    2) 派生资产（供电分区 service_zone，占位）
    3) 网页文件：节点 / 边 GeoJSON 与逻辑汇总 logic.json
Dependency-rules adapter: upstream assets → dependencies + derived zones + web graph files.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
import shapely

from ..schema import STORE_CRS
from ..twin import rules
from .base import AdapterResult, DatasetAdapter, write_json

# 【中文】网页上作为节点显示的资产类型（电力线只用于推断拓扑，不画成节点）
# asset types drawn as graph nodes (power lines only feed the topology rules)
NODE_TYPES = {"substation", "service_zone", "hospital", "dialysis", "nursing_home", "water_works", "water_tower",
              "reservoir_covered", "wastewater_plant", "traffic_signal"}


class DependencyRulesAdapter(DatasetAdapter):
    kind = "dependency_rules"
    code_modules = (rules,)     # 【中文】规则代码变了也要重建 / rebuild when the rules change

    def input_files(self):
        return []          # 【中文】没有原始文件，只依赖上游 / no raw input, upstream only

    def has_inputs(self):
        return True

    def upstream(self):
        c = self.cfg
        ids = [c.get(k) for k in ("substations", "power_lines", "water", "signals", "roads", "bridges",
                                  "population", "buildings")]
        return [i for i in ids if i] + [f["source"] for f in c.get("facilities", [])]

    def outputs(self):
        d = self.ctx.site_data_dir / "twin"
        return [d / "graph_nodes.geojson", d / "graph_edges.geojson", d / "logic.json"]

    def extract(self):
        return None

    def transform(self, _) -> AdapterResult:
        zones, deps, stats = rules.build(self.ctx, self.cfg)
        print(f"    {self.id}: {stats['edges']:,} edges, {stats['zones']} service zones, "
              f"{stats['placeholder_share']:.0%} placeholder; by rule {stats['by_rule']}")
        nodes_f, edges_f, logic_f = self.outputs()
        nodes_f.parent.mkdir(parents=True, exist_ok=True)

        # 【中文】网页节点：电力 / 水 / 健康资产 + 供电分区 / web nodes
        assets = pd.concat([self.ctx.load_assets(u) for u in self.upstream()], ignore_index=True)
        assets = gpd.GeoDataFrame(pd.concat([assets, zones], ignore_index=True), geometry="geometry", crs=STORE_CRS)
        a = rules.attrs(assets)
        node = assets[assets["asset_type"].isin(NODE_TYPES)].copy()
        na = a.loc[node.index]
        node["name"] = na.get("name", na.get("Facility Name")).fillna(na.get("Facility Name")).fillna(na.get("Provider Name"))
        node["kv"] = na.get("voltage")
        node["subtype"] = na.get("substation").fillna(na.get("man_made")) if "substation" in na else na.get("man_made")
        for col in ("pop_total", "pop_elderly", "building_area_m2"):
            node[col] = pd.to_numeric(na.get(col), errors="coerce")
        node["placeholder"] = node["asset_type"].eq("service_zone")
        zone_part = node[node["asset_type"] == "service_zone"]
        point_part = node[node["asset_type"] != "service_zone"].copy()
        point_part["geometry"] = point_part.geometry.representative_point()
        keep = ["asset_id", "system", "asset_type", "subtype", "name", "kv", "pop_total", "pop_elderly",
                "building_area_m2", "placeholder", "geometry"]
        web_nodes = gpd.GeoDataFrame(pd.concat([zone_part[keep], point_part[keep]]), crs=STORE_CRS).to_crs(4326)
        web_nodes["geometry"] = shapely.set_precision(web_nodes.geometry.values, 1e-6)
        nodes_f.write_text(web_nodes.to_json(drop_id=True), encoding="utf-8")

        # 【中文】网页边：两端资产代表点之间的直线（访问 / 控制边数量多，单独标类型便于开关）
        pts = assets.set_index("asset_id").geometry.representative_point()
        web = deps[deps["from_asset"].isin(pts.index) & deps["to_asset"].isin(pts.index)].copy()
        web = web[web["dep_type"] != "access"]
        geom = [shapely.LineString([pts[f], pts[t]]) for f, t in zip(web["from_asset"], web["to_asset"])]
        web_edges = gpd.GeoDataFrame(web[["from_asset", "to_asset", "dep_type", "rule_id", "coupling_id", "gate",
                                          "placeholder"]], geometry=geom, crs=STORE_CRS).to_crs(4326)
        web_edges["geometry"] = shapely.set_precision(web_edges.geometry.values, 1e-6)
        edges_f.write_text(web_edges.to_json(drop_id=True), encoding="utf-8")

        # 【中文】逻辑汇总：系统间的边数，按规则 / 耦合 / 是否占位 / system-level logic summary
        sys_of = assets.set_index("asset_id")["system"]
        deps_sys = deps.assign(from_system=deps["from_asset"].map(sys_of), to_system=deps["to_asset"].map(sys_of))
        summary = (deps_sys.groupby(["from_system", "to_system", "dep_type", "rule_id", "coupling_id", "gate", "placeholder"])
                   .size().rename("n").reset_index())
        write_json(logic_f, {"stats": stats, "links": summary.to_dict(orient="records"),
                             "asset_counts": assets.groupby(["system", "asset_type"]).size().rename("n")
                             .reset_index().to_dict(orient="records")})
        deps = deps.assign(source_id=self.id)
        return AdapterResult(layer=None, tables={"assets": zones, "dependencies": deps})
