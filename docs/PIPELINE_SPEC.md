# Nashville 热浪级联数字孪生 — 数据 Pipeline 与孪生关系方法规范
# Nashville Heat Cascade Digital Twin — Data Pipeline and Twin-Relation Method Specification

**版本 Version:** spec v1 (draft) · **日期 Date:** 2026-10-30 · **状态 Status:** 方法设计稿，大部分方法尚未编码 / method design; most methods are not coded yet.

**中文：** 本文件从"模型最终要回答的问题"倒推，列出 pipeline 需要的**全部变量**，不论现在有没有数据。没有数据的变量用明确标注的占位方法（placeholder）顶上，并给出将来换成真实数据的路径。目标是：以后任何新数据进来，都能按同一套规范登记、标准化、替换占位，而不用改模型结构。

**English:** This document works backwards from the questions the model must answer and lists **every variable** the pipeline needs, whether or not data exist today. A variable without data is filled by an explicitly flagged placeholder method, together with the path to replace it with real data. The aim is that any new dataset can be registered, standardised and swapped in for a placeholder under one set of rules, without changing the model structure.

**与其他文件的关系 / Related files**

| 文件 File | 内容 Content |
| --- | --- |
| [`docs/HANDBOOK.md`](HANDBOOK.md) | v0 已实现的模型：Eq. 1–18、规则 R-*、参数 C-*、假设 A-* / the implemented v0 model |
| **本文件 this file** | 完整的 pipeline 与方法规范；新方法编号 **M-1…M-44**、通用形式 **G-1…G-6** / full specification; new method ids M-*, general forms G-* |
| [`twin/variables.csv`](../twin/variables.csv) | 变量登记表（机器可读，唯一权威来源）/ variable registry (machine-readable, single source of truth) |
| [`twin/relations.csv`](../twin/relations.csv) | 孪生关系分级方法表 / tiered relation methods |
| [`twin/couplings.csv`](../twin/couplings.csv) | 参数（低 / 中 / 高值与来源）/ parameters with ranges and sources |
| [`docs/DATA_CATALOG.md`](DATA_CATALOG.md) | 由 `python -m pipeline.registry` 自动生成的变量与关系总表 / generated catalogue |

**编号约定 / Numbering.**
- `Eq. n` = v0 已编码（见 HANDBOOK）。`Eq. n` = coded in v0 (see HANDBOOK).
- `M-n` = 本规范定义、尚未编码的方法。`M-n` = specified here, not yet coded.
- `G-n` = 所有系统共用的通用形式。`G-n` = general forms shared by all systems.
- 变量编号 `CLM-` 气象气候、`LST-` 地表温度、`BLD-` 建成环境、`PWR-` 电、`WAT-` 水、`TRN-` 交通、`HLT-` 健康、`POP-` 人口、`MOD-` 模型控制。
  Variable prefixes: CLM climate, LST land surface temperature, BLD built environment, PWR power, WAT water, TRN transportation, HLT health, POP population, MOD model controls.

**状态标记 / Status vocabulary**（`variables.csv` 的 `status` 列）

| status | 中文含义 | Meaning |
| --- | --- | --- |
| `in_model` | 已入库并被 v0 模型使用 | ingested and used by v0 |
| `ingested` | 已入库，模型尚未使用 | in the standard tables, not used yet |
| `derived` | 由 v0 代码从其他变量计算得到 | computed by v0 code |
| `on_drive` | 文件已在 Google Drive，未接入 pipeline | file on Drive, not registered |
| `public` | 公开可下载，尚未下载 | public, not yet downloaded |
| `restricted` | 需要账号、协议或机构合作 | needs an account, agreement or partner |
| `placeholder` | 没有数据，用假设或代理值 | no data; assumption or proxy |
| `planned` | 方法已在本规范定义，代码未实现 | method defined here, not coded |

---

## 实现状态 Implementation status（2026-10-30 更新 / updated）

**中文：** 下列方法已经编码并接入 pipeline，结果见自动生成的 [`RESULTS.md`](RESULTS.md) §7–10。其余 M-* 仍为设计稿。

**English:** The methods below are coded and wired into the pipeline; results are in [`RESULTS.md`](RESULTS.md) §7–10. All other M-* remain design only.

| 方法 Method | 代码 Code | 数据集 Dataset | 与设计的差异 Deviations from the design |
| --- | --- | --- | --- |
| M-6 城市气温场 urban air-temperature field | `pipeline/twin/airfield.py`、`pipeline/adapters/airfield.py`；级联 `--air-field on` | `air_field_2022` | 树冠用 NLCD 2021 林地比例代替（MRLC WCS 不提供全美树冠层）；未用 LST 作预测因子（LST 只覆盖研究区，变电站在外扩 4 km 范围）；走航点无时间戳，不能去除走航期间的时间漂移。Canopy replaced by NLCD forest share; LST not used as a predictor; no time-drift correction. |
| M-18 河温 → 火电降额 → 系统缺口 river → thermal derate → shortfall | `pipeline/twin/river.py`、`pipeline/adapters/river.py`；级联中按运行计算 | `cumberland_thermal` | 只含直流冷却火电（Cumberland、Gallatin），未含水电低流量出力；系统容量取 EIA-860 2022 一年的快照。Thermal plants only (no hydro); 2022 capacity snapshot. 河温用 Mohseni logistic 模型（mohseni1998stream）由 7 日均气温拟合 TDEC 干流样本（n = 161，RMSE 2.38 °C）；USGS 03431500 无水温，只提供流量。Stream temperature: Mohseni logistic on 7-day mean air temperature fitted to TDEC main-stem samples (n = 161, RMSE 2.38 °C); the USGS gauge supplies discharge only. |
| M-28 / M-29 路网行程时间与可达性 network travel time and access | `pipeline/twin/traffic.py`、`pipeline/access.py` | `hpms_2024`、`tmas_2023`、`osm_fire_stations` | 无向图；各道路等级共用一条 TMAS 工作日小时曲线；信号灯熄灭按期望通行能力折减（不是逐次运行）；不含交叉口延误，所以是下限。Undirected; one hourly profile for all classes; expected-capacity approximation; no intersection delay (lower bound). |
| M-43 多年校准 multi-year calibration | `pipeline/calibrate.py` | `eaglei_davidson`（2014-11 – 2025）、`asos_bna`（2014–2025） | 用非风暴日的日最大值（而非逐小时）降低自相关；研究区结果按用户比例放大到全县（A-C1）；TVA 夏季未甩负荷作为硬约束（A-C3）。Daily maxima on non-storm days; AOI scaled to county (A-C1); no-shed constraint (A-C3). 逐日负二项似然退化（ESS 1.4 / 2000），只作诊断；主结果用 ABC：统计量 S = 热日（Tmax ≥ 35 °C）均值 − 凉日（< 32 °C）均值，高斯核，SE 由自助法估计；2018 年覆盖缺口剔除。Per-day NB likelihood is degenerate (ESS 1.4 of 2000) and kept as a diagnostic; the posterior uses ABC on S = hot-day mean − cool-day mean with a Gaussian kernel and bootstrap SE; 2018 excluded as a coverage gap. |

**新增假设 / New assumptions:** A-M6（走航当天的空间距平模式适用于所有日子 / the traverse-day anomaly pattern applies to every day）、A-C1、A-C2、A-C3（见 `pipeline/calibrate.py`）。

---

## 目录 Contents

1. [设计原则 Design principles](#1-设计原则-design-principles)
2. [Pipeline 总体架构 Architecture](#2-pipeline-总体架构-architecture)
3. [从结果反推变量 Backward derivation from outputs](#3-从结果反推变量-backward-derivation-from-outputs)
4. [孪生关系的统一形式 Unified relation formalism](#4-孪生关系的统一形式-unified-relation-formalism)
5. [分系统方法 Methods by system](#5-分系统方法-methods-by-system)
6. [关系分级 Relation tier ladder](#6-关系分级-relation-tier-ladder)
7. [新数据接入规范 Data onboarding protocol](#7-新数据接入规范-data-onboarding-protocol)
8. [数据获取优先级 Data acquisition priorities](#8-数据获取优先级-data-acquisition-priorities)
9. [文件与命令 Files and commands](#9-文件与命令-files-and-commands)

---

## 1. 设计原则 Design principles

**P1 结果驱动 / Output-driven.**
- **中文：** 每个变量都必须能追溯到至少一个最终输出（§3）；不能追溯的变量不进 pipeline，避免"有数据就堆进来"。
- **English:** Every variable must trace to at least one final output (§3). Variables that do not are kept out, so data are not added just because they exist.

**P2 先登记、后使用 / Register before use.**
- **中文：** 模型代码只能读取 `variables.csv` 里登记过的变量。每个变量有唯一编号、单位、时空分辨率、标准表字段、当前状态和占位方法。
- **English:** Model code may only read variables registered in `variables.csv`. Each has one id, units, resolution, standard-table field, status and fallback.

**P3 占位必须显式 / Placeholders are explicit.**
- **中文：** 占位值永远带 `placeholder` 标记，并且出现在参数表、依赖边、网页和报告里。占位方法本身也要有公式，这样换数据时接口不变。
- **English:** A placeholder always carries a flag that appears in the parameter table, the edges, the viewer and the reports. The placeholder method has its own formula, so the interface does not change when real data arrive.

**P4 关系分级 / Tiered relations.**
- **中文：** 每条孪生关系有一条"方法阶梯"，从 0 级（纯假设）到 4 级（用观测校准）。新数据的作用是让某条关系上一级，而不是改写模型（§6）。
- **English:** Each relation has a method ladder from tier 0 (assumption) to tier 4 (calibrated against observations). New data move a relation up the ladder rather than rewriting the model (§6).

**P5 同一套状态代数 / One state algebra.**
- **中文：** 电、水、交通、健康四个系统用同一种节点状态、门逻辑和缓冲形式（§4）。新系统或新设施类型只需要声明"需要什么、有什么缓冲"。
- **English:** Power, water, transport and health share one node-state, gate and buffer formalism (§4). A new system or facility type only declares what it needs and what buffers it has.

**P6 可复现 / Reproducible.**
- **中文：** 每次构建和模拟都记录输入文件哈希、代码版本、参数抽样和随机种子（沿用 v0 的 run manifest）。
- **English:** Every build and simulation records input hashes, code version, parameter draws and seed (the v0 run manifests).

---

## 2. Pipeline 总体架构 Architecture

```
L0 原始数据 Raw ──► L1 标准化 Standardise ──► L2 驱动与暴露 Drivers & exposure ──► L3 孪生图 Twin graph
                                                                                              │
L8 发布 Publish ◄── L7 验证与校准 Validate & calibrate ◄── L6 影响 Impacts ◄── L5 级联 Cascade ◄── L4 状态与易损性 State & fragility
                         ▲                                                                    │
                         └────────────── L7' 不确定性与情景 Uncertainty & scenarios ◄────────────┘
```

| 层 Layer | 中文说明 | English | 输入 Inputs | 输出 Outputs | 代码 Code | v0 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| **L0** 原始 Raw | 下载或复制原始文件，记录来源、时间和 sha256 | Acquire raw files with provenance and sha256 | Drive、开放 API | `raw/`、`raw/open_data_manifest.json` | `scripts/fetch_open_data.py` | 部分 partial |
| **L1** 标准化 Standardise | 适配器把每个数据集转成 7 张标准表；统一 CRS、时间、单位、编号 | Adapters write the 7 standard tables; CRS, time, units, ids | `datasets.yaml` | `data/standard/*.parquet` | `pipeline/adapters/*`、`pipeline/schema.py` | 已实现 done |
| **L2** 驱动与暴露 Drivers & exposure | 派生气象指标（热指数、热浪、夜间最低温）、城市气温场、资产 LST 暴露、路面温度 | Derived meteorology, urban air-temperature field, asset LST exposure, pavement temperature | CLM-*、LST-*、BLD-* | `drivers`、`exposures` | `series.py`、`timeseries.py`；M-1…M-10 计划中 | 部分 partial |
| **L3** 孪生图 Twin graph | 由关系规则 R-* 生成节点与依赖边；每条边带方法等级 | Rules R-* generate nodes and edges with method tiers | assets、relations.csv | `dependencies`、`graph_*.geojson` | `pipeline/twin/rules.py` | 已实现 done |
| **L4** 状态与易损性 State & fragility | 每类资产由暴露算出失效概率或服务水平 | Hazard → failure probability / service level per asset class | L2 + couplings | 逐时状态 hourly states | `pipeline/twin/cascade.py` | 电力已实现 power done |
| **L5** 级联 Cascade | 在图上按门逻辑、缓冲和修复逐时传播 | Hourly propagation with gates, buffers, restoration | L3 + L4 | 节点逐时状态 | `cascade.py` | 部分 partial |
| **L6** 影响 Impacts | 人口暴露、设施服务损失、健康结局、交通可达性 | Population exposure, service loss, health, access | L5 + POP-* + HLT-* | KPI | `cascade.py`；M-31…M-41 计划中 | 部分 partial |
| **L7'** 不确定性 Uncertainty | 参数抽样、情景、敏感性 | Parameter sampling, scenarios, sensitivity | couplings | 多次运行分布 | `pipeline/cascade.py` | 已实现 (Spearman) |
| **L7** 验证校准 Validate | 与 EAGLE-I、311、ED 等观测比较；用观测更新参数 | Compare with observations; update parameters | 观测 OBS | 指标、后验 | `pipeline/twin/validate.py`；M-43 计划中 | 部分 partial |
| **L8** 发布 Publish | 网页文件，只发布汇总 | Site files, aggregates only | 全部 | `site/data/` | `report.py`、adapters | 已实现 done |

**标准表 / Standard tables**（v0 已有，见 `pipeline/schema.py`）：`assets`、`dependencies`、`couplings`、`exposures`、`events`、`sources`、`drivers`。

**本规范建议的扩展 / Proposed extensions**（均为可选列，旧数据不受影响 / optional columns, old data unaffected）：

| 表 Table | 新列 New column | 含义 Meaning |
| --- | --- | --- |
| `dependencies` | `method_tier` | 生成这条边的方法等级（§6），如 `1`、`1s`、`3` / tier of the method that produced the edge |
| `dependencies` | `lag_h` | 依赖生效的时间滞后（小时），默认 0 / lag in hours (G-2) |
| `dependencies` | `weight` | 上游能提供的需求份额，用于连续服务水平（G-2）/ share of requirement deliverable by the upstream |
| `dependencies` | `buffer_var` | 缓冲变量编号，如 `HLT-04` / buffer variable id (G-3) |
| `dependencies` | `k_required` | k-of-n 门需要的上游数量 / k for k-of-n gates |
| `drivers`、`exposures` | `var_id` | 对应 `variables.csv` 的变量编号 / registry id |
| 新表 new `states`（结果层） | `run`、`asset_id`、`t`、`var_id`、`value` | 模拟输出的长表格式 / long-format simulation states |

---

## 3. 从结果反推变量 Backward derivation from outputs

**中文：** 下面列出模型要给出的 8 类结果（O1–O8），以及每类结果向下需要的变量。括号里是变量编号和当前状态：✅ 有数据（in_model / ingested / derived），🟡 数据在手但未接入（on_drive / public），🔒 需要合作方（restricted），⬜ 占位或计划（placeholder / planned）。

**English:** The eight result families (O1–O8) and the variables each needs. Marks: ✅ available, 🟡 in hand or public but not connected, 🔒 needs a partner, ⬜ placeholder or planned.

### O1 高温期间的停电人时 / Person-hours without power during heat

```
O1  E_c = Σ_t Pop_out(t) · 1[θ_A(t) ≥ T_heat]                        (Eq.14; M-41 by group)
├── Pop_out(t) = Σ_z pop_z · d_z(t)                                  POP-14 ✅
│   ├── pop_z  分区人口 zone population                              POP-06 ✅ (areal) → M-39 dasymetric ⬜
│   │   ├── ZCTA 人口 / 65+ / 贫困                                    POP-01..03 ✅
│   │   └── 住宅建筑面积 residential floor area                       BLD-01 ✅  BLD-02 🟡  BLD-03 🟡
│   └── d_z(t) 分区停电 zone outage                                   PWR-28 ✅
│       ├── 供电分区 service zones                                    PWR-20 🔒 → Voronoi ⬜ (R-P3)
│       ├── e_s(t) 变电站带电 energised                               PWR-17 ✅
│       │   ├── 拓扑 topology                                         PWR-01 ✅ PWR-02 ✅ PWR-24 🔒
│       │   ├── 热失效 thermal failure p_s(t)                         PWR-14 ✅
│       │   │   ├── θ_H 热点温度 hot spot                              PWR-13 ✅
│       │   │   │   ├── θ_A 气温                                       CLM-01 ✅ → CLM-19 城市气温场 ⬜
│       │   │   │   ├── K_s 负荷率 = L/L^r                             PWR-03 🔒  PWR-04 ⬜
│       │   │   │   │   └── 负荷–气温 load–temperature                  PWR-05/06 ✅ (monthly) → PWR-07 🟡 (hourly, M-11)
│       │   │   │   └── 热参数 thermal constants                       PWR-11 ✅ (typical)
│       │   │   └── 易损性 fragility θ50, σ                            PWR-15 ⬜
│       │   ├── 过载转移 overload transfer α                           PWR-16 ✅
│       │   └── 修复 repair R_h                                        PWR-18 ⬜ → M-16
│       ├── 配电变压器 distribution transformers                       PWR-21 🔒 → M-15 ⬜
│       └── 外部电源 / 火电降额 external supply                        PWR-09 🟡 WAT-13/14 🟡 → M-18 ⬜
└── T_heat 复合阈值 compound threshold                                POP-16 ⬜ → HLT-14 (local curve)
```

### O2 脆弱人群的室内高温暴露 / Indoor heat exposure of vulnerable groups

```
O2  E_in,g = Σ_t Σ_z pop_{z,g} · 1[T_in,z(t) ≥ T_thr,g]              (M-33)
├── pop_{z,g} 65+、独居老人、5 岁以下、依赖电力设备者                   POP-02 ✅ POP-08 🟡 POP-17 🟡 HLT-17 🟡
├── T_in(t) 室内温度 indoor temperature (M-32)                        HLT-22 ⬜
│   ├── 停电状态与时长 outage and duration                             PWR-28 ✅
│   ├── 室外气温（街区）outdoor air temperature                        CLM-19 ⬜ ← CLM-20 🟡 BLD-05/06 🟡 LST-01 ✅
│   ├── 建筑热时间常数 τ_b、得热 gains                                  BLD-08 ⬜ BLD-09 ⬜ ← BLD-03 🟡
│   └── 空调普及率 AC share                                            BLD-04 🟡
└── 室内阈值 indoor threshold                                          HLT-23 ⬜
```

### O3 医疗设施服务中断小时 / Health-facility service-hours lost

```
O3  Σ_t y_f(t)                                                        (Eq.11 → M-31)
├── 供电 e_f(t) ∨ 备用 (B_f ∧ b_f(t) > 0)                             PWR-28 ✅ HLT-03 ⬜ HLT-04 ⬜ HLT-08 ⬜
├── 供水 ¬w_out(t) ∨ 自备 s_f(t) > 0                                   WAT-11 ✅ HLT-09 ⬜
└── 可达 τ_access ≤ τ_max                                              TRN-16 ⬜
```

### O4 透析中断与转诊 / Missed dialysis sessions and relocation

```
O4  M_d = displaced_d − reassigned_d                                   (M-35)
├── 透析中心状态 y_f                                                    HLT-20 ✅
├── 患者数 patients                                                    HLT-06 🟡 (stations ✅ HLT-05)
└── 路网行程时间 travel time                                            TRN-16 ⬜ ← TRN-10/11/12 🟡
```

### O5 高温（叠加停电）归因死亡与急诊 / Heat-attributable deaths and ED visits with outage modifier

```
O5  AN_d = B_d · (1 − 1/RR_d)                                          (M-34)
├── 基线死亡 B_d                                                        HLT-13 🟡
├── 温度–死亡曲线 MMT、β_h                                               HLT-14 ⬜
├── 停电修正 RR_out 或放大系数 A_HW                                      HLT-15 ✅ HLT-16 ✅ (literature)
├── 停电人口比例 o_d                                                    POP-14 ✅
└── 校准观测 ED visits / deaths                                          HLT-12 🔒
```

### O6 供水服务损失 / Water service loss

```
O6  Σ_t pop_served · w_out(t)  或 / or  1 − DSR(t)                      (Eq.13 → M-20, M-22)
├── 产能 Q_prod(t) = Σ Q_k x_k(t)                                       WAT-02 ⬜ WAT-03 🔒 (M-21)
│   └── 水厂 / 泵站供电与备用                                             PWR-28 ✅ WAT-09 ⬜
├── 需求 D(t) 与气温斜率                                                 WAT-07 ⬜ WAT-08 ⬜ (M-19)
├── 储水 S_max                                                          WAT-04 ⬜
└── 管网与压力分区 network and pressure zones                            WAT-05 🔒 WAT-06 🟡 (synthetic)
```

### O7 交通系统表现 / Transportation performance

```
O7a 路面病害概率 pavement distress p_i                                    (Eq.15 → M-10, M-17)
    ├── T7 / T_pav                                                      LST-09 ✅ LST-10 ⬜ LST-08 ⬜
    ├── PG 等级 binder grade                                             TRN-03 ⬜
    └── 校准 311 路面报修                                                 TRN-22 ✅ TRN-02 ✅
O7b 信号灯熄灭与通行能力 dark signals and capacity                         (Eq.16 → M-27, M-28)
    ├── 电池时长 battery hours                                           TRN-07 ⬜
    └── 交通量与容量 volumes and capacity                                 TRN-10 🟡 TRN-11 🟡 TRN-12 🟡
O7c 可达性 / 急救响应 access and EMS response                              (M-29)
    └── 路网 + BPR + 设施状态                                             TRN-13 ⬜ TRN-21 🟡 HLT-20 ✅
O7d 铁路屈曲、公交站暴露 rail buckling, transit-stop exposure              (M-26, M-30)
    └── TRN-17 🟡 TRN-18 ⬜ TRN-19 🟡 TRN-20 🔒 CLM-08 🟡 CLM-13 ⬜
```

### O8 级联放大 / Cascade amplification

```
O8  过载跳闸 / 热失效 (v0)；跨系统放大矩阵 M_ab (M-44)
    └── 每次失效记录其直接原因（上游节点、规则编号）/ every failure records its cause
```

**中文小结：** 结果 O1、O3、O8 在 v0 已能出数，但关键环节（变压器额定值、易损性、供电分区）仍是占位。O2、O4、O5、O7c 需要先实现 M-29、M-32、M-34、M-35 等方法；其中大部分输入数据已经在 Drive 或可公开下载（§8）。

**English summary:** O1, O3 and O8 are produced by v0, but their key links (transformer ratings, fragility, service zones) are placeholders. O2, O4, O5 and O7c need methods M-29, M-32, M-34 and M-35 first; most of their inputs are already on Drive or public (§8).

---

## 4. 孪生关系的统一形式 Unified relation formalism

**中文：** 所有系统的节点都用同一套状态和逻辑。一个节点（变电站、水厂、信号灯、医院……）在每个时刻有：自身是否因灾害失效、对每一类"需求"是否被满足、缓冲还能撑多久。下面 G-1 至 G-6 是所有关系共用的形式；v0 的 Eq. 9、11、13、16 都是它们的特例。

**English:** Every node in every system uses the same state and logic. At each hour a node has its own hazard failure, whether each class of requirement is met, and how long its buffers last. G-1 to G-6 are shared by all relations; v0 Eq. 9, 11, 13 and 16 are special cases.

### G-1 节点状态 Node state

**中文：** 节点 $`i`$ 在时刻 $`t`$ 的状态包括：自身失效 $`F_i(t)\in\{0,1\}`$（由 L4 易损性抽样，持续到修复完成）；功能状态 $`x_i(t)\in\{0,1\}`$；可选的连续服务水平 $`q_i(t)\in[0,1]`$（用于部分停电、部分供水）。

**English:** Node $`i`$ at hour $`t`$ has an own failure $`F_i(t)`$ (drawn from its fragility in L4, lasting until repaired), a functional state $`x_i(t)`$, and optionally a service level $`q_i(t)\in[0,1]`$ for partial outages or partial supply.

### G-2 需求组合与门逻辑 Requirement composition and gates

**中文：** 节点的需求分成若干类 $`k\in K(i)`$（电、水、控制、可达……）。每类需求有一组上游 $`U_k(i)`$ 和一种门：series（全部上游都要）、redundant（任一上游即可）、k-of-n（至少 $`k`$ 个上游）。依赖可以有滞后 $`\ell_{ui}`$ 小时。

**English:** A node's requirements fall into classes $`k\in K(i)`$ (power, water, control, access, …). Each class has upstream set $`U_k(i)`$ and a gate: series (all needed), redundant (any one suffices) or k-of-n. An edge may act with a lag $`\ell_{ui}`$ hours.

```math
x_i(t)=\neg F_i(t)\;\wedge\;\bigwedge_{k\in K(i)}\Gamma_k\Big(\{x_u(t-\ell_{ui}) : u\in U_k(i)\}\Big),\qquad
\Gamma_{\mathrm{series}}=\bigwedge_u x_u,\quad
\Gamma_{\mathrm{redundant}}=\bigvee_u x_u,\quad
\Gamma_{k\text{-of-}n}=\mathbf 1\Big[\sum_u x_u\ge k\Big]
```

连续服务水平版本 / continuous version（$`w_{ui}`$ = 上游 $`u`$ 能提供的需求份额 / share of the requirement deliverable by $`u`$）：

```math
q_i(t)=\big(1-F_i(t)\big)\,\min_{k\in K(i)}\;\min\Big(1,\;\sum_{u\in U_k(i)} w_{ui}\,q_u(t-\ell_{ui})\Big)
```

**中文：** 当所有 $`w_{ui}=1`$ 时，连续版本退化为 redundant 门；当只有一个上游时，退化为 series 门。

**English:** With all $`w_{ui}=1`$ the continuous form reduces to the redundant gate; with a single upstream it reduces to series.

### G-3 缓冲 Buffers

**中文：** 备用发电机、储水、电池等是"有时限的替代上游"。需求类 $`k`$ 在上游失效时，如果缓冲 $`b_{ik}(t)>0`$ 且启动成功，仍算满足。缓冲在使用时按时间消耗，恢复供应后按速率 $`r_{ik}`$ 回充。启动是否成功在每次失效事件开始时抽一次：$`B_{ik}\sim\mathrm{Bernoulli}(1-p^{bf}_{ik})`$。

**English:** Backup generators, storage and batteries are time-limited substitute upstreams. Requirement $`k`$ still holds while the upstream is down if buffer $`b_{ik}(t)>0`$ and the buffer started; it drains while used and refills at rate $`r_{ik}`$ once supply returns. Start success is drawn once per outage episode.

```math
\tilde\Gamma_k(t)=\Gamma_k(t)\;\vee\;\big(B_{ik}\wedge b_{ik}(t-1)>0\big),\qquad
b_{ik}(t)=\begin{cases}
\max\big(0,\;b_{ik}(t-1)-\Delta t\big) & \Gamma_k(t)=0\\
\min\big(b^{\max}_{ik},\;b_{ik}(t-1)+r_{ik}\Delta t\big) & \Gamma_k(t)=1
\end{cases}
```

**中文：** v0 的医院备用电源（Eq. 11）相当于 $`b^{\max}=\infty`$；v0 的储水（Eq. 13）相当于 $`b^{\max}=h_s`$、$`r=\infty`$。

**English:** v0 hospital backup (Eq. 11) is the case $`b^{\max}=\infty`$; v0 storage (Eq. 13) is $`b^{\max}=h_s`$, $`r=\infty`$.

### G-4 每小时的不动点求解 Fixed-point solve per hour

**中文：** 每个小时内反复应用 G-2/G-3，直到没有节点状态改变。因为失效只会扩散不会自行恢复（修复在小时之间发生），迭代单调、最多 $`|V|`$ 轮收敛。v0 的 Eq. 8–9 循环（最多 40 轮）就是这个过程。

**English:** Within each hour, apply G-2/G-3 repeatedly until no state changes. Failures only spread within an hour (repairs happen between hours), so the iteration is monotone and converges in at most $`|V|`$ rounds; the v0 Eq. 8–9 loop is this procedure.

```math
\mathbf x^{(n+1)}(t)=\Psi\big(\mathbf x^{(n)}(t)\big),\qquad \text{stop when } \mathbf x^{(n+1)}=\mathbf x^{(n)}
```

### G-5 聚合部门的投入产出近似 Aggregate sectors (inoperability input–output)

**中文：** 对没有资产级数据的部门（如商业、通信），用 Haimes & Jiang (2001) 的不可运行度投入产出模型（IIM）做 0 级近似：$`\mathbf q`$ 为各部门不可运行度，$`A^*`$ 为部门间依赖矩阵，$`\mathbf c^*`$ 为直接冲击。

**English:** For sectors without asset data (e.g. commerce, telecom), use the inoperability input–output model of Haimes & Jiang (2001) as a tier-0 approximation [haimes2001].

```math
\mathbf q=A^*\mathbf q+\mathbf c^*\;\Rightarrow\;\mathbf q=(I-A^*)^{-1}\mathbf c^*
```

### G-6 时间步换算 Time-step conversion

**中文：** 易损性给出的是每小时概率 $`p_{1h}`$。当时间步改为 $`\Delta t`$（如 EAGLE-I 的 15 分钟）时，按常数风险率换算，保证结果与步长无关。

**English:** Fragilities give hourly probabilities. When the step changes to $`\Delta t`$ (e.g. 15 min), convert through a constant hazard rate so results do not depend on the step.

```math
h=-\ln(1-p_{1h}),\qquad p_{\Delta t}=1-e^{-h\,\Delta t}
```

---

## 5. 分系统方法 Methods by system

**中文：** 每个方法给出：用途、公式、输入变量、参数、当前数据状态和引用。参数编号带 "(planned)" 的是新参数，尚未写入 `couplings.csv`。引用键见 [`twin/references.yaml`](../twin/references.yaml)。

**English:** Each method lists purpose, formula, inputs, parameters, data status and citation. Parameter ids marked "(planned)" are not yet in `couplings.csv`. Citation keys refer to `twin/references.yaml`.

### 5.1 气象与气候驱动 Climate drivers (L2)

#### M-1 相对湿度 Relative humidity

**中文：** 用 Magnus 公式（Alduchov & Eskridge 1996 系数）由气温和露点算相对湿度。用途：检查 ASOS 的 relh，并给没有湿度观测的数据源（如格点气温）补湿度。
**English:** Relative humidity from temperature and dew point by the Magnus form with Alduchov & Eskridge (1996) coefficients [alduchov1996]; used to check ASOS relh and to add humidity where only dew point exists.

```math
e_s(T)=6.1094\exp\!\left(\frac{17.625\,T}{T+243.04}\right)\ \mathrm{hPa},\qquad
RH=100\,\frac{e_s(\theta_D)}{e_s(\theta_A)}
```

输入 Inputs：CLM-01, CLM-02 ✅ · 输出 Output：CLM-03

#### M-2 热指数 Heat index

**中文：** 美国国家气象局（NWS）热指数（Rothfusz 1990）。先算简式；简式与气温的平均值 ≥ 80 °F 时用完整回归式，并做低湿和高湿修正。单位为 °F、%。
**English:** NWS heat index [rothfusz1990]. Compute the simple form first; if its average with $`T`$ is ≥ 80 °F use the full regression with the low- and high-humidity adjustments. $`T`$ in °F, RH in %.

```math
HI_s=0.5\,\big[T+61+1.2\,(T-68)+0.094\,RH\big]
```

```math
\begin{aligned}
HI={}&-42.379+2.04901523\,T+10.14333127\,RH-0.22475541\,T\,RH-6.83783\times10^{-3}T^2\\
&-5.481717\times10^{-2}RH^2+1.22874\times10^{-3}T^2RH+8.5282\times10^{-4}T\,RH^2-1.99\times10^{-6}T^2RH^2
\end{aligned}
```

修正 Adjustments：若 $`RH<13`$ 且 $`80\le T\le112`$，减去 $`\frac{13-RH}{4}\sqrt{\frac{17-|T-95|}{17}}`$；若 $`RH>85`$ 且 $`80\le T\le87`$，加上 $`\frac{RH-85}{10}\cdot\frac{87-T}{5}`$。

输入 Inputs：CLM-01, CLM-03 ✅ · 输出 Output：CLM-12 · 用于 Used in：M-33, M-34, M-41

#### M-3 湿球黑球温度 WBGT

**中文：** 室外 WBGT 由自然湿球温度 $`T_{nwb}`$、黑球温度 $`T_g`$ 和气温组成；$`T_{nwb}`$、$`T_g`$ 用 Liljegren 等（2008）的能量平衡模型迭代求解（需要气温、湿度、风速、太阳辐射、气压和太阳天顶角），采用已发表的开源实现。缺辐射数据时用阴影近似。
**English:** Outdoor WBGT from natural wet-bulb, globe and air temperature; $`T_{nwb}`$ and $`T_g`$ come from the Liljegren et al. (2008) energy-balance model [liljegren2008] using a published implementation. Without irradiance, use the shade approximation.

```math
WBGT_{out}=0.7\,T_{nwb}+0.2\,T_g+0.1\,\theta_A,\qquad WBGT_{shade}\approx0.7\,T_{nwb}+0.3\,\theta_A
```

输入 Inputs：CLM-01..04 ✅, CLM-08 🟡, CLM-11 🟡 · 输出 Output：CLM-13 · 用于 Used in：M-30

#### M-4 夜间最低温、制冷度时、连续热夜 Night minimum, cooling degree hours, hot nights

**中文：** 夜间最低温决定变压器和室内能否"缓过来"。日界按当地时间（America/Chicago）。
**English:** Night-time minimum temperature controls whether transformers and homes recover overnight. Days use local time (America/Chicago).

```math
T^{night}_d=\min_{t\in[21{:}00_{d-1},\,06{:}00_d]}\theta_A(t),\qquad
CDH_d=\sum_{t\in d}\max\big(0,\theta_A(t)-T_b\big),\qquad
N^{hn}_d=\begin{cases}N^{hn}_{d-1}+1 & T^{night}_d\ge T_{hn}\\0&\text{otherwise}\end{cases}
```

参数 Parameters：$`T_b=18.3`$ °C（65 °F，度日惯例 / degree-day convention），$`T_{hn}`$ 热夜阈值（占位 24 °C / placeholder）。输入 CLM-01 ✅ · 输出 CLM-14, CLM-15

#### M-5 热浪定义：超额热因子 Heat-wave definition: excess heat factor

**中文：** 用 Nairn & Fawcett (2015) 的 EHF 替代人工选定的热浪窗口。$`T_d`$ 为日平均气温（日最高与最低的平均），$`T_{95}`$ 为气候期日平均气温的第 95 百分位。EHF > 0 为热浪日；EHF 超过所有正值的第 85 百分位为强热浪。
**English:** Replace the hand-picked heat window with the excess heat factor [nairn2015]. $`T_d`$ is the daily mean, $`T_{95}`$ the 95th percentile of daily means over the climatology. EHF > 0 marks a heat-wave day; above the 85th percentile of positive EHF marks a severe one.

```math
EHI^{sig}_d=\frac{T_d+T_{d+1}+T_{d+2}}{3}-T_{95},\qquad
EHI^{accl}_d=\frac{T_d+T_{d+1}+T_{d+2}}{3}-\frac{1}{30}\sum_{j=d-30}^{d-1}T_j,\qquad
EHF_d=EHI^{sig}_d\cdot\max\big(1,EHI^{accl}_d\big)
```

**中文注意：** 现有 GHCN-D 文件只有 2017–2024，原文建议 30 年气候期；可从 NOAA 公开下载更长的 BNA 序列。
**English note:** the Drive file covers 2017–2024 only; the paper uses a 30-year climatology, which can be downloaded from NOAA.

输入 Inputs：CLM-06 🟡 · 输出 Output：CLM-16 → `datasets.yaml project.heatwave`

#### M-6 城市气温场 Urban air-temperature field

**中文：** v0 用机场一个站代表全城（A-D4）。M-6 用 2022 年走航测温（早、午、晚三个时段）标定一个回归模型，把站点气温扩展成 10–100 m 的气温场，方法思路同 Shandas 等（2019）和 Ho 等（2014）。$`z_k(x)`$ 为空间预测因子：LST 距平、不透水面、树冠、高程、离河距离。$`b_k(h)`$ 为对应时段的系数，在三个时段之间按小时线性插值，夜间用傍晚系数。
**English:** v0 uses one airport station for the whole city (A-D4). M-6 calibrates a regression on the 2022 traverses (morning / afternoon / evening) to turn the station series into a 10–100 m field, following Shandas et al. (2019) [shandas2019] and Ho et al. (2014) [ho2014]. Predictors $`z_k(x)`$: LST anomaly, impervious fraction, canopy, elevation, distance to river. Coefficients $`b_k(h)`$ are interpolated linearly between the three periods; night uses the evening coefficients.

```math
\theta_A(x,t)=\theta_{A,\mathrm{ref}}(t)+\sum_k b_k\big(h(t)\big)\,\big[z_k(x)-z_k(x_{\mathrm{ref}})\big]+\varepsilon(x,t)
```

检验 Check：按走航路线分块交叉验证（留出整段路线），报告 RMSE。Block cross-validation by traverse route; report RMSE.

输入 Inputs：CLM-01 ✅, CLM-20/21 🟡, LST-06 ✅, BLD-05/06 🟡 · 输出 Output：CLM-19

#### M-7 情景构造 Scenario construction

**中文：** 三种情景构造方式，可在 `--scenarios` 中选择：
- (a) 均匀增温 $`\delta`$（v0 现有）；
- (b) 分位数增量映射（QDM，Cannon 等 2015）：用 LOCA2（Pierce 等 2023）在 Nashville 格点的历史期与未来期分布，对日最高、日最低温按分位数加增量，再按日内位置把增量分配到每小时；
- (c) 故事线：把历史热浪（如 2023-08-21 至 26）原样回放并叠加增温。

**English:** Three scenario types:
- (a) uniform offset (v0);
- (b) quantile delta mapping [cannon2015] with LOCA2 [pierce2023]: add quantile-dependent deltas to daily Tmax and Tmin, then spread them over the hours by each hour's position within the day;
- (c) storylines: replay observed heat waves with offsets.

```math
\Delta_m(q)=F^{-1}_{\mathrm{fut},m}(q)-F^{-1}_{\mathrm{hist},m}(q),\qquad
\theta'_A(t)=\theta_A(t)+\Delta^{\min}_d+\big(\Delta^{\max}_d-\Delta^{\min}_d\big)\frac{\theta_A(t)-T^{\min}_d}{T^{\max}_d-T^{\min}_d}
```

其中 where $`\Delta^{\max}_d=\Delta_m\big(F_{\mathrm{obs},m}(T^{\max}_d)\big)`$，$`\Delta^{\min}_d`$ 同理 / likewise。输入 CLM-06 🟡, CLM-24 🟡 · 控制 MOD-01

#### M-8 风暴掩膜 Storm mask

**中文：** 验证和校准只能用"非风暴小时"，否则停电被雷暴主导。v0 用 ±3 小时雷暴报告；M-8 再加上 NOAA 风暴事件库当天 Davidson 县的雷暴大风、冰雹、龙卷、山洪和大风事件。
**English:** Validation and calibration use non-storm hours. v0 uses thunder within ±3 h; M-8 adds NOAA Storm Events records for Davidson County on the same day.

```math
s(t)=\mathbf 1\big[\exists\,t'\in[t-3,t+3]: TS(t')=1\big]\;\vee\;\mathbf 1\big[\text{storm event in county on day}(t)\big]
```

输入 Inputs：CLM-05 ✅, CLM-18 🟡 · 输出 Output：CLM-17

### 5.2 地表温度 Land surface temperature (L2)

#### M-9 缺测与可疑帧填补 Gap filling and suspect frames

**中文：** 逐小时 LST 有缺日（07-14）、26 帧重复、以及不合理的小时跳变，而且没有覆盖真实热浪。M-9 用"同一小时的像元气候态 + 气温距平"填补：$`\overline{\mathrm{LST}}_p(h)`$ 为有效帧在小时 $`h`$ 的平均，$`\kappa_p(h)`$ 为像元（或地类）LST 对气温距平的回归斜率。有 GOES 数据时，改用 GOES 的距平作锚点。小时变化超过 15 K/h 的像元标记为 `suspect`。
**English:** The hourly LST has a missing day, 26 duplicate frames, implausible hourly jumps, and does not cover the real heat waves. M-9 fills gaps with the same-hour pixel climatology plus an air-temperature anomaly; with GOES available, the GOES anomaly is the anchor. Pixels changing more than 15 K/h are flagged suspect.

```math
\widehat{\mathrm{LST}}_p(d,h)=\overline{\mathrm{LST}}_p(h)+\kappa_p(h)\big[\theta_A(d,h)-\bar\theta_A(h)\big]
\quad\text{or}\quad
\overline{\mathrm{LST}}_p(h)+\big[\mathrm{LST}_{GOES}(x_p;d,h)-\overline{\mathrm{LST}}_{GOES}(x_p;h)\big]
```

**中文：** 这是占位方法，正式做法是用 LST v4.1 pipeline 重跑热浪期（LST-08）。
**English:** This is a placeholder; the real fix is to re-run LST v4.1 for the heat-wave dates (LST-08).

输入 LST-01 ✅, CLM-01 ✅, LST-11 🟡 · 输出 LST-08 ⬜

#### M-10 路面温度 Pavement temperature

**中文：** PG 分级定义在 20 mm 深度的 7 日平均最高路面温度，而 LST 是表面皮温，会偏高（A-D3）。M-10 用 LTPPBind 高温模型（Mohseni 1998）由 7 日平均最高气温 $`T_{air}`$（°C）、纬度 Lat 和深度 $`d`$（mm）算路面温度，再用 LST 提供路段之间的相对差异，$`\lambda`$ 为占位系数（0.3–0.7）。系数需在使用前对照 FHWA 原报告核实。
**English:** PG grading uses the 7-day average maximum at 20 mm, whereas LST is a skin temperature (A-D3). M-10 uses the LTPPBind high-temperature model [mohseni1998] with the 7-day mean maximum air temperature, latitude and depth, and lets LST supply the between-segment anomaly; $`\lambda`$ is a placeholder (0.3–0.7). Check the coefficients against the FHWA report before use.

```math
T_{pav}(d)=54.32+0.78\,T_{air}-0.0025\,\mathrm{Lat}^2-15.14\log_{10}(d+25)+z\sqrt{9+0.61\,\sigma_{air}^2}
```

```math
T_{pav,i}=T_{pav}(20)+\lambda\,\big(T7_i-\operatorname{median}_j T7_j\big)
```

$`z=0`$ 为期望值；$`z=2.055`$ 对应 98% 可靠度。$`z=0`$ gives the expected value; $`z=2.055`$ gives 98% reliability. 输入 CLM-06 🟡, LST-09 ✅ · 输出 LST-10 · 替换 Eq.15 中的 $`T7_i`$

### 5.3 电力 Power (L4–L5)

v0 已实现 Eq. 2–10（负荷、IEEE C57.91 热模型、易损性、过载转移、供电依赖、修复）。以下是补全方法。
v0 implements Eq. 2–10. The methods below complete the power module.

#### M-11 逐时负荷模型 Hourly load model

**中文：** v0 把月度售电量的斜率直接用于逐时（A-P4）。M-11 用 EIA-930 的 TVA 逐时负荷拟合：$`L_0(h,w)`$ 为"小时 × 工作日/周末"的基准曲线，$`\beta_h`$ 为分时段的气温斜率，$`\bar\theta_{24}`$ 为前 24 小时平均气温，代表建筑热惯性。TVA 远大于 Nashville，所以只取相对形状和斜率，再按 M-12 分配到变电站。
**English:** v0 applies a monthly-sales slope hourly (A-P4). M-11 fits TVA hourly demand from EIA-930 [eia930]: a baseline by hour and day type, an hour-specific slope, and a 24-h mean temperature term for building thermal inertia. TVA is much larger than Nashville, so only the relative shape and slopes are used; loads are allocated to stations by M-12.

```math
L(t)=L_0\big(h(t),w(t)\big)\Big[1+\beta_{h(t)}\max\big(0,\theta_A(t)-T_0\big)\Big]+\beta_{24}\max\big(0,\bar\theta_{24}(t)-T_0\big)+\varepsilon(t)
```

替换 Replaces：Eq. 2 的 $`m(T)`$ → $`L(t)/L(t_d)`$ · 输入 PWR-07 🟡, CLM-01 ✅ · 参数 C-P1 (refit)

#### M-12 分区负荷权重 Zone load weights

**中文：** v0 按建筑占地面积分配设计负荷（A-P3）。M-12 加入楼层数和用途：$`u_c`$ 为用途类别 $`c`$ 的单位面积负荷强度（占位，可参考 EIA RECS / CBECS）。
**English:** v0 weights design load by footprint area (A-P3). M-12 adds floors and use class; $`u_c`$ is a load intensity per floor area by class (placeholder; EIA RECS / CBECS as guides).

```math
L^d_z\propto\sum_{b\in z}A_b\,n^{fl}_b\,u_{c(b)},\qquad
L^d_s=\sum_{z\in Z(s)}L^d_z\ \ (\text{serving}),\qquad L^d_s=\sum_{s'\in\mathrm{fed}(s)}L^d_{s'}\ \ (\text{upstream})
```

输入 BLD-01 ✅, BLD-02/03 🟡 · 输出 PWR-04 ⬜

#### M-13 线路载流量降额 Line ampacity derating

**中文：** 气温升高会降低架空线允许电流（Bartos 等 2016）。IEEE 738 稳态热平衡：对流散热 $`q_c`$ 加辐射散热 $`q_r`$ 等于太阳得热 $`q_s`$ 加焦耳热。线路参数未知时，用只保留对流项的近似式（标注为近似）。线路过载需要潮流 $`f_l`$，只有在 ACTIVSg70k（合成）或真实网络上做直流潮流时才能算。
**English:** Higher air temperature lowers conductor ampacity [bartos2016]. IEEE 738 steady-state heat balance [ieee738_2012]; with unknown line parameters, use the convection-only approximation (flagged as such). Overloads need flows from a DC power flow on ACTIVSg70k (synthetic) or the real network.

```math
q_c(T_c,\theta_A,V_w)+q_r(T_c,\theta_A)=q_s+I^2R(T_c)\;\Rightarrow\;
I_{\max}(\theta_A)=\sqrt{\frac{q_c+q_r-q_s}{R(T_{c,\max})}}
\approx I_{\mathrm{ref}}\sqrt{\frac{T_{c,\max}-\theta_A}{T_{c,\max}-\theta_{A,\mathrm{ref}}}}
```

```math
\boldsymbol\vartheta=B^{-1}\mathbf P,\qquad f_l=\frac{\vartheta_i-\vartheta_j}{x_l},\qquad
\text{line } l \text{ trips if } \frac{|f_l(t)|}{S_{\max,l}(\theta_A)}>1+\alpha_l
```

输入 CLM-01 ✅, CLM-04 ✅, CLM-08 🟡, PWR-10 🟡, PWR-22 🔒 · 参数 C-P7 (planned) · 关系 R-P5

#### M-14 绝缘老化 Insulation aging

**中文：** IEEE C57.91 的老化加速系数（参考热点 110 °C）。作为"应力"输出，也可作为另一种易损性自变量（累计老化而非瞬时温度）。
**English:** IEEE C57.91 aging acceleration factor (110 °C reference) [ieee_c5791_2011]; a stress output and an alternative fragility predictor.

```math
F_{AA}(t)=\exp\!\left(\frac{15000}{383}-\frac{15000}{\theta_H(t)+273}\right),\qquad
F_{EQA}=\frac{\sum_t F_{AA}(t)\Delta t}{\sum_t\Delta t},\qquad
\mathrm{LoL}=\sum_t F_{AA}(t)\,\Delta t
```

输入 PWR-13 ✅ · 输出 PWR-19

#### M-15 配电变压器 Distribution transformers

**中文：** 高温停电很多发生在配电层（小区的杆上/箱式变压器），v0 没有这一层。M-15 在每个分区生成 $`n_{dt,z}`$ 台合成配电变压器（每 $`c`$ 栋住宅一台，占位 $`c=8`$），按夜间最低温给出每日失效概率（夜间不降温时绝缘无法冷却），失效后该台所带用户停电 $`R_{dt}`$ 小时。这使分区状态从 0/1 变为部分停电比例 $`o_z(t)`$（G-1 连续版本）。
**English:** Many heat outages are at distribution level, which v0 lacks. M-15 generates synthetic distribution transformers per zone (one per $`c`$ residential buildings, placeholder $`c=8`$), with a daily failure probability driven by night-time minimum temperature; a failure cuts its customers for $`R_{dt}`$ hours. Zone state becomes a partial outage fraction $`o_z(t)`$.

```math
n_{dt,z}=\left\lceil N^{res}_z/c\right\rceil,\qquad
p_{dt,d}=\Phi\!\left(\frac{T^{night}_d-x^{dt}_{50}}{\sigma_{dt}}\right),\qquad
N^{fail}_{z,d}\sim\mathrm{Binomial}(n_{dt,z},p_{dt,d}),\qquad
o_z(t)=\max\!\Big(d_z(t),\;\frac{\text{customers on failed units}}{N^{cust}_z}\Big)
```

参数 C-P8 (planned，全部占位 / all placeholder) · 输入 BLD-01/02, CLM-14, PWR-21 🔒 · 关系 R-P6

#### M-16 修复与抢修资源 Restoration with crews and access

**中文：** v0 修复时长固定（Eq. 10）。M-16：修复时间服从对数正态分布（统计修复时间模型参见 Liu 等 2007）；抢修队数量有限，按优先级排队（先保障医院、水厂所在分区）；到达时间取决于路网行程时间（交通 → 电力的反向依赖，R-X1）。
**English:** v0 uses a fixed repair time. M-16 draws lognormal repair times (statistical restoration models: Liu et al. 2007 [liu2007]); crews are limited and work a priority queue (zones with hospitals and water plants first); arrival depends on network travel time (transport → power dependency, R-X1).

```math
R_j\sim\mathrm{LogNormal}(\mu_R,\sigma_R),\qquad
t^{start}_j=\max\big(t^{fail}_j,\;\min_c t^{free}_c\big)+\tau_{\mathrm{travel}}(\mathrm{depot}_c\to j;t),\qquad
t^{restore}_j=t^{start}_j+R_j
```

参数 C-P6 (refit), C-P10 (planned) · 输入 PWR-18, PWR-30, TRN-16

#### M-17 易损性拟合 Fragility fitting from observations

**中文：** 有失效记录后，用最大似然拟合易损性参数（Baker 2015）。对路段这类"长度不同"的对象，把长度当作暴露量：长路段即使单位长度风险相同，也更容易出现至少一次报修——这正是 v0 验证中长度混杂的来源（V5）。
**English:** Once failure records exist, fit fragility parameters by maximum likelihood [baker2015]. For segments of unequal length, treat length as exposure: a long segment is more likely to get at least one request at equal per-length risk, which is the confounding seen in V5.

```math
\ln\mathcal L(x_{50},\sigma)=\sum_j\Big[y_j\ln P_j+(1-y_j)\ln(1-P_j)\Big],\qquad
P_j=1-\big(1-p_j\big)^{\ell_j/\ell_0},\qquad p_j=\Phi\!\left(\frac{x_j-x_{50}}{\sigma}\right)
```

用于 Used for：C-P3（变电站，需 NES 记录）、C-T1（路面，用 311）· 关系 R-T7 tier 4

#### M-18 火电冷却水降额（水 → 电）Thermal generation derate (water → power)

**中文：** 直流冷却电厂在河水温度过高或流量过低时必须降出力（van Vliet 等 2012）。这是 cascading-heat 设计里的"冷却水不足使发电机跳闸"环节。电厂在研究区外，所以表现为系统供电缺口，按比例甩负荷到各分区。参数全部占位。
**English:** Once-through cooled plants must curtail when river temperature is high or flow is low [vanvliet2012]; this is the "cooling water shortage trips generators" link in the cascading-heat design. The plants are outside the AOI, so the effect is a system supply shortfall shed pro rata over zones. All parameters are placeholders.

```math
\Delta P_g(t)=P_g\cdot\min\!\Big(1,\max\Big(0,\frac{T_r(t)-T_{\lim}}{T_{\max}-T_{\lim}}\Big)\Big)\;\vee\;P_g\,\mathbf 1\big[Q_r(t)<Q_{\min}\big],\qquad
Sh(t)=\max\Big(0,\;L_{sys}(t)-\sum_g\big(P_g-\Delta P_g(t)\big)-P_{imp}\Big)
```

输入 PWR-09 🟡, WAT-13 🟡, WAT-14 🟡, PWR-07 🟡 · 参数 C-P9 (planned) · 关系 R-P0, R-W5

### 5.4 供水 Water (L4–L5)

#### M-19 用水需求 Water demand

**中文：** 用水量随高温上升（综述见 House-Peters & Chang 2011）。$`D_0`$ 为人均日用水 × 人口，$`\eta_h`$ 为日内曲线。所有参数占位，等 Metro Water 日供水量数据后拟合。
**English:** Demand rises with heat [housepeters2011]. $`D_0`$ = per-capita use × population; $`\eta_h`$ is the diurnal pattern. All placeholders until Metro Water production data allow a fit.

```math
D(t)=D_0\,\eta_{h(t)}\Big[1+\beta_w\max\big(0,T^{\max}_{d(t)}-T_{w0}\big)\Big],\qquad D_0=c_{pc}\cdot\mathrm{pop}
```

参数 C-W4 (planned) · 输入 WAT-07 ⬜, CLM-06 🟡, POP-06 ✅

#### M-20 储水质量平衡 Storage mass balance

**中文：** 推广 v0 的 Eq. 13：用真实的产能和需求做逐时质量平衡。v0 是它的特例（$`Q_{prod}\in\{D,0\}`$，储水以小时计）。
**English:** Generalises Eq. 13 to an hourly mass balance with production and demand; v0 is the special case $`Q_{prod}\in\{D,0\}`$ with storage in hours.

```math
S(t)=\min\Big(S_{\max},\;\max\big(0,\;S(t-1)+\big[Q_{prod}(t)-D(t)\big]\Delta t\big)\Big),\qquad
w^{out}(t)=\mathbf 1\big[S(t)\le S_{\min}\;\wedge\;Q_{prod}(t)<D(t)\big]
```

输入 WAT-02 ⬜, WAT-04 ⬜, WAT-07 ⬜ · 关系 R-W2 tier 2

#### M-21 产能与泵站 Production and pumping

**中文：** 产能是各水厂（泵站）按功能状态加总；功能状态按 G-2/G-3 由供电、备用电源和自身失效决定。
**English:** Production sums plant (pump) capacities weighted by functional state from G-2/G-3.

```math
Q_{prod}(t)=\sum_k Q_k\,x_k(t),\qquad x_k(t)=\neg F_k(t)\wedge\big(e_{z(k)}(t)\vee(B_k\wedge b_k(t)>0)\big)
```

输入 WAT-02, WAT-03, WAT-09, PWR-28 · 关系 R-W3, R-W4

#### M-22 压力驱动需求（水力层级）Pressure-driven demand (hydraulic tier)

**中文：** 有管网模型时，用 WNTR（Klise 等 2017）按 Wagner 等（1988）的压力驱动需求计算各节点实际供水量。服务指标为需求满足率 DSR。
**English:** With a network model, WNTR [klise2017] computes delivered demand with the Wagner et al. (1988) pressure-driven formulation [wagner1988]; the service metric is the demand satisfaction ratio.

```math
q_n=\begin{cases}
q^{req}_n & p_n\ge p_{req}\\[2pt]
q^{req}_n\sqrt{\dfrac{p_n-p_{\min}}{p_{req}-p_{\min}}} & p_{\min}<p_n<p_{req}\\[2pt]
0 & p_n\le p_{\min}
\end{cases},\qquad
DSR(t)=\frac{\sum_n q_n(t)}{\sum_n q^{req}_n(t)}
```

输入 WAT-06（真实 🔒 / 合成 🟡）, WAT-07 · 输出 WAT-12 · 关系 R-W1 tier 2s / 3

#### M-23 水管破裂（背景）Pipe breaks (context)

**中文：** 管道破裂率与温度变化有关（Wols & van Thienen 2014），但主要是低温和温差；高温通过土壤干缩间接作用。v0+ 只做背景统计，不进入级联。
**English:** Break rates depend on temperature change [wols2014], mainly cold and swings; heat acts through soil drying. Context only.

```math
\lambda(t)=\lambda_0\exp\big(c_T\,\Delta T(t)+c_{SM}\,\Delta SM(t)\big)\quad[\text{breaks km}^{-1}\text{day}^{-1}]
```

输入 CLM-06, CLM-25, WAT-17/19 · 不传播 not propagated

#### M-24 余氯衰减（背景）Chlorine decay (context)

**中文：** 水温升高加快余氯衰减（一级动力学，温度修正系数 $`\theta_{Cl}`$ 占位）。只作水质背景指标。
**English:** Warmer water decays chlorine faster (first-order kinetics with a placeholder temperature factor). Water-quality context only.

```math
C(t_{age})=C_0\,e^{-k(T)\,t_{age}},\qquad k(T)=k_{20}\,\theta_{Cl}^{\,T-20}
```

输入 WAT-14, WAT-18 🔒 · 不传播 not propagated

### 5.5 交通 Transportation (L4–L6)

#### M-25 路面病害（推广 Eq. 15）Pavement distress (generalising Eq. 15)

**中文：** Eq. 15 的易损性不变，但自变量从 LST 的 T7 改为 M-10 的路面温度，并在验证与校准中按 M-17 把路段长度当作暴露量。
**English:** Same fragility as Eq. 15, but the predictor becomes the M-10 pavement temperature, and validation / calibration treat length as exposure (M-17).

```math
p_i=\Phi\!\left(\frac{T_{pav,i}-x_{50}(PG_i)}{\sigma_T}\right),\qquad
P(\text{request on } i)=1-(1-p_i)^{\ell_i/\ell_0}
```

输入 LST-10, TRN-03 ⬜, TRN-02 ✅, TRN-22 ✅ · 参数 C-T1, C-T1.sigma

#### M-26 铁轨屈曲 Rail buckling

**中文：** 轨温 ≈ 气温 + 太阳辐射造成的温升；轨温超过中和温度（RNT）一定幅度时屈曲风险上升（英国案例：Dobney 等 2009）。所有参数占位。
**English:** Rail temperature ≈ air temperature plus a solar term; buckling risk rises once rail temperature exceeds the rail neutral temperature by a margin (UK case: Dobney et al. 2009 [dobney2009]). All parameters are placeholders.

```math
T_{rail}(t)=\theta_A(x,t)+c_r\,GHI(t),\qquad
p^{buckle}_r(t)=\Phi\!\left(\frac{T_{rail}(t)-RNT_r-\Delta T_{crit}}{\sigma_r}\right)
```

参数 C-T7 (planned)，$`c_r`$ 占位约 0.02 K/(W·m⁻²) / placeholder · 输入 TRN-17 🟡, CLM-08 🟡, CLM-19 · 关系 R-T5

#### M-27 信号灯电池时长 Signal battery duration

**中文：** v0 用"有没有电池"的伯努利抽样（Eq. 11）。M-27 改为电池时长：分区停电时长超过电池续航后信号灯熄灭。没有电池的信号灯 $`h_{b,g}=0`$。
**English:** v0 draws battery presence only. M-27 uses battery duration: a signal goes dark once the zone outage outlasts its battery; signals without one have $`h_{b,g}=0`$.

```math
\mathrm{dark}_g(t)=d_{z(g)}(t)\wedge\big(\tau^{out}_{z(g)}(t)>h_{b,g}\big),\qquad
h_{b,g}=\begin{cases}0 & \text{with prob. } p^{nb}\\ \sim\mathrm{Tri}(h^{low},h^{mid},h^{high}) & \text{otherwise}\end{cases}
```

参数 C-T2, C-T2.h (planned) · 输入 PWR-28 ✅ · 关系 R-T3 tier 2

#### M-28 路段行程时间（BPR）Link travel time (BPR)

**中文：** 用 BPR 函数（Bureau of Public Roads 1964）计算拥堵下的行程时间。流量 = AADT × TMAS 小时系数；通行能力乘以折减系数：信号灯熄灭按全向停车处理（占位 $`\varphi_{dark}`$，参考 HCM），路面病害可加限速折减。
**English:** BPR volume–delay [bpr1964]. Volume = AADT × TMAS hourly factor; capacity is reduced when a signal is dark (all-way stop placeholder, cf. HCM [hcm2022]) and optionally for pavement distress.

```math
t_i(t)=t^0_i\left[1+a\left(\frac{v_i(t)}{\varphi_i(t)\,c_i}\right)^{b}\right],\qquad
v_i(t)=AADT_i\,\eta_{class(i)}\big(h(t)\big),\qquad
\varphi_i(t)=\varphi_{dark}^{\,\mathbf 1[\deg_i(t)]}
```

参数 $`a=0.15, b=4`$ (C-T6 planned), $`\varphi_{dark}`$ (C-T5 planned) · 输入 TRN-10/11/12 🟡, TRN-13, TRN-08

#### M-29 可达性与急救响应 Access and EMS response

**中文：** 在 M-28 的时变路网上做最短路（Dijkstra）。设施可达性：从分区中心到最近"仍在运行"的同类设施的时间；急救响应：从最近急救站到分区中心的时间。超过阈值 $`\tau_{\max}`$ 视为失去可达性（G-2 中的 access 需求）。
**English:** Shortest paths (Dijkstra) on the M-28 time-dependent network: time from a zone centroid to the nearest *functional* facility of a type, and EMS response time from the nearest station. Beyond $`\tau_{\max}`$ the access requirement fails.

```math
\tau_f(z,t)=\min_{f\in\mathcal F_{type},\;x_f(t)=1}SP_t(z,f),\qquad
\tau_{EMS}(z,t)=\min_{e\in\mathcal E}SP_t(e,z),\qquad
A_f(t)=\mathbf 1\big[\tau\le\tau_{\max}\big]
```

输入 TRN-01, TRN-21 🟡, HLT-20 · 输出 TRN-16 · 关系 R-T4 tier 2, R-H3

#### M-30 公交站等车暴露 Transit-stop waiting exposure

**中文：** 等车者在室外暴露，按上车人数 × 平均等待（半个发车间隔）× 高 WBGT 指示计算人分钟。上车数据受限时按站点均分（占位）。
**English:** Riders wait outdoors; exposure = boardings × half headway × high-WBGT indicator, in person-minutes. Without APC data, boardings are spread evenly (placeholder).

```math
E_{st}=\sum_{s}\sum_t B_s(t)\,\frac{H_s(t)}{2}\,\mathbf 1\big[WBGT(x_s,t)\ge W_{thr}\big]
```

输入 TRN-19 🟡, TRN-20 🔒, CLM-13 · 关系 R-T6

### 5.6 健康 Health (L5–L6)

#### M-31 医疗设施功能组合 Facility functional composition

**中文：** 医院、养老院、透析中心按 G-2/G-3 组合"供电（含备用燃料）、供水（含自备储水）、可达性"。燃料缓冲在路网可达时可补给（燃料车需要道路），这是交通 → 健康的依赖。
**English:** Facilities combine power (with fuel buffer), water (with on-site storage) and access by G-2/G-3. Fuel can be resupplied only when the facility is reachable, a transport → health dependency.

```math
x_f(t)=\neg F_f(t)\wedge\underbrace{\big[e_f(t)\vee(B_f\wedge b^{fuel}_f(t)>0)\big]}_{\text{power}}
\wedge\underbrace{\big[\neg w^{out}(t)\vee s_f(t)>0\big]}_{\text{water}}
\wedge\underbrace{A_f(t)}_{\text{access}},\qquad y_f(t)=\neg x_f(t)
```

参数 C-H1, C-H2, C-H3, C-H6 (planned), C-H7 (planned) · 关系 R-H1 tier 2

#### M-32 停电期间室内温度 Indoor temperature during outages

**中文：** 一阶 RC 模型：有电且有空调时室内保持设定温度 $`T_{set}`$；停电或无空调时，室内温度以热时间常数 $`\tau_b`$ 趋向"室外气温 + 得热温升"。$`\tau_b`$ 按建筑类型给占位值（养老院热韧性案例：Sun 等 2020）。这是"停电 → 健康"的核心环节（Stone 等 2023 用建筑能耗模型得到热浪停电使高温死亡翻倍）。
**English:** First-order RC model: with power and AC the home stays at $`T_{set}`$; otherwise indoor temperature relaxes towards outdoor temperature plus a gain lift with time constant $`\tau_b`$ (placeholder by building class; nursing-home case: Sun et al. 2020 [sun2020]). This is the core outage → health link (Stone et al. 2023 used building energy models [stone2023]).

```math
T^{eq}(t)=\theta_A(x,t)+\Delta T_{gain}(t),\qquad
T_{in}(t)=\begin{cases}
T_{set} & \text{powered} \wedge \text{AC}\\
T^{eq}(t)+\big[T_{in}(t-1)-T^{eq}(t)\big]e^{-\Delta t/\tau_b} & \text{otherwise}
\end{cases}
```

参数 C-B1 $`\tau_b`$、C-B2 $`\Delta T_{gain}`$ (planned) · 输入 PWR-28, CLM-19, BLD-03/04 · 输出 HLT-22

#### M-33 室内高温暴露 Indoor heat exposure

**中文：** 分两类住户：有空调（比例 $`f_{AC}`$）只有停电时才"自由升温"；无空调住户始终自由升温。按人群 $`g`$（65+、独居老人、5 岁以下、依赖电力设备者）计算超过室内阈值的人时。
**English:** Two household types: with AC (share $`f_{AC}`$) free-run only during outages; without AC always free-run. Person-hours above the indoor threshold by group $`g`$.

```math
E^{in}_g=\sum_t\sum_z\mathrm{pop}_{z,g}\Big[f_{AC}\,\mathbf 1\big[T^{AC,out}_{in,z}(t)\ge T_{thr,g}\big]\,d_z(t)+(1-f_{AC})\,\mathbf 1\big[T^{noAC}_{in,z}(t)\ge T_{thr,g}\big]\Big]
```

参数 C-H10 (planned) · 输入 POP-02/08/17, HLT-17, BLD-04 · 关系 R-H5 tier 1

#### M-34 高温与停电的健康结局 Health outcomes of heat and outages

**中文：** 用分布滞后非线性模型（DLNM，Gasparrini 等 2010）的温度–死亡关系，加上停电修正，计算归因死亡数。占位时用简化的对数线性形式（滞后 0–3 天累计）。停电修正提供两种互斥的方案，避免重复计算：
- 方案 A（Anderson & Bell 2012）：停电人口比例 $`o_d`$ 的人群相对风险乘以 $`RR_{out}`$；
- 方案 B（Stone 等 2023）：停电人群的高温超额风险乘以放大系数 $`A_{HW}`$。

**English:** Temperature–mortality from a DLNM [gasparrini2010] with an outage modifier gives attributable deaths; the placeholder is a log-linear form over lags 0–3. Two mutually exclusive outage modifiers avoid double counting:
- variant A [anderson2012]: multiply by $`RR_{out}`$ for the outage share;
- variant B [stone2023]: amplify the heat excess risk of the outage share by $`A_{HW}`$.

```math
\ln RR_T(d)=\sum_{l=0}^{L}\sum_j \eta_j(T_{d-l})\,\omega_j(l)\quad\Big(\text{placeholder: }\ \beta_h\sum_{l=0}^{3}\max(0,T_{d-l}-MMT)/4\Big)
```

```math
\text{A: } RR_d=RR_T(d)\cdot RR_{out}^{\,o_d},\qquad
\text{B: } RR_d=1+\big(RR_T(d)-1\big)\big[1+(A_{HW}-1)\,o_d\big],\qquad
AN_d=B_d\Big(1-\frac{1}{RR_d}\Big)
```

$`o_d`$ = 当日停电人时 / (24 × 人口) / outage person-hours ÷ (24 × population)。参数 C-H4, C-H5, C-H8 (planned) · 输入 HLT-13 🟡, HLT-14 ⬜, CLM-06 🟡, POP-14 ✅ · 关系 R-H5 tier 2

#### M-35 透析转诊 Dialysis relocation

**中文：** 透析患者每周 3 次、每次约 4 小时，停诊即有风险（Kelman 等 2015）。每日需求 $`D_f=P_f\cdot 3/6`$（每周 3 次，6 个营业日）。设施停摆时，患者在可达时间 $`\tau_{\max}`$ 内按最近优先转到仍运行且有空位的设施；未能转出的为当日漏诊。
**English:** Dialysis patients need about three sessions a week; missed sessions are dangerous [kelman2015]. Daily demand $`D_f=P_f\cdot3/6`$. When a facility is down, patients move greedily (nearest first) to functional facilities with spare capacity within $`\tau_{\max}`$; the rest are missed sessions.

```math
C^{spare}_g(d)=st_g\cdot n_{shift}-D_g,\qquad
\mathrm{reassigned}_d=\sum_{f:\,y_f(d)=1}\ \sum_{g:\,x_g(d)=1,\ \tau(f,g)\le\tau_{\max}}a_{fg},\qquad
M_d=\sum_{f:\,y_f(d)=1}D_f-\mathrm{reassigned}_d
```

其中 $`a_{fg}`$ 为从 $`f`$ 转到 $`g`$ 的人数，受 $`\sum_f a_{fg}\le C^{spare}_g`$ 约束。$`a_{fg}`$ = patients moved from $`f`$ to $`g`$, with $`\sum_f a_{fg}\le C^{spare}_g`$. 输入 HLT-05/06, TRN-16 · 关系 R-H2

#### M-36 依赖电力医疗设备的居民 Electricity-dependent residents

**中文：** HHS emPOWER 给出各 ZIP 依赖电力医疗设备（呼吸机、制氧机等）的 Medicare 受益人数（该人群特征见 Molinari 等 2017）。按 M-39 的权重分到分区；停电时长超过设备电池续航即处于高风险。
**English:** HHS emPOWER gives ZIP counts of electricity-dependent Medicare beneficiaries [empower; molinari2017]; allocate to zones with M-39 weights; at risk once the outage outlasts the device battery.

```math
N^{risk}(t)=\sum_z n^{ED}_z\,d_z(t)\,\mathbf 1\big[\tau^{out}_z(t)>h_{dev}\big],\qquad
n^{ED}_z=\sum_{c\in\mathrm{ZIP}}n^{ED}_c\,\omega_{c\to z}
```

参数 C-H9 (planned) · 输入 HLT-17 🟡 · 关系 R-H6

#### M-37 医院急诊负荷（占位）Hospital ED surge (placeholder)

**中文：** 高温使急诊就诊上升，同时医院在备用电源运行时会压缩非必要服务。比值 $`\rho_f(t)>1`$ 表示超负荷。优先级低，等 ESSENCE 数据后再定参数。
**English:** Heat raises ED demand while hospitals on backup cut non-essential services; $`\rho_f>1`$ means overload. Low priority until ESSENCE data exist.

```math
\lambda^{ED}_f(t)=\lambda^{ED}_{0,f}\,RR_{ED}\big(\theta_A(t)\big),\qquad
\kappa_f(t)=\kappa_f\big(1-\rho_{bk}\,\mathbf 1[\text{on backup}]\big),\qquad
\rho_f(t)=\lambda^{ED}_f(t)/\kappa_f(t)
```

输入 HLT-02 🟡, HLT-12 🔒

#### M-38 避暑中心覆盖 Cooling-centre coverage

**中文：** 脆弱人群中，有多少人在可达时间内能到达"有电、开放"的避暑中心。无车住户用步行时间。
**English:** Share of vulnerable residents who can reach a powered, open cooling centre in time; households without a car use walking time.

```math
Cov(t)=\frac{\sum_z v_z\,\mathbf 1\big[\exists\,cc: x_{cc}(t)=1\wedge\tau(z,cc,t)\le\tau_{cc}\big]}{\sum_z v_z}
```

输入 HLT-10 🟡, POP-08/09, TRN-16 · 关系 R-H4

### 5.7 人口与脆弱性 Population and vulnerability (L6)

#### M-39 分区密度制图 Dasymetric allocation

**中文：** v0 按面积加权分配 ZCTA 人口。M-39 改为按住宅建筑面积分配（Mennis 2003）：人只住在住宅里。若某普查单元内没有住宅建筑，退回面积加权。
**English:** Replace areal weighting with residential floor area [mennis2003]; fall back to areal weighting where a census unit has no residential buildings.

```math
\mathrm{pop}_z=\sum_c\mathrm{pop}_c\,\frac{\sum_{b\in c\cap z}A_b\,n^{fl}_b\,\mathbf 1[\mathrm{res}_b]}{\sum_{b\in c}A_b\,n^{fl}_b\,\mathbf 1[\mathrm{res}_b]}
```

输入 POP-01/07, BLD-01/02/03 · 输出 POP-06 · 关系 R-POP1 tier 2

#### M-40 脆弱性指数 Vulnerability index

**中文：** 直接用 CDC SVI（Flanagan 等 2011），或者按同样的百分位方法自建高温脆弱性指数（老年、独居、贫困、无车、残障、慢性病、无空调）。用作结果的加权。
**English:** Use CDC SVI [flanagan2011] directly, or build a heat-specific index with the same percentile-rank method; used to weight outputs.

```math
HVI_z=\frac1K\sum_{k=1}^{K}\mathrm{PR}_k\big(x_{k,z}\big),\qquad
E^{w}=\sum_z HVI_z\,E_z
```

输入 POP-05, POP-08..12, HLT-21, BLD-04

#### M-41 分人群复合暴露 Compound exposure by group

**中文：** 推广 Eq. 14：阈值可以用热指数，人群可以是任一脆弱组，停电可以是部分比例 $`o_z`$（M-15）。
**English:** Generalises Eq. 14 to the heat index, any group and partial outages.

```math
E^c_g=\sum_t\sum_z\mathrm{pop}_{z,g}\,o_z(t)\,\mathbf 1\big[HI(x_z,t)\ge HI_{thr}\big]
```

### 5.8 不确定性、敏感性与校准 Uncertainty, sensitivity and calibration (L7)

#### M-42 Sobol 总效应指数 Sobol total-effect index

**中文：** v0 用 Spearman 秩相关排序敏感性。M-42 用 Saltelli 等（2010）的方差分解总效应指数（Jansen 估计量），可以捕捉非线性和交互（例如易损性中位数与设计负荷的交互）。代价 $`N(K+2)`$ 次运行。
**English:** Replace the Spearman ranking with variance-based total-effect indices [saltelli2010] (Jansen estimator), which capture non-linearity and interactions; cost $`N(K+2)`$ runs.

```math
S_{T,k}=\frac{\mathbb E_{\mathbf X_{\sim k}}\big[\mathrm{Var}_{X_k}(Y\mid\mathbf X_{\sim k})\big]}{\mathrm{Var}(Y)}
\approx\frac{\frac{1}{2N}\sum_{j=1}^{N}\big[f(A)_j-f(A_B^{(k)})_j\big]^2}{\mathrm{Var}(Y)}
```

#### M-43 用观测校准参数 Calibration against observations

**中文：** Kennedy & O'Hagan（2001）框架：观测 = 模型 + 模型偏差 + 观测误差。实用的第一步：利用已经从先验（三角分布）抽样的蒙特卡洛运行，按非风暴小时 EAGLE-I 的似然给每次运行加权，得到后验，不需要额外模拟（自归一化重要性抽样）。有效样本量 ESS 太小时，改用逼近贝叶斯计算（ABC）或增加运行次数。
**English:** Kennedy & O'Hagan (2001) framework [kennedy2001]: observation = model + discrepancy + noise. Practical first step: re-weight the existing prior Monte Carlo runs by their likelihood on non-storm EAGLE-I hours to get a posterior without new simulations (self-normalised importance sampling); if the effective sample size is small, use ABC or more runs.

```math
y_t\sim\mathrm{NegBin}\big(\mu_t(\theta)=b_0+\kappa\,\hat Y_t(\theta),\;r\big),\quad t:\ s(t)=0,\qquad
w_r\propto\prod_t p\big(y_t\mid\theta^{(r)}\big),\qquad
ESS=\frac{(\sum_r w_r)^2}{\sum_r w_r^2}
```

用于 Used for：C-P1.Kd, C-P3, C-P3.sigma, C-P6；以后 ED 数据可用于 C-H8 / C-H5 · 观测 PWR-26 ✅, PWR-25 🔒, HLT-12 🔒 · 掩膜 CLM-17

#### M-44 跨系统放大矩阵 Cross-system amplification matrix

**中文：** 每次失效记录它的直接原因（上游节点和规则编号）。由此统计系统 $`a`$ 的失效通过依赖链引发系统 $`b`$ 失效的次数，得到放大矩阵；对角线外的元素就是"级联"本身。
**English:** Every failure records its direct cause (upstream node and rule id). Count failures in system $`b`$ whose causal chain contains a failure in system $`a`$; off-diagonal entries are the cascade itself.

```math
M_{ab}=\mathbb E_r\Big[\#\{\text{failures in } b \text{ with an ancestor in } a\}\Big],\qquad
A_{tot}=\frac{\sum_{i,t}\mathbf 1[x_i(t)=0]}{\sum_{i,t}\mathbf 1[F_i(t)=1]}
```

---

## 6. 关系分级 Relation tier ladder

**中文：** 每条关系在 [`twin/relations.csv`](../twin/relations.csv) 里有多行，每行是一个等级的方法，`current = yes` 表示现在使用的那一行。等级定义如下；带 `s` 后缀的是"合成数据"等级，只能做敏感性分析，不能当真实结果。

**English:** Each relation has one row per tier in `twin/relations.csv`; `current = yes` marks the tier in use. Tiers with an `s` suffix use synthetic data and are for sensitivity analysis only.

| 等级 Tier | 中文 | English | quality_rank |
| --- | --- | --- | --- |
| 0 | 纯假设或未建模 | assumption or not modelled | 4 |
| 1 | 由开放地理数据推断（邻近、拓扑、Voronoi） | inferred from open geodata (proximity, topology, Voronoi) | 3 |
| 1s / 2s | 合成网络（ACTIVSg70k、DiTEC / SyNF 管网） | synthetic networks | 4 |
| 2 | 由公开统计或经验关系拟合 | fitted to public statistics or empirical relations | 3 |
| 3 | 运营方 / 资产方真实数据（NES、TVA、Metro Water、TDOT） | operator / asset-owner data | 2 |
| 4 | 在 3 或 2 级基础上用观测校准（M-17、M-43） | calibrated against observations | 不变 unchanged；`calibrated = yes` |

**v0 现状 / v0 status**（详见自动生成的 [`DATA_CATALOG.md`](DATA_CATALOG.md)）

| 关系 Relation | 内容 Content | 当前等级 Current | 下一步 Next tier | 需要的数据 Data needed |
| --- | --- | --- | --- | --- |
| R-P0 | 外部电网 / 火电 external grid | 0 | 2 (M-18) | EIA-860 🟡、USGS 🟡、TDEC 🟡、EIA-930 🟡 |
| R-P1 | 变电站拓扑 substation topology | 1 | 3 | TVA / NES 单线图 🔒 |
| R-P1b, R-P2 | 配电供电 / 最近站 | 1 / 0 | 3 | NES 馈线 🔒 |
| R-P3 | 供电分区 service zones | 0 | 1 → 2 | 负荷权重 / NES 停电快照 🔒 |
| R-P4 | 分区 → 资产 zone → asset | 0 | 3 | NES 用户–馈线 🔒 |
| R-P5 | 气温 → 线路容量 | 0 | 2 (M-13) | ACTIVSg70k 🟡、辐射 🟡 |
| R-P6 | 配电变压器 | 0 | 1 (M-15) | 建筑用途 🟡 |
| R-W1, R-W2 | 产水 / 储水 → 设施 | 0 | 1 → 2 | 水厂产能 ⬜、储量 ⬜、需求 ⬜ |
| R-W3, R-W4 | 电 → 水厂 / 泵站 | 0 | 1 → 3 | OSM 泵站 🟡、Metro Water 🔒 |
| R-W5 | 河水 → 火电（水 → 电） | 0 | 2 (M-18) | USGS 🟡、TDEC 🟡 |
| R-T1, R-T2 | 信号灯 / 桥梁 → 路段 | 1 | 3 | Metro 信号灯台账 🔒 |
| R-T3 | 电 → 信号灯 | 0 | 2 (M-27) | 电池时长 ⬜ |
| R-T4 | 路网 → 可达 | 1 (不传播) | 2 (M-28, M-29) | HPMS 🟡、TMAS 🟡 |
| R-T5, R-T6 | 铁路 / 公交站 | 0 | 1 | NTAD 🟡 |
| R-T7 | 高温 → 路面 | 1 | 2 (M-10) → 4 (M-17) | GHCN-D 🟡、311 ✅ |
| R-H1 | 设施功能组合 | 0 | 2 (M-31) | 燃料、储水 ⬜、可达 |
| R-H2…R-H6 | 透析转诊、急救、避暑中心、室内高温、依赖电力者 | 0 | 1 → 2 | CMS 🟡、emPOWER 🟡、WONDER 🟡 |
| R-POP1 | 分区 → 人口 | 1 | 2 (M-39) | 建筑用途 🟡、街区组 🟡 |
| R-X1 | 路网 → 抢修 | 0 | 2 (M-16) | 修复记录 🔒、抢修队 ⬜ |

---

## 7. 新数据接入规范 Data onboarding protocol

**中文：** 任何新数据都按下面 7 步接入。核心思想：**数据进来先对上变量编号，再决定它替换哪个占位、让哪条关系升级**。

**English:** Every new dataset follows seven steps. Core idea: **map the data to variable ids first, then decide which placeholder it replaces and which relation it upgrades.**

### 7.1 步骤 Steps

| 步 Step | 中文 | English | 改哪里 Where |
| --- | --- | --- | --- |
| 1 登记来源 Register | 在 `datasets.yaml` 加一条：`id`、`kind`、`provider`、`license`、`retrieved_date`、`temporal_res`、`spatial_res`、`quality_rank`。原文件放 `raw/`，大文件只在 Drive。 | Add an entry with provenance; raw file in `raw/`. | `datasets.yaml` |
| 2 对上变量 Map | 找到它提供的变量编号；没有对应编号就先在 `variables.csv` 新增一行（必须能追溯到 §3 的某个结果）。把 `status` 改为 `ingested`，`source_dataset` 填数据集 id。 | Map to var ids; add a row if needed (must trace to an output in §3). Set status and source. | `twin/variables.csv` |
| 3 标准化 Standardise | 选现有 adapter 或新写一个；输出必须满足 §7.2 的规则，并通过 `schema.validate`。 | Use or write an adapter; output must pass §7.2 and `schema.validate`. | `pipeline/adapters/` |
| 4 质控 QA | `python -m pipeline.registry` 检查值域（`valid_min/valid_max`）、单位、覆盖时段；`python -m pipeline.build --strict` 检查结构。 | Range, unit and coverage checks; strict build. | 命令 commands |
| 5 替换占位 Replace | 把相关参数行的 `basis/citation/evidence` 改为新来源，`placeholder` 改为 `no`；在 `relations.csv` 把新等级设为 `current = yes`，旧等级改为 `no`（保留，不删除）。 | Update coupling rows; flip `current` in relations.csv (keep the old tier). | `couplings.csv`、`relations.csv` |
| 6 重跑对比 Re-run | 用**同一随机种子**重跑 `pipeline.cascade`，对比新旧 run_id 的 KPI 与敏感性排名，写进 `RESULTS.md` 的变更说明。 | Re-run with the same seed and compare KPIs and sensitivity against the previous run_id. | `pipeline.cascade`、`pipeline.report` |
| 7 更新文档 Document | 更新 HANDBOOK 的占位清单（§3.4）和本规范的状态标记；`DATA_CATALOG.md` 自动重生成。 | Update the placeholder register; regenerate the catalogue. | `docs/` |

### 7.2 标准化规则 Standardisation rules

| 项目 Item | 规则 Rule（中文） | Rule (English) |
| --- | --- | --- |
| 坐标 CRS | 存储一律 EPSG:32616；只有网页导出转 4326 / 3857。Metro 建筑轮廓原为 EPSG:2274（美制英尺），入库时转换。 | Store in EPSG:32616; reproject only for the web. Convert Metro footprints from EPSG:2274. |
| 时间 Time | 存储一律 UTC；"日"按当地时间 America/Chicago 切分（热浪、日最高温、透析日）。时段数据写 `timestamp` + `time_end`。 | Store UTC; daily aggregates use local days. Intervals use `timestamp` + `time_end`. |
| 单位 Units | 用 `variables.csv` 的 `units`。温度用 °C；唯一例外是 C-P1 的负荷斜率（每 °F），因为它是按 °F 拟合的。转换在 adapter 里做。 | Use the registry units; °C except the C-P1 slope (per °F, as fitted). Convert inside adapters. |
| 编号 Ids | `asset_id` 保持 v0 的"数据集前缀 + 原始编号"格式，保证可追溯且不冲突。 | Keep the v0 source-prefixed asset ids. |
| 缺测 Missing | 缺测写 NaN，**绝不写 0**；"没有记录"与"值为 0"含义不同时要在 adapter 里写明（如 A-D2：EAGLE-I 无记录视为 0 户停电）。 | Missing = NaN, never 0; document when absence means zero (A-D2). |
| 时间聚合 Aggregation | 气温取平均，降水取和，停电户数取小时最大值，事件取计数；规则写在变量备注里。 | Mean for temperature, sum for precipitation, hourly max for customers out, counts for events. |
| 空间支撑 Support | 必须声明 `spatial_res`。点位数据匹配到资产要写明距离阈值（如 311 匹配 ≤ 30 m）。 | Declare spatial support; point-to-asset matching states its distance threshold. |
| 质量标记 Flags | 逐时数据带 `quality_flag`：`ok` / `partial` / `suspect` / `filled`（M-9 填补）。模型默认排除 `suspect`。 | Hourly data carry ok / partial / suspect / filled; models exclude suspect by default. |
| 隐私 Privacy | 个人或地址级数据（311、急救、急诊）只发布网格或区域汇总。 | Person- or address-level data are published as aggregates only. |

### 7.3 多源冲突 Conflicting sources

**中文：** 同一变量有多个来源时，按下列顺序选一个作为模型输入，其他来源保留为验证用（在 `datasets.yaml` 加 `role: validation`），**不做静默混合**：
1. 关系等级高者；
2. `quality_rank` 小者；
3. 空间分辨率细者；
4. 时间覆盖与模拟期重合多者；
5. 较新者。

**English:** When several sources give one variable, choose one for the model in this order and keep the rest for validation (`role: validation`); never blend them silently:
1. higher tier;
2. lower `quality_rank`;
3. finer resolution;
4. more overlap with the simulation period;
5. more recent.

### 7.4 新变量登记模板 New-variable template

```csv
var_id,system,entity,kind,symbol,name_en,name_zh,units,spatial_res,temporal_res,std_table,std_field,status,source_dataset,fallback,target_source,used_in,coupling_id,valid_min,valid_max,priority,note_en,note_zh
PWR-32,power,substation,attribute,L^peak_s,Observed substation peak load,变电站实测峰值负荷,MW,station,annual,assets,attributes.peak_mw,ingested,nes_peaks_2025,-,NES SCADA,Eq.3;M-12,,0,500,1,"Replaces PWR-04 placeholder.","替换 PWR-04 占位。"
```

---

## 8. 数据获取优先级 Data acquisition priorities

**中文：** 按"解锁多少结果 ÷ 获取成本"排序。第一组数据已经在 Drive 上，不花钱、不需要审批，建议先做。

**English:** Ranked by outputs unlocked per unit of effort. Group A is already on Drive and needs no approval.

### A. 已在 Drive，只需接入 / On Drive, only needs connecting

| 变量 Var | 数据 Data | 位置 Location | 解锁 Unlocks |
| --- | --- | --- | --- |
| CLM-06/07 | NOAA GHCN-D 日值、GSOM 月值 | `cascading-heat_data/01_temperature/`（日值已在 `raw/`） | M-5 热浪定义、M-10 路面温度、O5 |
| CLM-20/21 | 2022 走航测温（早 / 午 / 晚） | `01_temperature/traverse_2022/` | M-6 城市气温场 → O1、O2 |
| PWR-26 | EAGLE-I 2014–2025 | `02_power/power_outage/` | M-43 多年校准 |
| PWR-09 | EIA-860 2022 | `02_power/eia8602022.zip` | M-18 |
| PWR-10 | ACTIVSg70k（合成） | `02_power/case_ACTIVSg70k.m` | R-P1 1s、M-13 |
| WAT-13/14/15 | USGS 03431500 流量；TDEC 水温、溶解氧 | `03_water/` | M-18（水 → 电） |
| WAT-06 | DiTEC 合成管网 | `03_water/ditec_large.inp` | R-W1 2s、M-22 |
| TRN-10/12 | HPMS 2024 Davidson（AADT、车道） | `twin_demo/l1_std/ntad/hpms_2024_davidson.parquet` | M-28 |
| TRN-11 | TMAS 逐小时计数 | `twin_demo/l2/state_tmas_hourly.parquet` | M-28 时变曲线 |
| TRN-17/19/23 | NTAD 铁路、公交站点 / 线路、充电站 | `twin_demo/l1_std/ntad/` | M-26、M-30 |
| TRN-09 | NBI 桥梁 | `twin_demo/l1_std/ntad/national_bridge_inventory__0.parquet` | R-T2 补充 |
| POP-09 | 住户车辆拥有 | `twin_demo/l1_std/ntad/household_size_by_vehicles_available__0.parquet` | M-38、M-40 |
| PWR-31, WAT-19 | 311 道路 / 电力 / 供水 2017–2025 | `05_311_requests/` | 多年验证（注意 2024-11 后电力类停收） |

### B. 公开可下载 / Public downloads

| 变量 Var | 数据 Data | 解锁 Unlocks |
| --- | --- | --- |
| PWR-07 | EIA-930 TVA 逐时负荷 | M-11，替换假设 A-P4（**收益最大** / biggest gain） |
| HLT-17 | HHS emPOWER（ZIP） | M-36、O2 |
| CLM-18 | NOAA Storm Events | M-8 更准的风暴掩膜 → 校准 |
| CLM-08..11, CLM-22 | ASOS 辐射代用（云量）、降水、气压；JWN、MQY 站 | M-3、M-6 |
| BLD-02/03 | Metro Nashville 地块（用途、建造年份、楼层） | M-12、M-32、M-39 |
| BLD-05/06 | NLCD 不透水面、树冠 | M-6 |
| POP-07..12, POP-17 | ACS 街区组 / 普查区；CDC SVI | M-39、M-40 |
| HLT-13 | CDC WONDER 县级死亡 | M-34 |
| HLT-06 | CMS 透析设施报告（患者数） | M-35 |
| HLT-10, TRN-21 | 避暑中心名单；消防 / 急救站 | M-29、M-38 |
| CLM-24 | LOCA2 | M-7 情景 |
| LST-11/12 | GOES-16 ABI、ECOSTRESS | M-9 |

### C. 需要合作 / Needs a partner

| 合作方 Partner | 变量 Vars | 解锁 Unlocks |
| --- | --- | --- |
| NES | PWR-03, 04, 20, 21, 24, 25, 30；修复记录 | 变压器额定、负荷、分区、配电层、校准 —— 解决敏感性前三的占位 |
| Metro Water Services | WAT-02..07, 16..18 | 产能、储量、压力分区、管网（R-W1 → 3 级） |
| Tennessee Dept. of Health | HLT-12 | 健康结局校准（R-H5 → 4 级） |
| Nashville Fire Dept. | HLT-11 | 急救验证 |
| TDOT / Metro Public Works | TRN-03, 04；信号灯台账 | PG 等级、路面状况、信号灯电池 |
| WeGo | TRN-20 | 公交站暴露 |

### D. 团队内部可生产 / Producible in-house

| 变量 Var | 内容 | 负责 |
| --- | --- | --- |
| LST-08 | 用 LST v4.1 重跑 2023-07-27–29、08-21–26 逐小时 LST | LST pipeline（Gio） |
| CLM-20 | 确认 2022 走航日期 | 走航数据来源方 |

---

## 9. 文件与命令 Files and commands

```bash
# 【中文】检查登记表一致性并生成 docs/DATA_CATALOG.md / check the registry and write the catalogue
.venv/bin/python -m pipeline.registry

# 【中文】同时检查标准表里的数值是否在值域内 / also range-check values in the standard tables
.venv/bin/python -m pipeline.registry --check-data

# 【中文】其余流程同 HANDBOOK §9 / the rest as in HANDBOOK §9
.venv/bin/python -m pipeline.build --strict
.venv/bin/python -m pipeline.cascade --runs 2000 --mid-runs 500 --scenarios 0,2,4
.venv/bin/python -m pipeline.report
```

**`pipeline.registry` 检查内容 / What the registry checks:**
- 变量编号唯一、状态和类型在词表内；
- `in_model` / `ingested` 变量的 `source_dataset` 在 `datasets.yaml` 中存在；
- 引用的参数编号在 `couplings.csv` 中存在（不存在时必须是占位或计划状态，报为"计划参数"）；
- `used_in` 中的 M-* / G-* 编号在本文件中有定义；
- 每条关系恰好有一个 `current = yes` 的等级，输入变量都已登记，引用键都在 `references.yaml` 中；
- 加 `--check-data` 时，`drivers` 和 `exposures` 中的数值不超出 `valid_min` / `valid_max`。

English:
- unique ids and valid vocabularies;
- datasets exist;
- coupling ids exist, or are reported as planned;
- method ids are defined in this file;
- one current tier per relation;
- inputs are registered and citations resolve;
- with `--check-data`, values fall inside the declared ranges.

**参考文献 / References:** 全部引用键与完整条目见 [`twin/references.yaml`](../twin/references.yaml)。本规范新增的条目（2026-10-30 经 Crossref 核对 DOI）：alduchov1996, baker2015, birchfield2017, cannon2015, dobney2009, flanagan2011, gasparrini2010, haimes2001, ho2014, housepeters2011, kennedy2001, liljegren2008, liu2007, mennis2003, molinari2017, nairn2015, pierce2023, saltelli2010, shandas2019, sun2020, vanvliet2012, wagner1988, wols2014。无 DOI 的标准 / 报告 / 数据集：bpr1964, eia860, eia930, empower, hcm2022, mohseni1998, rothfusz1990。另加 mohseni1998stream（河温模型，DOI 10.1029/98WR01877）。
