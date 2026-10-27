# Nashville Heat Cascade Digital Twin — Model Handbook

**Version:** dependency model v0 · **Date:** 2026-10-27 · **Status:** preliminary. Several links and parameters are placeholders; they are listed in §3.4 and §6 and are marked in every table and on the map.

This handbook records the logic, every equation and every parameter source used by the v0 heat-cascade model. Numbers in brackets such as (Eq. 7), (R-P3) and (C-H1) are the identifiers used in the code (`pipeline/twin/`), in the standard tables and on the web viewer (`site/cascade.html`). Results of the current run are generated automatically into [`RESULTS.md`](RESULTS.md).

Contents: [1 Scope](#1-scope) · [2 Data](#2-data) · [3 Logic system](#3-logic-system) · [4 Equations](#4-equations) · [5 Simulation procedure](#5-simulation-procedure) · [6 Parameters](#6-parameters) · [7 Validation design](#7-validation-design) · [8 Limitations](#8-limitations-and-next-steps) · [9 Reproducibility](#9-reproducibility) · [10 References](#10-references)

---

## 1. Scope

| Item | v0 choice |
| --- | --- |
| Area | Downtown AOI `[-86.837, 36.118, -86.727, 36.208]` (EPSG:4326). Power and water assets are taken from a ~4 km wider box so that service zones at the AOI edge are correct. |
| Period | 2023-06-01 – 2023-08-31, hourly (2,208 h). Pavement module: 2023-07-01 – 07-21, the span of the 10 m hourly LST. |
| Systems | Power (substations, lines, service zones), water (production and storage), health (hospitals, dialysis, nursing homes), transportation (roads, signals, bridges), population (ZCTA). |
| Drivers | Hourly air temperature at Nashville International Airport (ASOS BNA); 10 m hourly land surface temperature (LST v4.1). |
| Observations used for validation | EAGLE-I county outage counts (Davidson); hubNashville 311 road requests. |
| Scenarios | Observed 2023 temperature and uniform offsets of +2 °C and +4 °C. These are sensitivity scenarios, not climate projections. |

The model follows the design's stage structure: heat exposure (stage A), cascade propagation (stage B), Monte Carlo uncertainty (stage C) and a first comparison with observed events (stage D).

---

## 2. Data

### 2.1 Assets (all real locations)

| Dataset id | Assets in model | Source | Quality rank |
| --- | --- | --- | --- |
| `osm_substations` | 78 substations (3 transmission, 31 distribution, 36 minor distribution, 4 industrial, 1 generation, 3 untyped), with voltage tags | OpenStreetMap via Overpass [osm2026] | 3 |
| `osm_power_lines` | 289 transmission lines, 20 cables, 5,689 distribution lines | [osm2026] | 3 |
| `osm_water` | 3 water works, 3 water towers, 2 covered reservoirs, 2 wastewater plants | [osm2026] | 3 |
| `osm_traffic_signals` | 422 signals in the AOI | [osm2026] | 3 |
| `tdot_bridges` | 184 bridges with condition ratings | [tdot_bridges] | 2 |
| `hospitals` / `dialysis` / `nursing_homes` | 6 / 5 / 4 facilities in the AOI | [cms_provider] | 2 |
| `zcta_population` | 20 ZCTA pieces clipped to the AOI; counts scaled by area share | [acs2020] | 2 |
| `buildings_aoi` | 60,547 building footprints (zone load weights only) | Metro Nashville footprints via twin_demo | 2 |
| `roads_lst` | 4,137 road segments | TIGER/Line + LST buffer statistics | 2 |

### 2.2 Drivers and observations

| Dataset id | Content | Source |
| --- | --- | --- |
| `asos_bna` | Hourly air temperature, dew point, humidity, wind and present weather (thunder flag) at BNA; routine reports rounded to the nearest hour; 0 hours missing in the period | [iem_asos] |
| `lst_hourly_2023` | 165 hourly 10 m LST frames, 09:00–17:00 CDT, 2023-07-01 – 07-21; 26 frames flagged `suspect` (pixel-identical pairs) | LST v4.1 |
| `eaglei_2023` | Davidson County customers out, 15-min snapshots → hourly maximum | [eaglei2023] |
| `hub311_2023` | 311 infrastructure requests; road-type requests matched to segments within 30 m | [hub311] |

**Data assumptions.**
A-D1: EAGLE-I `run_start_time` is treated as UTC.
A-D2: hours with no EAGLE-I record count as zero customers out.
A-D3: LST is used as a proxy for pavement surface temperature; `suspect` frames are excluded.
A-D4: BNA air temperature represents the whole AOI (the urban heat island is ignored for the power module).

### 2.3 Standard tables

The model reads only the standard tables written by `python -m pipeline.build`, all stored in EPSG:32616: `assets`, `dependencies`, `couplings`, `exposures`, `events`, `sources`, plus the auxiliary `drivers` table (station time series, not attached to an asset). Every dependency row carries `rule_id`, `coupling_id`, `gate`, `placeholder` and `quality_rank`. Automatic checks (required fields, CRS, geometry, time order and range, duplicate ids, foreign keys, `param_low ≤ param_mid ≤ param_high`) run on every build.

---

## 3. Logic system

### 3.1 Systems and edge semantics

An edge `from_asset → to_asset` means the downstream asset needs the upstream one. Edges differ by:

- **dep_type**: `power` (supply), `power_peer` (load transfer between same-voltage stations), `water`, `water_storage`, `control` (signal → road), `structural` (bridge → road), `access` (road → facility).
- **gate**, which sets how upstream failures combine:
  - `series`: the downstream asset fails if *any* upstream asset fails.
  - `redundant`: the downstream asset fails only if *all* upstream assets fail.
- **placeholder**: `yes` when the link is assumed rather than observed.
- **quality_rank**: 2 means real data with a direct relationship, 3 means inferred from real data, 4 means placeholder.

This follows the physical / cyber / geographic / logical taxonomy of Rinaldi et al. (2001) [rinaldi2001] and the network-based modelling class reviewed by Ouyang (2014) [ouyang2014]. Failures that propagate between interdependent networks follow Buldyrev et al. (2010) [buldyrev2010].

```
Air temperature ──C-P1…C-P3──► Substations ◄──R-P1 / R-P1b / R-P2──► Substations
                                    │  R-P3 (series)
                                    ▼
                              Service zones ──R-P4──► Hospitals (C-H1, backup) · Nursing homes (C-H2, backup)
                                    │                 Dialysis (C-H3, no backup) · Water works (C-W2, backup)
                                    │                 Traffic signals (C-T2, battery) · Population (C-POP1)
Water works ──R-W1 (redundant)──► Health facilities ◄──R-W2 storage (C-W3)
Traffic signals ──R-T1──► Road segments ◄──R-T2── Bridges          LST ──C-T1──► Road segments
```

### 3.2 Rules

| Rule | From → to | Method | Real / placeholder | Edges (v0) | Coupling |
| --- | --- | --- | --- | --- | --- |
| R-P1 | substation → substation | Connectivity along OSM transmission lines and cables. Line vertices within 60 m of a substation belong to it; a BFS from each station stops at the first other station reached. A higher-voltage station supplies a lower one; equal-voltage stations become load-transfer peers. | inferred (real lines) | 68 supply + 76 peer (38 pairs) | C-P5 / C-P4 |
| R-P1b | substation → serving substation | For serving stations without an R-P1 feed: up to two nearest higher-voltage stations reachable along distribution lines. | inferred (switch states unknown) | 51 | C-P5 |
| R-P2 | substation → serving substation | Stations still without a feed are connected to the nearest higher-voltage station within 12 km. | placeholder | 8 | C-P5 |
| R-P3 | substation → service zone | Voronoi tessellation of serving substations, clipped to the AOI [okabe2000]. | placeholder | 40 | C-P5 |
| R-P4 / R-P4b | zone (or nearest station) → asset | An asset is served by the zone it lies in, otherwise by the nearest serving station. | placeholder | 548 + 2 | C-H1, C-H2, C-H3, C-W2, C-T2, C-POP1 |
| R-W1 | water works → health facility | Every production source supplies every facility (redundant). | placeholder | 45 | C-W1 |
| R-W2 | storage → health facility | Towers and covered reservoirs buffer supply. | placeholder | 75 | C-W3 |
| R-T1 | signal → road segment | Segments within 30 m of a signal. | real proximity | 2,076 | C-T3 |
| R-T2 | bridge → road segment | Nearest segment within 30 m. | real proximity, not propagated | 184 | C-T4 |
| R-A1 | road segment → facility | Nearest segment within 300 m. | real proximity, not propagated | 15 | C-A1 |

In total there are 3,188 edges, of which 22.5% are placeholders. Edge counts are regenerated on every build (`site/data/twin/logic.json`).

### 3.3 Why R-P1 uses transmission lines only

In OSM, distribution lines form a mesh because normally-open tie switches are not mapped. When they were included in the BFS, every station appeared connected to a dozen others (910 supply edges and 675 peer links among 78 stations), which is not physical. They are therefore used only for R-P1b, which finds the nearest upstream source.

### 3.4 Placeholder register

The placeholders to replace are listed below, roughly in order of influence on results (see the sensitivity ranking in [`RESULTS.md`](RESULTS.md)):

1. Substation design loading `K_design` (C-P1.Kd) and the transformer hot-spot fragility `θ50`, `σ` (C-P3). These need NES transformer ratings and peak loads.
2. Service zones (R-P3/R-P4). These need NES feeder or service-territory maps.
3. Transformer thermal constants (C-P2.*). These need nameplate data.
4. Backup power on demand (C-H1, C-H2, C-W2), signal batteries (C-T2) and water storage hours (C-W3). These need facility surveys and Metro Water data.
5. Water network topology (R-W1/R-W2). This needs a hydraulic model (WNTR, [klise2017]) built on the Metro Water network.
6. Repair duration (C-P6). This needs NES restoration records.

Modelling assumptions:
- **A-P1**: stations with no supply edge are fed by an always-available external grid.
- **A-P2**: Voronoi service zones.
- **A-P3**: design load is proportional to the building footprint area of each zone; a non-serving station's load is the sum of the stations it feeds directly; loads are normalised by the median.
- **A-P4**: a slope fitted to monthly sales is applied hourly.
- **A-P5**: load moves only between same-voltage peers.
- **A-P6**: distribution-line connectivity ignores switch states.
- **A-W1**: every OSM `water_works` is treated as a production source (the "Ewing Creek" feature may be a pumping or wastewater asset; to be verified).
- **A-H1**: backup failures are independent per outage episode.

---

## 4. Equations

Notation: $`s`$ is a substation, $`z`$ a service zone, $`f`$ a facility, $`i`$ a road segment, $`t`$ an hour, $`\Delta t = 1`$ h. $`\theta_A(t)`$ is the air temperature in °C and $`T(t)`$ the same temperature in °F. $`\Phi`$ is the standard normal CDF. Each parameter's symbol is followed by its coupling id.

### Stage A — exposure

**Eq. 1 — zonal LST.** $`P_i`$ is the set of 10 m pixels whose centres fall inside asset $`i`$ (lines are buffered by 15 m with flat caps). If none do, the pixel under the centroid is used.

```math
\overline{\mathrm{LST}}_i(t)=\frac{1}{|P_i^{\mathrm{valid}}(t)|}\sum_{p\in P_i^{\mathrm{valid}}(t)}\mathrm{LST}_p(t),\qquad
\mathrm{LST}^{\max}_i(t)=\max_{p\in P_i^{\mathrm{valid}}(t)}\mathrm{LST}_p(t)
```

The quality flag is `ok` if at least 50% of $`P_i`$ is valid, otherwise `partial`. It is `suspect` if the frame is pixel-identical to another frame.

### Stage B — power

**Eq. 2 — load–temperature multiplier** (C-P1 $`\beta`$, C-P1.T0 $`T_0`$). Piecewise-linear above a threshold, fitted to Tennessee EIA-861M sales [cascadingheat2026]. That load rises with summer temperature is documented by Bartos et al. (2016) [bartos2016] and Auffhammer et al. (2017) [auffhammer2017].

```math
m(T)=1+\beta\,\max\left(0,\;T-T_0\right)
```

**Eq. 3 — per-unit transformer load** (C-P1.Kd $`K_d`$, C-P1.Td $`T_d`$). $`L^d_s`$ is the design load (assumption A-P3). The rated load is $`L^r_s=L^d_s/K_d`$, so $`K=K_d`$ at the design temperature. $`\Delta L_s(t-1)`$ is the load transferred in the previous hour (Eq. 8).

```math
L_s(t)=L^d_s\,\frac{m\big(T(t)\big)}{m(T_d)},\qquad
K_s(t)=\frac{L_s(t)+\Delta L_s(t-1)}{L^r_s}
```

**Eq. 4 — ultimate top-oil rise** (C-P2.dTOR $`\Delta\theta_{TO,R}`$, C-P2.R $`R`$, C-P2.n $`n`$), IEEE C57.91 [ieee_c5791_2011]:

```math
\Delta\theta_{TO,U}(t)=\Delta\theta_{TO,R}\left[\frac{K_s(t)^2R+1}{R+1}\right]^{n}
```

**Eq. 5 — hot-spot gradient** (C-P2.dHR $`\Delta\theta_{H,R}`$, C-P2.m $`m`$), IEEE C57.91. The winding time constant (minutes) is neglected at hourly steps.

```math
\Delta\theta_{H}(t)=\Delta\theta_{H,R}\,K_s(t)^{2m}
```

**Eq. 6 — top-oil lag and hot-spot temperature** (C-P2.tau $`\tau_{TO}`$). This is the first-order exponential response of IEEE C57.91 Clause 7.

```math
\Delta\theta_{TO}(t)=\Delta\theta_{TO}(t-1)+\left[\Delta\theta_{TO,U}(t)-\Delta\theta_{TO}(t-1)\right]\left(1-e^{-\Delta t/\tau_{TO}}\right),\qquad
\theta_H(t)=\theta_A(t)+\Delta\theta_{TO}(t)+\Delta\theta_H(t)
```

**Eq. 7 — hourly thermal failure** (C-P3 $`\theta_{50}`$, C-P3.sigma $`\sigma`$). Normal (probit) fragility in hot-spot temperature; fragility-curve form after Shinozuka et al. (2000) [shinozuka2000]. An in-service station fails in hour $`t`$ with probability

```math
p_s(t)=\Phi\!\left(\frac{\theta_H(t)-\theta_{50}}{\sigma}\right),\qquad X_s(t)\sim\mathrm{Bernoulli}\big(p_s(t)\big)
```

**Eq. 8 — load redistribution and overload trips** (C-P4 $`\alpha`$), after Motter & Lai (2002) [motter2002]. The capacity is $`C_s=(1+\alpha)L^d_s`$. Let $`D`$ be the set of stations down and $`N_s`$ the load-transfer peers of $`s`$ (R-P1 equal-voltage pairs). The load of each down station is shared equally among its peers that are still up:

```math
\Delta L_j(t)=\sum_{f\in D\cap N_j}\frac{L_f(t)}{|N_f\setminus D|},\qquad
\text{station } j\notin D \text{ trips if } L_j(t)+\Delta L_j(t)>C_j
```

If a down station has no peer still up, its load is not transferred and its customers are out.

**Eq. 9 — supply dependency** (C-P5), the functional dependency of Buldyrev et al. (2010). $`U(s)`$ is the set of supply edges into $`s`$ (redundant gate). $`F_s`$ means the station has failed, by Eq. 7 or Eq. 8, and $`e_s`$ means it is energised. The equation is iterated to a fixed point:

```math
e_s=\neg F_s\;\wedge\;\Big(U(s)=\varnothing\;\vee\;\bigvee_{u\in U(s)}e_u\Big)
```

Stations with $`U(s)=\varnothing`$ are fed by the external grid (A-P1). Eq. 8 and Eq. 9 are repeated within the hour until no new station fails (at most 40 rounds).

**Eq. 10 — restoration** (C-P6 $`R_h`$). A station that fails by Eq. 7 or Eq. 8 stays failed for $`R_h`$ hours. A station that is only de-energised (Eq. 9) returns as soon as one of its suppliers does.

### Stage B — downstream systems

**Eq. 11 — facilities, signals.** A zone is down when its substation is down: $`d_z(t)=\neg e_{s(z)}(t)`$. For assets with backup power (hospitals C-H1, nursing homes C-H2, water works C-W2), a backup failure $`B_f\sim\mathrm{Bernoulli}(p^{bf})`$ is drawn at the start of each outage episode:

```math
y_f(t)=d_{z(f)}(t)\wedge B_f
```

Dialysis facilities (C-H3) are series assets with no backup assumed: $`y_f(t)=d_{z(f)}(t)\vee w^{out}(t)`$ [kelman2015]. A signal $`g`$ goes dark when $`d_{z(g)}(t)\wedge NB_g`$, where $`NB_g\sim\mathrm{Bernoulli}(p^{nb})`$ is drawn once per run (C-T2).

**Eq. 13 — water.** Production is lost when every water works has lost power: $`W(t)=\bigwedge_k y_k(t)`$. Storage $`S(t)`$, starting at $`h_s`$ hours (C-W3), drains while production is lost:

```math
S(t)=\begin{cases}S(t-1)-1 & W(t)\\ h_s & \neg W(t)\end{cases},\qquad w^{out}(t)=W(t)\wedge S(t)<0
```

**Eq. 14 — population and compound exposure** (C-POP1, C-POP2 $`T_{heat}`$). The zone population is obtained by areal weighting of the ZCTA counts, $`\mathrm{pop}_z=\sum_c \mathrm{pop}_c\,|c\cap z|/|c|`$. Then

```math
\mathrm{Pop}^{out}(t)=\sum_z \mathrm{pop}_z\,d_z(t),\qquad
E^{c}=\sum_t \mathrm{Pop}^{out}(t)\;\mathbf{1}\big[\theta_A(t)\ge T_{heat}\big]\quad\text{(person-hours)}
```

The same sums are formed for the population aged 65+ and the population below the poverty line. Health risk modifiers are kept as context only and are not multiplied into a mortality baseline in v0:
- non-accidental mortality RR = 1.25 (1.12–1.41) during the 2003 New York blackout (C-H4) [anderson2012];
- heat-related mortality "more than double" when a multiday blackout coincides with a heat wave (C-H5) [stone2023].

**Eq. 15 — pavement heat distress** (C-T1 $`x_{50}`$, C-T1.sigma $`\sigma_T`$). PG binder grading uses the 7-day average maximum pavement temperature (AASHTO M 320 [aashto_m320]); grade selection under warming is discussed by Underwood et al. (2017) [underwood2017]. The model uses the closest quantity the LST record supports. Daily maxima of $`\mathrm{LST}^{\max}_i`$ are taken over the `ok` frames; $`T7_i`$ is the largest 7-day running mean of those daily maxima, requiring at least 5 days with data in the window. The median $`x_{50}`$ sits at the high-temperature grade of a PG 64 binder. LST is a skin temperature, whereas the PG definition refers to 20 mm depth, so $`T7_i`$ overstates the pavement temperature (assumption A-D3).

```math
d_{i,k}=\max_{t\in\mathrm{day}\,k}\mathrm{LST}^{\max}_i(t),\qquad
T7_i=\max_{k}\frac{1}{7}\sum_{j=k-6}^{k}d_{i,j},\qquad
p_i=\Phi\!\left(\frac{T7_i-x_{50}}{\sigma_T}\right)
```

**Eq. 16 — road control degraded** (C-T3). $`G(i)`$ is the set of signals on segment $`i`$:

```math
\mathrm{deg}_i(t)=\bigvee_{g\in G(i)}\mathrm{dark}_g(t)
```

### Stage C — uncertainty

**Eq. 12 — parameter sampling.** For run $`r=1\ldots N`$, each parameter $`k`$ is drawn independently from a triangular distribution on its low / mid / high values, so the Monte Carlo output combines parameter uncertainty and the Bernoulli draws of Eq. 7 and Eq. 11. A second batch with every parameter at its mid value isolates the Bernoulli part alone.

```math
\theta_k^{(r)}\sim\mathrm{Tri}\left(a=\theta_k^{low},\;c=\theta_k^{mid},\;b=\theta_k^{high}\right)
```

Scenarios add $`\delta\in\{0,+2,+4\}`$ °C to $`\theta_A(t)`$. The same random-number stream is used in every scenario (common random numbers), so differences between scenarios come from temperature only.

**Sensitivity.** Spearman rank correlation between each sampled power-model parameter $`\theta_k^{(r)}`$ and the season totals of run $`r`$ (person-hours without power, compound person-hours, thermal failures, overload trips). The cascade amplification of a run is the number of overload trips per thermal failure.

### Stage D — validation

**Eq. 17 — metrics.** Spearman ρ, with a 95% interval from a day-block bootstrap (500 resamples of whole days, which keeps within-day autocorrelation). For ranking scores against binary outcomes:

```math
\mathrm{AUC}=\frac{U}{n_1 n_0}=\Pr\big(\text{score of a segment with a request} > \text{score of a segment without}\big)
```

The stratified AUC is the positive-weighted mean of the AUCs computed within quintiles of a confounder (here segment length).

**Eq. 18 — outage comparison.** The model's expected population without power, $`\hat Y(t)=\mathbb{E}_r[\mathrm{Pop}^{out}(t)]`$, is compared with the EAGLE-I customers out $`Y(t)`$ over all hours, and over non-storm hours (no ASOS thunder report within ±3 h).

---

## 5. Simulation procedure

For every run $`r`$ (vectorised over $`N`$ runs) and every hour $`t`$:

1. Compute $`L_s(t)`$ and $`K_s(t)`$ (Eq. 2–3), update $`\Delta\theta_{TO}`$ and $`\theta_H`$ (Eq. 4–6).
2. Draw thermal failures among in-service stations (Eq. 7); failed stations get $`R_h`$ repair hours (Eq. 10).
3. Repeat until stable: energisation fixed point (Eq. 9), then load transfer (Eq. 8) and overload trips.
4. Derive zone states and facility, water, signal and road states (Eq. 11, 13, 16), and accumulate population exposure (Eq. 14).
5. Decrement repair counters.

The pavement module (Eq. 15) runs separately on the LST period. Outputs are written to `data/standard/results/<run_id>/` (run manifest with every parameter draw, hourly substation states, pavement table) and `site/data/twin/results/` (viewer files).

---

## 6. Parameters

All parameters live in [`twin/couplings.csv`](../twin/couplings.csv) and are loaded into the `couplings` standard table. Every row records its basis and citation; the evidence column quotes the abstract wherever a number comes from a paper.

The basis column takes one of four values:
- **literature**: a number or relationship from a peer-reviewed paper;
- **standard**: an IEEE or AASHTO standard (values marked "typical" must still be confirmed against unit data);
- **internal**: an analysis in the cascading-heat project;
- **assumption**: a placeholder with no source (`citation = assumption`).

| Id | Parameter | Low / mid / high | Units | Basis | Source |
| --- | --- | --- | --- | --- | --- |
| C-P1 | load slope β | 0.0166 / 0.0238 / 0.0381 | per °F | internal | [cascadingheat2026]; cf. [bartos2016], [auffhammer2017] |
| C-P1.T0 | threshold $`T_0`$ | 75 | °F | internal | [cascadingheat2026] |
| C-P1.Kd | design loading $`K_d`$ | 0.70 / 0.85 / 1.00 | p.u. | assumption | — |
| C-P1.Td | design temperature $`T_d`$ | 93 / 95 / 97 | °F | assumption | — |
| C-P2.dTOR | rated top-oil rise | 50 / 55 / 60 | K | standard (typical) | [ieee_c5791_2011] |
| C-P2.dHR | rated hot-spot gradient | 20 / 25 / 30 | K | standard (typical) | [ieee_c5791_2011] |
| C-P2.R | load / no-load loss ratio | 3.0 / 4.5 / 6.0 | — | standard (typical) | [ieee_c5791_2011] |
| C-P2.n, C-P2.m | oil / winding exponents | 0.8 | — | standard (ONAN) | [ieee_c5791_2011] |
| C-P2.tau | top-oil time constant | 2 / 3 / 4 | h | standard (typical) | [ieee_c5791_2011] |
| C-P3 | fragility median $`\theta_{50}`$ | 130 / 140 / 150 | °C | assumption | anchored on C57.91 hot-spot guidance (to be confirmed); form [shinozuka2000] |
| C-P3.sigma | fragility dispersion | 5 / 8 / 12 | K | assumption | [shinozuka2000] |
| C-P4 | tolerance α | 0.15 / 0.35 / 1.45 | — | internal | [motter2002]; thresholds 1.15 / 1.35 / 2.45 from [cascadingheat2026] |
| C-P5 | supply dependency | 1 | — | literature | [buldyrev2010], [rinaldi2001] |
| C-P6 | repair duration | 4 / 8 / 24 | h | assumption | — |
| C-H1 | hospital backup fails on demand | 0.02 / 0.05 / 0.15 | — | assumption | requirement: [cms2016] |
| C-H2 | nursing-home backup fails | 0.10 / 0.30 / 0.50 | — | assumption | requirement: [cms2016] |
| C-H3 | dialysis series dependency | 1 | — | literature | [kelman2015] |
| C-H4 | outage RR, non-accidental mortality | 1.12 / 1.25 / 1.41 | — | literature (context) | [anderson2012] |
| C-H5 | heat + blackout amplification | ≥ 2 | — | literature (context) | [stone2023] |
| C-W1 | redundant production | 1 | — | literature | [rinaldi2001], [klise2017] |
| C-W2 | plant backup fails | 0.05 / 0.15 / 0.30 | — | assumption | — |
| C-W3 | storage | 6 / 12 / 24 | h | assumption | — |
| C-T1 | pavement fragility median | 60 / 64 / 70 | °C | standard | [aashto_m320], [underwood2017] |
| C-T1.sigma | pavement dispersion | 3 / 5 / 8 | K | assumption | [shinozuka2000] |
| C-T2 | signals without battery | 0.50 / 0.75 / 1.00 | — | assumption | — |
| C-T3 | signal → road | 1 | — | literature | [rinaldi2001] |
| C-T4, C-A1 | bridge / access links | 0 (not propagated) | — | — | [ouyang2014] |
| C-POP1 | zone → population | 1 | — | literature | [stone2023] |
| C-POP2 | compound-exposure threshold | 30 / 32 / 35 | °C | assumption | context [gasparrini2015] |

**Evidence quotes (from abstracts).**
- Bartos et al. (2016): "by mid-century (2040–2060), increases in ambient air temperature may reduce average summertime transmission capacity by 1.9%–5.8% … peak per-capita summertime loads may rise by 4.2%–15% on average due to increases in ambient air temperature."
- Anderson & Bell (2012): "During the blackout, mortality increased for accidental deaths (122% [95% confidence interval = 28%-287%]) and nonaccidental (ie, disease-related) deaths (25% [12%-41%])."
- Stone et al. (2023): "We find the concurrence of a multiday blackout event with heat wave conditions to more than double the estimated rate of heat-related mortality across all three cities."
- Underwood et al. (2017): "Over the past 20 years, stationary assumptions have resulted in incorrect material selection for 35% of 799 observed locations."
- Buldyrev et al. (2010): "failure of nodes in one network may lead to failure of dependent nodes in other networks. This may happen recursively and can lead to a cascade of failures."
- Hines et al. (2010), a caution that applies to this model: "evaluating vulnerability in power networks using purely topological metrics can be misleading."

---

## 7. Validation design

| Check | Observation | Model quantity | Why it matters |
| --- | --- | --- | --- |
| V1 | EAGLE-I customers out (county, hourly) | $`\hat Y(t)`$ (Eq. 18) | Does modelled heat-driven outage track observed outages? |
| V2 | Same, non-storm hours only | Same | Most large outages are storm-driven; heat effects should show here if anywhere. |
| V3 | EAGLE-I vs air temperature, non-storm hours (no model) | — | A data-only test of whether heat and outages co-vary in Nashville. |
| V4 | 311 pavement requests matched to segments (LST period) | $`p_i`$ and $`T7_i`$ (Eq. 15) | Do hotter segments receive more pavement requests? |
| V5 | V4 with a segment-length baseline and length-stratified AUC | — | Long segments are both hotter on average and more likely to receive a request; the length baseline separates the two. |

EAGLE-I covers the whole county while the model covers the downtown AOI, so V1 and V2 compare rankings (Spearman), not magnitudes.

---

## 8. Limitations and next steps

- **Topology.** The power graph is inferred from OSM. Feeder boundaries, switch states, transformer ratings and loads are unknown. Following Hines et al. (2010), the graph should not be read as an engineering model of the NES system.
- **Load.** A monthly-sales slope is applied hourly (A-P4); diurnal load shape, humidity and the 2023 customer mix are not represented.
- **Fragility.** No measured heat fragility exists for these substations. Results in the observed-2023 scenario are dominated by the tails of the placeholder ranges (see the sensitivity ranking in [`RESULTS.md`](RESULTS.md)).
- **Water.** There are no hydraulics: water service is a storage-buffered logical state.
- **Transport.** Signal outages degrade segments but traffic is not routed; bridges and facility access are recorded but not propagated.
- **Observation mismatch.** EAGLE-I is county-level and dominated by storms; 311 requests reflect reporting behaviour as well as damage.
- **Heat wave choice.** The NOAA daily maxima show that 2023-07-11 – 07-21 (the earlier "heat window") peaked at 89–92 °F. The hottest 2023 spells (≥ 95 °F for three or more days) were 07-27 – 07-29 and 08-21 – 08-26, which the hourly LST does not cover. The power module uses the whole summer; the pavement module is limited to the LST period.

Next steps, in order:
1. NES transformer ratings, feeder maps and restoration records (C-P1.Kd, C-P3, R-P3, C-P6).
2. Hourly LST for 2023-07-27 – 08-26.
3. A WNTR model of the Metro Water network.
4. Calibration of C-P3 against EAGLE-I on non-storm hot hours.

---

## 9. Reproducibility

```bash
python scripts/fetch_open_data.py          # OSM + ASOS into raw/ (logged in raw/open_data_manifest.json)
python -m pipeline.build                   # standard tables, dependency graph, validation
python -m pipeline.cascade --runs 2000 --mid-runs 500 --seed 20261027 --scenarios 0,2,4
python -m pipeline.report                  # writes docs/RESULTS.md from the latest run
```

Every build writes `data/standard/runs/<build run_id>.json` (code version, config hash, dataset fingerprints, input sha256). Every cascade run writes `data/standard/results/<cascade run_id>/run.json`, which records the seed, the number of runs, every parameter draw, the couplings hash and the build run it used.

---

## 10. References

DOIs were checked against Crossref / DataCite on 2026-10-27; full entries are in [`twin/references.yaml`](../twin/references.yaml).

- [aashto_m320] AASHTO. M 320: Standard Specification for Performance-Graded Asphalt Binder. American Association of State Highway and Transportation Officials. (Standard; edition to be fixed when the TDOT binder grade is confirmed.)
- [acs2020] U.S. Census Bureau. 2020 ZCTA cartographic boundaries and American Community Survey 5-year estimates.
- [anderson2012] Anderson, G. B., & Bell, M. L. (2012). Lights out: Impact of the August 2003 power outage on mortality in New York, NY. *Epidemiology, 23*(2), 189–193. https://doi.org/10.1097/EDE.0b013e318245c61c
- [auffhammer2017] Auffhammer, M., Baylis, P., & Hausman, C. H. (2017). Climate change is projected to have severe impacts on the frequency and intensity of peak electricity demand across the United States. *PNAS, 114*(8), 1886–1891. https://doi.org/10.1073/pnas.1613193114
- [bartos2016] Bartos, M., Chester, M., Johnson, N., Gorman, B., Eisenberg, D., Linkov, I., & Bates, M. (2016). Impacts of rising air temperatures on electric transmission ampacity and peak electricity load in the United States. *Environmental Research Letters, 11*(11), 114008. https://doi.org/10.1088/1748-9326/11/11/114008
- [buldyrev2010] Buldyrev, S. V., Parshani, R., Paul, G., Stanley, H. E., & Havlin, S. (2010). Catastrophic cascade of failures in interdependent networks. *Nature, 464*(7291), 1025–1028. https://doi.org/10.1038/nature08932
- [cascadingheat2026] Vanderbilt Data Science Institute (2026). *cascading-heat* (private repository, main @ 001cd56): `temp_energy_sale_model.ipynb` and simulation results; data inventory compiled 2026-10-02.
- [cms2016] Centers for Medicare & Medicaid Services (2016). Medicare and Medicaid Programs; Emergency Preparedness Requirements for Medicare and Medicaid Participating Providers and Suppliers. *Federal Register, 81*(180), 63860–64044.
- [cms_provider] Centers for Medicare & Medicaid Services. Provider Data Catalog (hospitals, dialysis facilities, nursing homes).
- [eaglei2023] Tansakul, V., Myers, A., Tennille, S., et al. (2023). *EAGLE-I Power Outage Data 2014–2022* [Data set]. Oak Ridge National Laboratory. https://doi.org/10.13139/ORNLNCCS/1975202 (the 2023 file is from the same series).
- [gasparrini2015] Gasparrini, A., Guo, Y., Hashizume, M., et al. (2015). Mortality risk attributable to high and low ambient temperature: a multicountry observational study. *The Lancet, 386*(9991), 369–375. https://doi.org/10.1016/S0140-6736(14)62114-0
- [hines2010] Hines, P., Cotilla-Sanchez, E., & Blumsack, S. (2010). Do topological models provide good information about electricity infrastructure vulnerability? *Chaos, 20*(3), 033122. https://doi.org/10.1063/1.3489887
- [hub311] Metro Nashville (2023). hubNashville 311 Service Requests. Nashville Open Data.
- [ieee_c5791_2011] IEEE (2012). *IEEE Guide for Loading Mineral-Oil-Immersed Transformers and Step-Voltage Regulators* (IEEE Std C57.91-2011). https://doi.org/10.1109/IEEESTD.2012.6166928
- [iem_asos] Iowa Environmental Mesonet. ASOS archive, station BNA, retrieved 2026-10-27.
- [kelman2015] Kelman, J., Finne, K., Bogdanov, A., Worrall, C., Margolis, G., Rising, K., MaCurdy, T. E., & Lurie, N. (2015). Dialysis care and death following Hurricane Sandy. *American Journal of Kidney Diseases, 65*(1), 109–115. https://doi.org/10.1053/j.ajkd.2014.07.005
- [klise2017] Klise, K. A., Bynum, M., Moriarty, D., & Murray, R. (2017). A software framework for assessing the resilience of drinking water systems to disasters with an example earthquake case study. *Environmental Modelling & Software, 95*, 420–431. https://doi.org/10.1016/j.envsoft.2017.06.022
- [motter2002] Motter, A. E., & Lai, Y.-C. (2002). Cascade-based attacks on complex networks. *Physical Review E, 66*(6), 065102. https://doi.org/10.1103/PhysRevE.66.065102
- [okabe2000] Okabe, A., Boots, B., Sugihara, K., & Chiu, S. N. (2000). *Spatial Tessellations: Concepts and Applications of Voronoi Diagrams* (2nd ed.). Wiley. https://doi.org/10.1002/9780470317013
- [osm2026] OpenStreetMap contributors (2026). OpenStreetMap data via the Overpass API, retrieved 2026-10-27. ODbL 1.0.
- [ouyang2014] Ouyang, M. (2014). Review on modeling and simulation of interdependent critical infrastructure systems. *Reliability Engineering & System Safety, 121*, 43–60. https://doi.org/10.1016/j.ress.2013.06.040
- [rinaldi2001] Rinaldi, S. M., Peerenboom, J. P., & Kelly, T. K. (2001). Identifying, understanding, and analyzing critical infrastructure interdependencies. *IEEE Control Systems Magazine, 21*(6), 11–25. https://doi.org/10.1109/37.969131
- [shinozuka2000] Shinozuka, M., Feng, M. Q., Lee, J., & Naganuma, T. (2000). Statistical analysis of fragility curves. *Journal of Engineering Mechanics, 126*(12), 1224–1231. https://doi.org/10.1061/(ASCE)0733-9399(2000)126:12(1224)
- [stone2023] Stone, B., Gronlund, C. J., Mallen, E., et al. (2023). How blackouts during heat waves amplify mortality and morbidity risk. *Environmental Science & Technology, 57*(22), 8245–8255. https://doi.org/10.1021/acs.est.2c09588
- [tdot_bridges] Tennessee Department of Transportation (2022). Bridge Condition Annual, Davidson County.
- [underwood2017] Underwood, B. S., Guido, Z., Gudipudi, P., & Feinberg, Y. (2017). Increased costs to US pavement infrastructure from future temperature rise. *Nature Climate Change, 7*(10), 704–707. https://doi.org/10.1038/nclimate3390
