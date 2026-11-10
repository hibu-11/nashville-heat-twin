# 精简主线模型（骨架）Core skeleton model

2026-11-03 · 代码 Code：[`pipeline/twin/core.py`](../pipeline/twin/core.py)、[`pipeline/core.py`](../pipeline/core.py) · 组成清单 Manifest：[`twin/core.yaml`](../twin/core.yaml)

## 0. 结构调整 Structure revision (2026-11-10)

**中文：**
- **气候层只保留两个节点。** 背景气候（气温、地表温度、河温）和城市基础信息（城市热分布，目前是 2022 年走航测温的气温场）。之后会拿到一份完整的历史数据包；在那之前，模拟继续用现有记录（BNA 2014–2025、2023 年地表温度、模拟河温）。
- **暂不考虑经济损失。** D9 经济损失和 D3 车辙成本标为暂停，代码、变量和证据保留。
- **结局层围绕两条线组织，都以就医时间为综合指标。** 医院、养老院、透析中心合并为"医疗设施"一层，各自保留备用规则。A 线：电、水、交通影响医疗设施和路程，使就医时间增加（K6–K8，已模拟）。B 线：高温使热相关病症和就医人数增加，需求超过设施容量时产生等待，同样拉长就医时间（B1，待建）。就医时间 = 路程时间 + 等待时间。

**English:**
- **The climate layer keeps two nodes:** background climate (air temperature, land surface temperature, river temperature) and urban base information (the city's heat pattern, now the 2022 traverse field). A complete historical package will replace the current records (BNA 2014–2025, 2023 LST, modelled river temperature); until then the model runs on them.
- **Economic loss is paused.** D9 economic loss and D3 rutting cost are marked paused; code, variables and evidence are kept.
- **The outcome layer is organised around two lines that both end in time to care.** Hospitals, nursing homes and dialysis centres form one medical-facility layer with their own backup rules. Line A: power, water and transport disrupt facilities and the trip, raising time to care (K6–K8, simulated). Line B: heat raises heat-related illness and the number of people seeking care; demand beyond capacity adds waiting (B1, to build). Time to care = travel time + waiting time.

## 1. 目的与副本 Purpose and the preserved full model

**中文：** 完整模型（v0 + 2026-10-30 的四个模块）把很多关系都接了进来，但其中不少环节的参数是占位值，而且彼此叠加，结果很难解释。骨架模型只保留文献证据最强、从气温到人群受害不可缺少的一条主线，其余环节暂缓，代码不删。完整模型原样保留在 git 分支 `full-model`、标签 `full-model-v1`（提交 `04eb531`）；在 main 上它仍可用 `python -m pipeline.cascade` 运行。

**English:** The full model (v0 plus the four modules of 2026-10-30) wires in many relations, several with placeholder parameters that compound and make results hard to interpret. The core keeps only the chain that the literature supports most strongly and that cannot be cut without breaking the path from air temperature to harm. Everything else is deferred with its code kept. The full model is preserved unchanged on git branch `full-model`, tag `full-model-v1` (commit `04eb531`), and still runs on main as `python -m pipeline.cascade`.

## 2. 选取原则 Selection rule

**中文：** 一个环节进入骨架，需要同时满足：
1. 文献把它记录为"热浪期间高温 → 停电 → 人群受害"链条上的一环；
2. 去掉它，从气温到结局的链条就断了；
3. 用现有数据就能运行。

属于二阶效应、所用机制被文献质疑、或在我们自己的数据中没有作用的环节暂缓。

**English:** A link enters the core only if all three hold:
1. The literature documents it as part of the heat → outage → harm pathway during heat waves.
2. Removing it would cut the chain from air temperature to the outcome.
3. It runs on data we already hold.

Second-order effects, mechanisms the literature warns against, and links that showed no effect in our own data are deferred.

## 3. 骨架 Skeleton

```mermaid
flowchart LR
  BG["背景气候<br/>background climate"] --> K1["K1 本地气温<br/>local temperature"]
  UB["城市基础信息<br/>urban base information"] --> K1
  K1 --> K2["K2 负荷<br/>load"]
  K1 --> K3["K3 变压器热点 → 热失效<br/>hot spot → failure"]
  K2 --> K3
  K2 --> K4["K4 系统缺口 → 轮流停电<br/>shortfall → rotating outages"]
  K3 --> K5["K5 供电依赖 → 分区停电<br/>supply dependency → zone outage"]
  K4 --> K5
  K5 --> K6["K6 水厂 → 断水<br/>water"]
  K5 --> K7["K7 医疗设施（医院 / 养老院 / 透析）<br/>medical facilities"]
  K6 --> K7
  K5 --> K8["K8 信号灯 → 路程；设施关闭 → 改道<br/>signals, closures"]
  K7 --> K8
  K8 ==> T["就医时间（综合指标）<br/>time to care"]
  K5 --> K9["K9 失去制冷 → 室内高温 → 高温暴露<br/>indoor heat → exposure"]
  K1 --> K9
  K9 -. B1 待建 .-> B["热病症与就医需求<br/>heat illness, care demand"]
  B -. B1 待建 .-> T
```

| 环节 Link | 内容 Content | 方法 / 公式 Method | 参数 Parameters | 文献依据 Evidence |
| --- | --- | --- | --- | --- |
| K1 | 城市气温场 θ_A(x,t) / urban air-temperature field | M-6 | — | shandas2019, ho2014 |
| K2 | 气温 → 负荷 / air temperature → load | Eq. 2–3 | C-P1, C-P1.T0, C-P1.Kd, C-P1.Td | auffhammer2017, bartos2016 |
| K3 | 热点温度 → 热失效 / hot spot → thermal failure | Eq. 4–7 | C-P2.*, C-P3, C-P3.sigma | ieee_c5791_2011, bartos2016, shinozuka2000 |
| K4 | 系统缺口 → 轮流停电（负荷侧）/ shortfall → rotating outages (demand side) | M-18 | C-P9.avail, C-P9.imp | auffhammer2017, eia860, eia930 |
| K5 | 供电依赖、分区、固定修复 / supply dependency, zones, fixed repair | Eq. 9–10, 14 | C-P5, C-P6, C-POP1 | buldyrev2010, rinaldi2001 |
| K6 | 水厂失电 → 储水耗尽 / plant power loss → storage exhausted | Eq. 13 | C-W1, C-W2, C-W3 | rinaldi2001, klise2017 |
| K7 | 医院、养老院（备用）；透析（电 ∨ 水）/ facilities | Eq. 11 | C-H1, C-H2, C-H3 | cms2016, kelman2015, anderson2012 |
| K8 | 信号灯熄灭 → 通行能力 → 到医院、透析中心、急救站的行程时间 / dark signals → capacity → travel time to care | Eq. 11, 16, M-28, M-29 | C-T2, C-T3, C-T5, C-T6.* | rinaldi2001, ouyang2014, hcm2022, bpr1964, kelman2015 |
| K9 | 失去空调 → 室内温度 → 暴露 / loss of AC → indoor heat exposure | M-32, M-33 | C-B1–C-B4, C-H10 | stone2023, sun2020 |

**中文：** K8 是交通系统保留的主线：它是交通环节中唯一直接连到健康结局的一条（停电 → 信号灯 → 到医疗服务的时间），而且透析中心停电后患者必须转去别处（Kelman 等 2015）。与完整模型不同，K8 按每次运行在其最坏小时的实际状态计算，保留尾部情形。

**English:** K8 is the transport link kept in the core: it is the one transport pathway that reaches a health outcome (outage → signals → time to care), and patients of a closed dialysis centre must travel elsewhere (Kelman et al. 2015). Unlike the full model, K8 is computed per run at that run's worst hour, so tail cases are kept.

**中文：** K9 是这次新加的一环，也是骨架的结局。Stone 等（2023）发现热浪期间的多日停电使高温死亡率增加一倍以上，机制就是失去制冷后的室内温度，所以骨架停在"室内高温暴露人·小时"上，而不是用室外气温阈值（完整模型的 C-POP2）。

**English:** K9 is new and is the core's endpoint. Stone et al. (2023) found that a multiday blackout during a heat wave more than doubles heat-related mortality, through indoor temperature once cooling is lost. The core therefore ends at indoor heat person-hours rather than an outdoor threshold (C-POP2 in the full model).

## 4. 公式 Equations

**中文：** K2–K8 与完整模型的 Eq. 2–16 相同（见 [`HANDBOOK.md`](HANDBOOK.md) §4），只有两处差别：
- 标幺负荷不再加上邻站转来的负荷；
- 供电依赖迭代里没有过载跳闸。

**English:** K2–K8 follow Eq. 2–16 of the full model ([`HANDBOOK.md`](HANDBOOK.md) §4) with two differences:
- the per-unit load no longer includes load transferred from neighbours;
- the supply-dependency fixed point has no overload trips.

```math
K_s(t)=K_d\,\frac{1+\beta\max(0,T_s(t)-T_0)}{1+\beta\max(0,T_d-T_0)},\qquad
e_s(t)=\neg f_s(t)\wedge\neg\mathrm{shed}_s(t)\wedge\Big(\neg\exists u\to s\ \vee\ \bigvee_{u\to s}e_u(t)\Big)
```

**K8（M-28、M-29）：** 每次运行 $`r`$ 取其降级路段最多的小时 $`h_r`$。受控路段的通行能力乘以该次运行抽到的 $`\varphi_{dark}`$（C-T5），停电的医院与透析中心不再作为目的地；行程时间增量相对同一小时的正常情况计算（BPR 路段延误，TMAS 工作日小时曲线；路段容量参数取中值）。

**K8 (M-28, M-29):** For each run $`r`$, take its hour $`h_r`$ with the most degraded segments. Capacities of controlled segments are multiplied by that run's $`\varphi_{dark}`$ (C-T5) and closed hospitals and dialysis centres are removed as destinations. The increase is taken against the normal time at the same hour (BPR link delay, TMAS weekday profile, mid lane capacities).

```math
\Delta\tau_{c,k}(r)=\min_{f\in F_k\setminus D_r}SP_{\varphi_r}\big(c,f;h_r\big)-\min_{f\in F_k}SP_{1}\big(c,f;h_r\big),\qquad
\overline{\Delta\tau}_k(r)=\frac{\sum_c \mathrm{pop}_c\,\Delta\tau_{c,k}(r)}{\sum_c \mathrm{pop}_c}
```

**K9（M-32、M-33）：** 有电且有空调时室内为 $`T_{set}`$；停电时以热时间常数 $`\tau_b`$ 趋向平衡温度；无空调住户始终自由升温。白天（当地 08:00–20:00）得热温升为 $`\Delta T_{gain}`$，夜间为 1 K。

**K9 (M-32, M-33):** A powered home with AC stays at $`T_{set}`$; during an outage it relaxes towards the equilibrium with time constant $`\tau_b`$. Homes without AC always free-run. The gain lift is $`\Delta T_{gain}`$ by day (local 08:00–20:00) and 1 K at night.

```math
T^{eq}_z(t)=\theta_A(z,t)+\Delta T_{gain}(t),\qquad
T^{AC}_{in,z}(t)=\begin{cases}T_{set} & e_z(t)\\ T^{eq}_z(t)+\big[T^{AC}_{in,z}(t-1)-T^{eq}_z(t)\big]e^{-1/\tau_b} & \neg e_z(t)\end{cases}
```

```math
E^{out}_g=\sum_t\sum_z f_{AC}\,\mathrm{pop}_{z,g}\,\mathbf 1\big[\neg e_z(t)\wedge T^{AC}_{in,z}(t)\ge T_{thr}\big],\qquad
E^{noAC}=\sum_t\sum_z (1-f_{AC})\,\mathrm{pop}_z\,\mathbf 1\big[T^{noAC}_{in,z}(t)\ge T_{thr}\big]
```

**中文：** $`E^{out}`$ 是级联造成的室内暴露（只在停电时出现），按全体、65 岁以上、贫困人口分别统计；$`E^{noAC}`$ 是与停电无关的背景暴露，用来衡量级联的相对大小。

**English:** $`E^{out}`$ is the indoor exposure caused by the cascade (outage hours only), reported for everyone, people aged 65+ and people below the poverty line. $`E^{noAC}`$ is the background exposure unrelated to outages, used as a yardstick.

| 参数 Parameter | 符号 Symbol | 低 / 中 / 高 Low / mid / high | 依据 Basis |
| --- | --- | --- | --- |
| C-B1 | $`\tau_b`$ (h) | 5 / 12 / 40 | literature-informed placeholder (wijesuriya2024, sun2020, leigh2014) |
| C-B2 | $`\Delta T_{gain}`$ (K) | 2 / 4 / 7 | literature-informed placeholder (sun2020, leigh2014) |
| C-B3 | $`T_{set}`$ (°C) | 21 / 22.5 / 24.5 | literature (eia_recs2020) |
| C-B4 | $`f_{AC}`$ | 0.90 / 0.94 / 0.98 | literature (eia_recs2020, census_lace2023) |
| C-H10 | $`T_{thr}`$ (°C) | 26 / 28 / 32 | literature (meade2024, huizenga2024) |

### 4.1 参数取值与数据来源 Parameter values and sources (2026-11-04)

【中文】下表是 2026-11-04 用公开数据替换的骨架参数。「来源等级」：**A** 本地实测或官方统计直接给出；**B** 由官方数据或文献换算（换算是本项目自己做的，写在「换算」一栏）；**C** 文献模拟或从图中读数；**D** 新闻、二手引用或推断，需尽快核实。每条的原文出处与页码、表号写在 [`twin/couplings.csv`](../twin/couplings.csv) 的 `evidence` 列，文献条目在 [`twin/references.yaml`](../twin/references.yaml)。

English: core parameters replaced with public data on 2026-11-04. Source grade: **A** stated directly by local measurements or official statistics; **B** derived from official data or literature (the derivation is this project's own, shown in the "Derivation" column); **C** simulation studies or values read from figures; **D** news, secondary citations or inference, to be verified. Page and table locators are in the `evidence` column of [`twin/couplings.csv`](../twin/couplings.csv); entries are in [`twin/references.yaml`](../twin/references.yaml).

| 参数 Parameter | 旧值 Old | 新值 New | 等级 Grade | 来源 Source (locator) | 换算 Derivation |
| --- | --- | --- | --- | --- | --- |
| C-P6 修复时长 repair hours (h) | 4 / 8 / 24 | 1 / 3 / 12 | B | eaglei2023, Davidson 2015–2025 excl. 2018; `scripts/eaglei_restoration.py` | Non-storm events > 3,000 customers, ≥ 30 min (n = 278): q50 1.38 h, q90 5.25 h; storm q90 12.8 h. Customer outage time incl. switching |
| C-P9.avail TVA 可用容量比例 available share | 0.82 / 0.88 / 0.93 | 0.83 / 0.90 / 0.95 | B | nerc_sra 2022–2026 (risk-scenario table, SERC-Central); tva10k FY2023 | (1 + typical-outage margin)/(1 + anticipated margin) = 0.924–0.958; Elliott ≈ 0.81. SERC-Central ⊃ TVA |
| C-P9.imp 净输入 net import (MW) | 0 / 1,500 / 3,000 | 1,000 / 4,000 / 6,900 | A/B | eia930 TVA 2016–2025 Jun–Sep; nerc_itcs2024 (ETI07, p. 64) | Peak-hour net import 4,282 / 5,716 / 5,067 MW (2023–25); transfer capability 6,878 MW |
| C-H1 医院备用电源失效 hospital backup fails | 0.02 / 0.05 / 0.15 | 0.01 / 0.05 / 0.15 | B/D | marqusee2020 (Tables 2–4); irvinbarnwell2020; klinger2014 (secondary); hhs_oig_sandy2014 (p. 13) | Failure to start 0.13–1.65%; disasters 6–11% |
| C-H2 养老院无法维持制冷 nursing home cannot keep cooling | 0.10 / 0.30 / 0.50 | unchanged | D | hhs_oig_nh2026; tn_0720_18 | 73% of homes with power-system deficiencies; TN does not require generator cooling. No measured rate |
| C-W2 水厂备用电源失效 plant backup fails | 0.05 / 0.15 / 0.30 | 0.02 / 0.05 / 0.15 | B | metrowater2024 (p. 6); marqusee2020 | Four generators per plant; Harrington runs 72 of 90 MGD on backup |
| C-W3 储水时长 storage (h) | 6 / 12 / 24 | 5 / 10 / 18 (2026-11-10) | B | metrowater2024 (pp. 6–7); MWS commercial-paper memorandum Dec 2025 | 51.7 MG in service (98.3 MG was a drafting inconsistency) ÷ 109.5–137.8 MGD = 9–11 h; ~84 MG after the 8th Ave rebuild = 15–18 h; usable share ~50% assumed for the low end |
| C-T2 无电池信号灯比例 signals without battery | 0.50 / 0.75 / 1.00 | 0.75 / 0.90 / 1.00 | D | wsmv2025 (news); nysdot2009 (pp. 19–25) | 36 of ~600 signals with batteries (~6%). Battery hours 2–8 h not modelled |
| C-T5 熄灯通行能力系数 dark-signal capacity factor | 0.40 / 0.50 / 0.70 | 0.35 / 0.50 / 0.65 | B | french1956 (pp. 22, 27–28); kyte1994 (p. 111); alkaisy2023 | 500 veh/h/lane ÷ (1,750 × 0.45 green) ≈ 0.6; lower on multilane arterials |
| C-B1 τ_b (h) | 5 / 15 / 40 | 5 / 12 / 40 | C | wijesuriya2024 (Fig. 7); sun2020 (Fig. 4); leigh2014 (Fig. 4) | No fitted τ published; own fit to Leigh Fig. 4 gives 6–12 h |
| C-B2 ΔT_gain (K) | 1 / 3 / 6 | 2 / 4 / 7 | C | sun2020 (Figs. 4, 12); leigh2014 (Fig. 4) | Daily-mean lift 2–5 K read from figures; night lift 5–7 K (model keeps 1 K) |
| C-B3 T_set (°C) | 23 / 24 / 25 | 21 / 22.5 / 24.5 | A | eia_recs2020 HC7.8 (East South Central) | Median daytime setting 71–73 °F |
| C-B4 f_AC | 0.85 / 0.92 / 0.97 | 0.90 / 0.94 / 0.98 | A | eia_recs2020 (TN 93%); census_lace2023 (Davidson 97.7%, tracts 89.7–100%) | — |
| C-H10 T_thr (°C) | 26 / 28 / 32 | unchanged | B | meade2024; huizenga2024 (pp. 7–8) | 26 older adults, 28 general, 32 acute strain |

【中文】仍缺的：NES 变压器额定容量与馈线分区（PWR-03、PWR-20，需合作）、Nashville 信号灯 UPS 清单（向 NDOT 申请）、夜间室内外温差参数化、电池续航时长建模。变电站峰值负荷的公开量级（平均每站约 13 MW，eia861、nes_fiscalfacts）已记入 PWR-04，模型仍用相对负荷。

English: still missing are NES transformer ratings and feeder zones (PWR-03, PWR-20; partner data), the Nashville signal UPS inventory (NDOT request), a night-lift parameter and battery runtime. The public scale of substation peak load (~13 MW mean, eia861, nes_fiscalfacts) is recorded under PWR-04; the model still uses relative loads.

### 4.2 因果贡献：敲除实验 Causal contribution by knockout (2026-11-10)

**中文：** 对关系图集中的每条关系，用相同的随机数分别运行"全部开启"和"只关掉这一条"（do 干预），贡献 = (基准 − 敲除) / 基准。正值表示这条关系放大结局，负值表示它起缓冲作用。结局有三个：A 线的就医时间增量（医院、透析、急救三类设施人口加权的增加分钟数之和，取每次运行最坏的小时）、停电人·小时，以及 B 线的输入"室内高温暴露人·小时"。串联链上任何一环被关掉，下游效果都会消失，所以串联各环的贡献相同，各条的贡献也不能相加。程序：`python -m pipeline.contrib --runs 1000 --scenarios 2,4`，输出 `site/data/twin/core/contrib.json`；结果见第 6 节和关系图集。

**English:** For each relation in the atlas, the core model is run with everything on and with only that relation switched off (a do-intervention), using the same random numbers; contribution = (base − knockout) / base. Positive means the relation adds to the outcome; negative means it buffers. Three outcomes: line A time to care (population-mean added minutes to hospital, dialysis and EMS, summed, at each run's worst hour), person-hours without power, and indoor heat exposure (the input of line B). Switching off any link in a series chain removes everything downstream, so series links share the same contribution and contributions do not add up. Command: `python -m pipeline.contrib --runs 1000 --scenarios 2,4`; output `site/data/twin/core/contrib.json`.

**K8 的两处修正 Two changes to K8 (2026-11-10):**
- 每次运行的"最坏小时"原来只按降级路段数选，改为降级路段数加关闭的医院与透析中心（每家记 500），使有设施关闭的小时优先。否则关掉信号灯时找不到最坏小时，设施关闭的影响也会被漏算。The worst hour now counts closed hospitals and dialysis centres (500 each) as well as degraded segments; otherwise switching signals off would also hide facility closures.
- 研究区内某类设施全部不可达时，受影响人口按增加 30 分钟计入就医时间（假设：研究区外的设施不在路网中）。Cells that lose every facility of a type inside the area count 30 added minutes (assumption: facilities outside the area are not on the network).
- 每小时都抽取轮流停电的随机数，保证不同敲除之间的随机数对齐。The rotating-outage random draw is made every hour so that knockouts share random numbers.

### 4.3 B 线初步检验 First test of line B (2026-11-10)

**中文：** 田纳西卫生厅公布的 Davidson 每年高温病症急诊人次（2012–2023，T1）与 BNA 当年 5–9 月高温指标在 10 个重叠年份（2014–2023）中正相关：≥35 °C 天数 ρ = 0.73（p = 0.02），日均气温超过 25 °C（Nashville 最低死亡温度）的度日 ρ = 0.67；周边五县合计结果相同。对数线性拟合：每增加 1 个度日，急诊约增加 0.44%（标准误 0.11%），从最凉年（约 110 度日）到最热年（约 230 度日）约多 70%。2020 年偏低，可能与疫情期间回避就医有关。这只说明年度尺度存在信号；B 线需要逐日急诊数据来拟合暴露–反应关系。脚本 `scripts/heat_ed_annual.py`，结果 `twin/evidence/heat_ed_annual.json`。

**English:** Davidson's annual heat-illness ED visits (Tennessee Department of Health, 2012–2023, T1) rise with BNA's May–September heat over the ten overlapping years (2014–2023): days ≥ 35 °C ρ = 0.73 (p = 0.02); degree-days of daily mean above 25 °C (Nashville's minimum-mortality temperature) ρ = 0.67; the five-county total gives the same. A log-linear fit gives about +0.44% visits per degree-day (SE 0.11%), about 70% more visits from the coolest year (~110 degree-days) to the hottest (~230). 2020 is low, probably COVID-19 care avoidance. This shows an annual signal only; line B needs daily ED counts to fit an exposure–response curve. Script `scripts/heat_ed_annual.py`; output `twin/evidence/heat_ed_annual.json`.

### 4.4 核对发现的规则缺口 Rule gaps found in the 2026-11-10 audit

**中文：**
- 轮流停电（K4）随机切除供电站，没有保护医院所在的线路；现实中拉闸限电通常避开关键负荷。
- 急救站（消防站）被假设始终有电，没有对应的停电关系；消防站一般有发电机，但这是假设。
- 信号灯电池只有有 / 无两种状态，没有 2–8 小时的续航。
- 路段通行能力与 BPR 系数（C-T6.*）固定取中值，它们的不确定性不在敏感性分析中。
- 补入 B 线的两条待建关系：养老院失去制冷 → 住户高温暴露；分区停电 → 依赖电力设备的居民 → 就医需求（见 core.yaml B1）。

**English:**
- Rotating outages (K4) shed serving stations at random and do not protect hospital feeders; real load shedding usually spares critical loads.
- EMS (fire) stations are assumed always powered; there is no outage relation for them.
- Signal batteries are on or off, without 2–8 h of runtime.
- Link capacities and BPR coefficients (C-T6.*) are fixed at mid values, so their uncertainty is not in the sensitivity analysis.
- Two to-build relations added to line B: nursing-home cooling loss → residents' heat exposure; zone outage → electricity-dependent residents → care demand (core.yaml B1).

## 5. 暂缓的细节 Deferred details

| 编号 Id | 细节 Detail | 暂缓理由 Reason | 加回方式 How it returns |
| --- | --- | --- | --- |
| D1 | 同电压站负荷转移与过载跳闸（Motter–Lai，C-P4）/ peer transfer and overload trips | 纯拓扑的负荷重分配可能误判电网脆弱性（hines2010）；真实连锁服从潮流（dobson2007）。完整模型中约 89% 的停电人·小时来自这一机制（2026-11-04 参数），而容忍度 α 是假设值。Topological redistribution can mislead; it produced ~89% of person-hours in the full model with an assumed α. | 有额定值后以直流潮流加回（R-P5 2–3 级）/ as DC power flow once ratings exist |
| D2 | 河温 → 火电降额（K4 供给侧）/ river derating | 2014–2025 年模拟河温最高 27.3 °C，低于阈值；各情景降额相同。Modelled river temperature never reached the threshold. | 打开 M-18 供给侧（代码在 `pipeline/twin/river.py`）/ enable the supply side of M-18 |
| D3 | 路面高温 → 车辙 → 铺装成本 / pavement heat → rutting → resurfacing cost | 长期经济路径，不属于急性级联，接到经济损失 D9。HPMS 2024：夏季 LST 每高 1 °C 车辙深约 1.8%（4,269 个路段，R² 0.09，横截面）。A long-run cost pathway feeding D9; HPMS shows rut depth about 1.8% deeper per °C of LST (cross-sectional). | 有单价与多年车辙测量后（M-10、M-45）/ with unit costs and rut survey panels (M-10, M-45) |
| D5 | 室外复合暴露阈值（C-POP2）/ outdoor compound threshold | 由 K9 取代。Replaced by K9. | — |
| D6 | 归因死亡与急诊（M-34）/ attributable deaths and ED visits | 需要 Nashville 温度–死亡曲线与基线死亡数（HLT-13、HLT-14）。Needs local exposure–response and baseline deaths. | 以 K9 的室内暴露为输入 / takes K9 exposure as input |
| D7 | 修复过程（M-16）/ restoration process | 等 NES 修复记录。Awaits NES restoration records. | 替换 C-P6 / replaces C-P6 |
| D8 | 配电变压器、线路载流量、水力及医院 / 养老院用水、依赖电力设备者、透析转诊、避暑中心 / other refinements | 需要尚未获得的数据。医院、养老院在依赖图中连到供水，但骨架只对透析中心使用断水（医院有自备储水，且运行中未出现断水）。Need data we do not hold. Hospitals and nursing homes are linked to water in the graph, but the core applies water loss to dialysis only. | 见 [`PIPELINE_SPEC.md`](PIPELINE_SPEC.md) §8 |
| D9 | 经济损失：用户停电损失、健康结局货币化 / economic loss | 健康之外的第二个结局。停电损失 = 用户·小时 × 供电可靠性价值（sullivan2015）；健康损失 = 归因死亡 × 统计生命价值（usdot_vsl），需等 D6。两者分开报告。The second endpoint besides health; outage cost from customer-hours × value of service reliability, health cost after D6. | 需要 NES 按分区、用户类别的户数 / needs NES customers by class per zone |

## 6. 结果 Results

运行 Run `core-20261110T191340Z-0ed4b5b116`：2023 年 6–8 月，2,000 次蒙特卡洛，城市气温场开启，参数为 §4.1 加上 2026-11-10 的储水时长（5/10/18 h），K8 按 §4.2 的两处修正计算；与完整模型 `cascade-20261110T191034Z-0ed4b5b116` 使用相同的随机种子和参数表。括号里是 2026-11-04 的上一次运行 `core-20261104T184037Z-e8e2407fbb`。

Run `core-20261110T191340Z-0ed4b5b116`: June–August 2023, 2,000 Monte Carlo runs, urban air field on, parameters of §4.1 plus the 2026-11-10 storage range (5/10/18 h), K8 with the two changes of §4.2; same seed and coupling table as the full-model run `cascade-20261110T191034Z-0ed4b5b116`. Values in brackets are the previous run of 2026-11-04.

| 指标 Output（均值 mean） | +0 °C | +2 °C | +4 °C |
| --- | --- | --- | --- |
| 有停电的运行比例 runs with any outage | 12.1% (12.0%) | 33.7% (33.5%) | 61.8% (61.2%) |
| 停电人·小时（骨架）person-hours without power (core) | 15k (15k) | 143k (147k) | 819k (806k) |
| 停电人·小时（完整模型）(full model) | 142k (142k) | 1.35M (1.35M) | 6.63M (6.63M) |
| 失去空调人·小时 person-hours without AC due to outages | 14k (15k) | 134k (139k) | 770k (758k) |
| 其中室内超过阈值 of which indoor ≥ threshold, $`E^{out}`$ | 0.9k (1.0k) | 14k (15k) | 140k (136k) |
| 65 岁以上 aged 65+ | 86 (97) | 1.3k (1.4k) | 13k (13k) |
| 贫困人口 below poverty | 169 (181) | 2.6k (2.7k) | 25k (25k) |
| 背景暴露（无空调住户）background, $`E^{noAC}`$ | 5.8M | 10.0M | 13.2M |
| TVA 缺口运行比例 runs with a TVA shortfall | 0 | 0 | 4.2% |
| 断水小时 water-out hours | 0 | 0 | 0 |
| K8：就医时间增量（医院 + 透析 + 急救）time to care, added minutes per person | 0.06 | 0.73 | 3.9 |
| K8：有路段降级或设施关闭的运行 runs with degraded segments or closures | 11.7% | 33.2% | 61.0% |
| K8：到医院平均时间增量（p99）hospital Δ, population mean (p99) | 0.004 (0.08) min | 0.016 (0.23) min | 0.048 (0.41) min |
| K8：到透析中心平均时间增量（p99）dialysis Δ (p99) | 0.04 (1.6) min | 0.22 (5.2) min | 0.50 (5.3) min |
| K8：研究区内没有可用透析中心的运行 runs with no dialysis centre available | 0.05% (0) | 1.6% (0.8%) | 11.1% (8.9%) |
| K8：到急救站平均时间增量（p99）EMS Δ (p99) | 0.002 (0.04) min | 0.007 (0.08) min | 0.018 (0.12) min |

In the K8 rows the brackets give the 99th percentile. The K8 figures moved because the worst hour now also counts facility closures (§4.2).

**中文：**
- **储水时长调整**（6/12/24 → 5/10/18 h）后仍没有一次运行断水；其余变化来自随机数对齐和 K8 最坏小时的新定义，量级很小。
- **过载转移仍主导完整模型。** 去掉 D1 后，停电人·小时在三个情景下都减少约 88–89%。
- **室内暴露随升温增加。** 失去空调的人·小时里，室内超过阈值的比例从 +0 °C 的 6.5% 升到 +4 °C 的 18%。$`\tau_b`$ 和 $`\Delta T_{gain}`$ 仍是文献推断的占位值。
- **级联暴露远小于"没有空调"的背景暴露**（+0 °C 下约 6,200 倍）。
- **A 线：设施关闭远比堵车重要。** 就医时间增量 +4 °C 时人均 3.9 分钟，其中约 98% 来自设施关闭（§6.1）；+4 °C 时 11.1% 的运行在最坏小时研究区内没有可用的透析中心。BPR 不含路口全向停车延误，拥堵部分是下限。
- **敏感性**仍由变压器参数主导：C-P1.Kd ρ = 0.40、C-P3.sigma 0.28、C-P3 −0.24。对停电造成的室内暴露，排第一的是建筑热时间常数 C-B1（−0.15），其后是 C-P1.Kd（0.15）、C-P3.sigma（0.13）、修复时长 C-P6（0.12）。
- **验证：** 模型与 EAGLE-I 逐小时停电的相关 ρ = 0.042 [−0.038, 0.112]，仍没有信号（县级停电由风暴主导）。

**English:**
- **Storage range** (6/12/24 → 5/10/18 h): still no run loses water; other changes come from random-number alignment and the new K8 worst hour, and are small.
- **Overload transfer still dominates the full model.** Without D1, person-hours without power fall by about 88–89% in every scenario.
- **Indoor exposure grows with warming.** The share of AC-loss person-hours with indoor temperature above the threshold rises from 6.5% at +0 °C to 18% at +4 °C. $`\tau_b`$ and $`\Delta T_{gain}`$ are still literature-informed placeholders.
- **Cascade exposure is small next to the no-AC background** (about 6,200 times at +0 °C).
- **Line A: facility closures matter far more than congestion.** Time to care rises by 3.9 min per person at +4 °C, about 98% of it from closures (§6.1); 11.1% of +4 °C runs have no dialysis centre open at their worst hour. BPR omits all-way-stop delay, so congestion is a lower bound.
- **Sensitivity** is led by transformer placeholders (C-P1.Kd ρ = 0.40, C-P3.sigma 0.28, C-P3 −0.24). For indoor exposure from outages, the building time constant C-B1 ranks first (−0.15), then C-P1.Kd (0.15), C-P3.sigma (0.13) and repair time C-P6 (0.12).
- **Validation:** ρ(model, EAGLE-I hourly) = 0.042 [−0.038, 0.112]; still no signal, because county outages are storm-driven.

### 6.1 因果贡献 Knockout contributions

`python -m pipeline.contrib --runs 1000 --scenarios 2,4`（方法见 §4.2）。贡献 = 只关掉这一条关系时结局下降的比例；负值表示缓冲。串联各环贡献相同，不能相加。Contribution = share of the outcome lost when only that relation is switched off; negative = buffer. Series links share the same value; figures do not add up.

| 关系 Relation | 关掉什么 What is switched off | 就医时间 time to care +2 / +4 °C | 停电人·小时 person-hours without power +4 °C | 室内暴露 indoor exposure +4 °C |
| --- | --- | ---: | ---: | ---: |
| R01 背景气候 × 城市基础信息 | 全城用机场气温 / airport series everywhere | −38% / −18% | −1.6% | −4.8% |
| R02 气温 → 负荷 | 负荷不随气温变化 / no load response | 100% / 100% | 100% | 1.1% |
| R03a 环境气温 → 热点 | 环境取时期平均 / period-mean ambient | 92% / 84% | 84% | 1.0% |
| R03b 负荷 → 热点 | 负荷取时期平均 / period-mean load | 100% / 99% | 100% | 1.1% |
| R04 热点 → 热失效 | 无热失效 / no thermal failure | 100% / 100% | 100% | 1.1% |
| R05、R06 系统缺口 → 轮流停电 | 无轮流停电 / no rotating outages | 0% / 0.4% | 0.1% | 0% |
| R07 修复时长 | 失效一小时后恢复 / back after 1 h | 33% / 32% | 73% | 1.1% |
| R08 供电依赖 | 不向下游传播 / no upstream propagation | 52% / 43% | 34% | 0.5% |
| R09、R10 水厂与储水 | 水厂不失电；无储水缓冲 / plants always powered; no storage | 0% / 0% | 0% | 0% |
| R11 分区停电 → 医疗设施 | 设施不因停电关闭 / no facility closures from outages | 96% / 98% | 0% | 0% |
| R12 供水 → 医疗设施 | 透析不受断水影响 / dialysis ignores water | 0% / 0% | 0% | 0% |
| R13 分区停电 → 信号灯 | 信号灯不熄灭 / no dark signals | 10% / 3.4% | 0% | 0% |
| R14–R16 通行能力 → 路程 | 熄灯不降低通行能力 / no capacity loss | 3.4% / 1.8% | 0% | 0% |
| R17 设施关闭 → 改道 | 关闭的设施仍可到达 / closures ignored | 97% / 98% | 0% | 0% |
| R18 停电 → 室内温度 | 停电时室内保持设定温度 / set point kept | 0% / 0% | 0% | 1.1% |
| R19 本地气温 → 室内平衡温度 | 室内不受室外驱动 / indoor not driven by outdoor | 0% / 0% | 0% | 100% |

**中文：**
- **A 线几乎完全由"变压器过热 → 停电 → 设施关闭"驱动。** 关掉设施关闭（R11）或改道（R17），就医时间增量减少 96–98%；关掉信号灯熄灭只减少 2–10%。
- **高温通过两个入口进入电网，缺一不可。** 负荷随气温上升（R02）和热点对环境气温的直接响应（R03a）都接近 100%，而这两个环节的数据分级是 T4 和 T2；负荷的设计负荷率 K_design 是纯假设，是最需要 NES 数据的地方。
- **修复时长贡献 73% 的停电人·小时**（关掉后停电只持续一小时）：它决定的是停电多久，而不是是否停电。
- **城市气温场是负贡献（−18% 到 −38%）。** Nashville 大部分变电站比机场凉，用机场气温会高估停电。
- **供水和系统缺口在当前参数下贡献为零**，说明在这些情景里它们不是风险来源，而不是说它们不重要。
- **停电只贡献室内高温暴露的约 1%；** 其余来自无空调住户。B 线的就医需求因此主要由高温本身驱动，停电是加剧因素。

**English:**
- **Line A is driven almost entirely by transformer overheating → outage → facility closure.** Switching off facility closures (R11) or rerouting (R17) removes 96–98% of the added time to care; switching off dark signals removes 2–10%.
- **Heat enters the grid through two gates, both indispensable:** load response (R02) and the direct ambient effect on the hot spot (R03a) are each near 100%; the load gate rests on K_design, a T4 assumption and the first item to obtain from NES.
- **Repair time accounts for 73% of person-hours without power:** it sets how long outages last, not whether they happen.
- **The urban field contributes negatively (−18% to −38%)**: most substations are cooler than the airport, so the airport series overstates outages.
- **Water and system shortfall contribute nothing under current parameters,** meaning they are not risk sources in these scenarios, not that they are unimportant.
- **Outages account for about 1% of indoor heat exposure;** the rest comes from homes without AC, so line B demand will be driven mainly by heat itself, with outages as an aggravating factor.

## 7. 加回细节的规程 Protocol for adding a detail back

**中文：**
1. 在 `pipeline/twin/core.py` 里以函数或开关实现该细节，默认关闭；
2. 在 `twin/core.yaml` 中把它从 `deferred` 移到 `links`，写明证据；
3. 运行 `python -m pipeline.registry` 检查编号；
4. 开、关各跑一次 `python -m pipeline.core`，在 RESULTS.md 记录差异；
5. 只有当差异有数据或文献支持时才默认打开。

**English:**
1. Implement the detail in `pipeline/twin/core.py` as a function or switch, off by default.
2. Move it from `deferred` to `links` in `twin/core.yaml` with its evidence.
3. Run `python -m pipeline.registry`.
4. Run `python -m pipeline.core` with it on and off and record the difference in RESULTS.md.
5. Turn it on by default only when data or literature support the difference.

## 8. 命令 Commands

```
.venv/bin/python -m pipeline.build                     # 参数表改动后重建 / after editing twin/couplings.csv
.venv/bin/python -m pipeline.core --runs 2000           # 骨架模型 / core model (~3 min)
.venv/bin/python -m pipeline.cascade --runs 2000        # 完整模型 / full model
.venv/bin/python -m pipeline.report                     # RESULTS.md（含 §11 骨架 / incl. §11 core）
.venv/bin/python -m pipeline.registry                   # 登记表与 core.yaml 检查 / registry and core.yaml check
```
