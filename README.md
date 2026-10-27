# Nashville 热环境数字孪生（阶段 1 原型）

Downtown Nashville 热浪–基础设施数字孪生的静态网站原型，对应设计方案第 8 节的**阶段 1：道路 + 一次热浪，LST → 资产 → 事件跑通，2.5D 时间回放**。网站只读取 `site/data/` 里的静态文件，不调用 GEE 瓦片链接或任何需要 key 的服务，发布后不会过期。网站界面是英文，代码注释中英双语。

## 目录结构

```
datasets.yaml          数据集登记表：新增数据只改这里（每条 = sources 表的一行）
pipeline/
  schema.py            六张标准表的 schema + 自动校验（设计方案第 3、4 节）
  build.py             入口：python -m pipeline.build
  analysis.py          G1 全链条检查（LST → 道路 → 事件）
  adapters/            每种数据类型一个 adapter
    raster.py            单幅 GeoTIFF → 网页叠加图 + 数值网格 + 标准 COG
    series.py            逐小时栅格序列 → 标准多波段栅格 + 逐小时 exposures + 回放帧
    vector.py            Shapefile / GeoJSON → assets（+ 合成期 exposures）+ 网页 GeoJSON
    events.py            历史事件 → events（空间匹配 asset_id）+ 网页聚合统计
    table.py             CSV / Parquet → couplings 或 dependencies
    timeseries.py        ASOS 逐小时气象 → drivers；EAGLE-I 县级停电 → events
    dependencies.py      依赖规则 → dependencies + 供电分区 + 网页依赖图
  twin/                级联模型 v0：rules（依赖规则 R-*）、params、cascade（Eq. 2–16）、validate
  cascade.py           级联模拟入口：python -m pipeline.cascade
  report.py            由最近一次运行生成 docs/RESULTS.md
twin/                  耦合参数表 couplings.csv（每行带来源与证据）、参考文献 references.yaml
docs/                  学术手册 HANDBOOK.md（逻辑、公式、参数、引用）、RESULTS.md（自动生成）
scripts/               fetch_open_data.py：下载 OSM 与 ASOS 公开数据
templates/             couplings.csv / dependencies.csv 表头模板
raw/                   原始数据（不进 git，清单见 raw/README.md）
data/standard/         标准表 + 标准栅格 + 校验报告 + run 清单（不进 git，存 GCS / Zenodo）
site/                  GitHub Pages 发布的网站
  data/                pipeline 生成的图层文件、layers.json、sources.json、build.json
  vendor/              打包好的 MapLibre GL JS 4.7.1（无 CDN 依赖）
```

## 运行

1. 安装依赖。推荐单独建一个环境，避免和 anaconda base 里的旧包冲突：

   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   # 或：conda install -c conda-forge rasterio geopandas pyarrow pyyaml matplotlib pillow
   ```

2. 按 `raw/README.md` 的清单，从 Google Drive 复制文件到 `raw/`。
3. 构建数据：

   ```bash
   .venv/bin/python -m pipeline.build            # 增量构建
   .venv/bin/python -m pipeline.build --force    # 全部重建（约 3.5 分钟）
   .venv/bin/python -m pipeline.build --strict   # 校验有错误时返回 1（适合 CI）
   ```

   终端逐个显示 `[build] / [skip] / [missing] / [failed]`，最后打印校验结果和本次 `run_id`。缺少或失败的数据集不影响其他数据集。

4. 本地预览：

   ```bash
   cd site && python -m http.server 8000     # 打开 http://localhost:8000
   ```

## 级联模型 v0（阶段 2 雏形）

基于真实资产（OSM 变电站与电力线、CMS 医疗设施、TDOT 桥梁、OSM 信号灯与水务设施、ACS 人口）和占位依赖（Voronoi 供电分区、备用电源、储水时长等），逐小时模拟 2023 年 6–8 月热 → 电 → 水 / 医疗 / 交通 / 人口的连锁反应，并用 EAGLE-I 停电和 311 报修做验证。

```bash
.venv/bin/python scripts/fetch_open_data.py                 # 下载 OSM + ASOS 到 raw/
.venv/bin/python -m pipeline.build                          # 标准表 + 依赖图 + 校验
.venv/bin/python -m pipeline.cascade --runs 2000 --mid-runs 500 --scenarios 0,2,4
.venv/bin/python -m pipeline.report                         # 生成 docs/RESULTS.md
```

- **学术手册**：[docs/HANDBOOK.md](docs/HANDBOOK.md)——逻辑体系、规则（R-*）、每一步公式（Eq. 1–18）、参数表（C-*，标明文献 / 标准 / 内部 / 占位假设）、验证设计、局限与参考文献（DOI 已核实）。
- **结果**：[docs/RESULTS.md](docs/RESULTS.md)，由 `pipeline.report` 从运行结果生成，不手填数字。
- **可视化**：`site/cascade.html`（网站首页左下角 "Cascade model"）。

每次模拟写入 `data/standard/results/<run_id>/`，记录随机种子、全部参数抽样、耦合表哈希和所用构建的 run_id。

## 网站功能

- **时间回放**：选中 "Hourly LST, July 2023" 后，底部出现回放条，可以播放或拖动，逐小时查看 LST。日期条上标出热浪时间窗，每天的柱子是 311 基础设施请求数，缺帧的日期有分隔标记。
- **道路 / 停车场按当前小时着色**：与 LST 图层用同一色带。
- **资产详情卡**：点击道路或停车场，显示属性、逐小时热暴露曲线、热浪期与对照期均值对比。
- **事件图层**：500 m 网格内的 311 请求数（热浪期 vs 对照期）。网站只发布聚合统计，单条记录只在 `data/standard/events.parquet` 里。
- **Data sources**：由 sources 表生成，列出版本、时间、分辨率、许可、文件日期，以及本次构建的 `run_id`、代码版本和校验结果。
- **Chain check**：G1 关卡检查，见下文。

## 标准表

`data/standard/` 对应设计方案第 3 节。六张表始终存在（没有数据时是带表头的空表），全部 GeoParquet，存储 CRS 统一为 **EPSG:32616**：

| 表 | 当前内容 |
| --- | --- |
| `assets.parquet` | 道路 4,137 段 + 地面停车场 993 个；`asset_id` 全局唯一（如 `roads_lst:1105…`），各系统特有属性放在 `attributes` JSON 列 |
| `exposures.parquet` | 约 85 万行：道路和停车场的逐小时 `lst_mean` / `lst_max` / `n_pixels` / `quality_flag`（165 个时刻），以及道路的 2023 年 6–9 月合成值（有 `time_end`） |
| `events.parquet` | 3,367 条 311 基础设施请求，其中道路类请求在 30 m 内按距离匹配到 `asset_id`（2,866 / 3,046） |
| `dependencies.parquet` / `couplings.parquet` | 空表，等文献整理好后用 `table` adapter 接入（模板在 `templates/`） |
| `sources.parquet` | 数据来源登记（提供方、许可、版本、时间、分辨率、质量等级、构建状态） |
| `raster/*.tif` | 裁剪到 AOI 的标准栅格（EPSG:32616，原始 10 m）；逐小时序列为一个 165 波段的 GeoTIFF，波段描述是 UTC 时间 |
| `validation.json` | 最近一次自动校验的结果 |
| `runs/<run_id>.json` | 每次构建的记录：代码版本、配置哈希、包版本、每个数据集的指纹和输入文件 sha256 |

可以直接用 DuckDB 查询：

```sql
INSTALL spatial; LOAD spatial;
-- 热浪期最热的 10 段道路
SELECT asset_id, avg(lst_mean) AS lst
FROM 'data/standard/exposures.parquet'
WHERE source_id = 'lst_hourly_2023' AND quality_flag = 'ok'
  AND timestamp BETWEEN '2023-07-11 05:00Z' AND '2023-07-22 05:00Z'
GROUP BY asset_id ORDER BY lst DESC LIMIT 10;
```

### 自动校验

`pipeline/schema.py` 在每次构建结束时检查：必填字段、存储 CRS、几何是否为空或无效、时间先后和项目时间范围、ID 重复、外键（exposures / events / dependencies 的 `asset_id` 必须在 assets 里，`coupling_id` 必须在 couplings 里）。

### 增量重算

每个数据集有一个输入指纹：本条配置、项目配置、原始文件（大小 + 修改时间）、adapter 代码，以及上游数据集的指纹。指纹不变就跳过；上游重建后，依赖它的下游会自动重算（例如道路变了，逐小时 exposures 和事件匹配都会重跑）。上次失败且输入没变的数据集不会重复尝试，加 `--force` 才会重试。

## G1 全链条检查

`site/data/analysis/chain_check.json`（网站上的 "Chain check"）把道路的逐小时 exposures 和匹配到同一路段的 311 道路请求连起来，按热浪期 LST 五分位汇总事件率。它用来证明链条端到端可查询，**不是统计检验**：事件数很少，也没有控制道路长度以外的任何因素。

热浪时间窗（2023-07-11 – 07-21）沿用 twin_demo 的 `in_event_window`，对照期是之前 10 天，都在 `datasets.yaml` 的 `project` 里配置。验证用哪几次热浪仍是待决问题（设计方案第 9 节）。

## 新增一个数据集

1. 把文件放进 `raw/`。
2. 在 `datasets.yaml` 加一条，例如：

   ```yaml
   - id: lst_20230801_utc19
     kind: raster
     title: LST 2023-08-01 14:00 CDT
     group: Land surface temperature
     file: LST10m_2023-08-01_UTC19.tif
     units: "°C"
     colormap: inferno
     timestamp: "2023-08-01T19:00:00Z"
   ```

3. 运行 `python -m pipeline.build`，提交 `site/data/`。

前端代码不用改：图层面板、图例、点击读数、回放条都由 `site/data/layers.json` 生成。需要支持新的数据类型时，在 `pipeline/adapters/` 写一个新 adapter（实现 `extract` / `transform`，返回 `AdapterResult(layer, tables)`），在 `adapters/__init__.py` 注册；如果它读取其他数据集的资产，在 `upstream()` 里声明，构建顺序会自动排好。

## 发布到 GitHub Pages

1. 新建仓库（建议放在实验室的 GitHub Organization 下），把本文件夹全部推上去，包括 `site/data/`。
2. 仓库 Settings → Pages → Build and deployment → Source 选 **GitHub Actions**。
3. 之后每次 push 到 `main`，`.github/workflows/pages.yml` 会自动发布 `site/`。

`site/data/` 目前约 94 MB，其中回放帧占大头（165 张 WebP 无损图，单张约 0.5 MB）。GitHub 单个文件上限 100 MB；如果仓库太大，可以在 `datasets.yaml` 给序列设 `max_px: 800`（帧会小约 35%，但像元比 10 m 粗）。

## 已知数据问题（需要上游确认）

- **`Nashville_Sentinel2_RGB.tif` 和 `Nashville_LST_10m_Final.tif` 只覆盖西南角约 5%**，downtown AOI 内没有像元，两个图层构建失败。需要从 GEE 按 AOI 重新导出。
- **逐小时 LST 有 26 帧是成对的完全相同帧**，以 UTC19 为中心对称出现（例如 7 月 1 日 UTC16 = UTC22、UTC17 = UTC21、UTC18 = UTC20），集中在 7/1、7/8、7/9、7/13、7/18、7/20 这几天。可能是融合模型在这些天退回到了对称的日变化曲线。这些帧对应的 exposures 标为 `quality_flag = suspect`，回放条上也有提示。
- **逐小时 LST 的 AOI 均值在相邻小时之间跳动很大**（例如 7 月 4 日依次为 23 → 30 → 19 → 35 → 21 °C；7 月 11 日 09:00 已达 61 °C），不像真实的日变化，可能有云污染或尺度问题，建议核对 LST v4.1 hourly 的输入。
- 7 月 14 日没有帧，7 月 19 日只有 1 帧，7 月 21 日只有 2 帧。
- `Nash_ampMap_2023.tif` 的含义和单位（目前标为 "LST amplitude, °C"）。
- 道路 shapefile 的 `road_class` 中文部分已乱码（如 `Interstate / ????`），目前只显示英文部分。

## 第三方组件

- MapLibre GL JS 4.7.1（BSD-3-Clause，见 `site/vendor/maplibre-gl-4.7.1/LICENSE.txt`）
- 可选在线底图：© OpenStreetMap contributors（OSM 官方瓦片，无需 key）。在线底图失效时，自托管的数据图层照常显示。
- hubNashville 311 数据：Nashville Open Data 条款，只发布聚合统计。
