# Results — heat-cascade model v0

Generated from cascade run `cascade-20261104T183107Z-e8e2407fbb` (build `20261104T182412Z-20960c7c`, code `git:d73a39d-dirty`, seed 20261027, 2,000 Monte Carlo runs per scenario plus 500 runs at mid parameters). Period 2023-06-01 – 2023-08-31, 2,208 hours. Methods: [HANDBOOK.md](HANDBOOK.md).

> These are preliminary results from a model with placeholder links and parameters (HANDBOOK §3.4). They show how the coupled system responds under stated assumptions; they are not estimates of actual outages.

## 1. Network

| Element | Count |
| --- | --- |
| Substations (OSM, AOI + 4 km) | 78 |
| Service zones (placeholder) | 40 |
| Supply edges | 127 |
| Load-transfer peer pairs | 38 |
| Hospitals | 6 |
| Nursing homes | 4 |
| Dialysis facilities | 5 |
| Water works | 3 |
| Traffic signals | 422 |
| Road segments with a signal | 607 |
| Population in service zones | 115,203 (age 65+: 10,873) |

## 2. Scenarios (season totals, Jun–Aug)

Mean over runs, with the 95th percentile in brackets. Scenarios add a uniform offset to the observed 2023 air temperature.

| Scenario | Peak air temp. | Runs with any failure | Thermal failures | Overload trips | Trips per thermal failure | Person-hours without power | Compound heat–outage person-hours | Dialysis facility-hours down |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023 observed | 36.7 °C | 15.0% | 1.7 [6] | 5.2 [12] | 0.41 | 142,118 [381,649] | 48,136 [194,275] | 8.9 |
| +2 °C | 38.7 °C | 37.4% | 14.2 [85] | 49.6 [214] | 1.20 | 1,350,404 [6,473,522] | 507,455 [3,157,990] | 88.0 |
| +4 °C | 40.7 °C | 65.9% | 74.5 [411] | 264.6 [1,554] | 4.35 | 6,629,059 [38,198,571] | 2,973,064 [15,633,809] | 419.2 |

With every parameter at its mid value (observed 2023), the mean is 0.00 thermal failures and 0 person-hours without power. Most of the risk in the full Monte Carlo therefore comes from the tails of the parameter ranges, not from the Bernoulli draws.

## 3. Sensitivity (observed 2023 scenario)

Spearman ρ between each sampled parameter and the season totals of a run. Sorted by |ρ| with person-hours without power.

| Parameter | Name | Basis | ρ person-hours | ρ compound person-hours | ρ thermal failures | ρ overload trips |
| --- | --- | --- | --- | --- | --- | --- |
| `C-P1.Kd` | K_design | assumption | 0.43 | 0.43 | 0.45 | 0.40 |
| `C-P3.sigma` | sigma | assumption | 0.29 | 0.29 | 0.31 | 0.26 |
| `C-P3` | theta_50 | assumption | -0.22 | -0.22 | -0.22 | -0.20 |
| `C-P2.dTOR` | dTheta_TO_R | standard | 0.12 | 0.12 | 0.12 | 0.12 |
| `C-P2.dHR` | dTheta_H_R | standard | 0.11 | 0.11 | 0.10 | 0.10 |
| `C-P1.Td` | T_design | assumption | -0.06 | -0.06 | -0.05 | -0.05 |
| `C-P2.tau` | tau_TO | standard | -0.05 | -0.05 | -0.06 | -0.04 |
| `C-P6` | repair_hours | internal | 0.04 | 0.04 | 0.03 | 0.02 |
| `C-POP2` | T_heat | assumption | 0.04 | 0.03 | 0.03 | 0.03 |
| `C-P9.imp` | P_imp | literature | -0.04 | -0.04 | -0.05 | -0.04 |
| `C-H2` | p_backup_fail | literature | -0.03 | -0.03 | -0.04 | -0.04 |
| `C-P2.R` | R | standard | -0.03 | -0.03 | -0.03 | -0.03 |
| `C-P9.avail` | a | literature | 0.03 | 0.02 | 0.03 | 0.03 |
| `C-T2` | p_no_battery | literature | -0.02 | -0.02 | -0.02 | -0.03 |
| `C-P9.flow` | f_low | assumption | -0.01 | -0.01 | -0.01 | -0.02 |
| `C-W3` | storage_hours | internal | 0.01 | 0.01 | 0.00 | 0.02 |
| `C-P9.span` | span | assumption | -0.01 | -0.01 | -0.00 | -0.00 |
| `C-P9.Qmin` | Q_min | assumption | -0.01 | -0.01 | -0.01 | -0.01 |
| `C-H1` | p_backup_fail | literature | 0.01 | 0.01 | 0.01 | 0.00 |
| `C-P1` | beta | internal | 0.00 | 0.00 | -0.00 | -0.00 |
| `C-W2` | p_backup_fail | literature | -0.00 | -0.00 | -0.00 | 0.01 |
| `C-P4` | alpha | internal | 0.00 | -0.00 | 0.01 | -0.00 |
| `C-P9` | T_lim | assumption | 0.00 | 0.00 | 0.01 | 0.01 |

## 4. Validation

| Check | Result |
| --- | --- |
| V1 Model vs EAGLE-I, all hours (Spearman ρ, 95% day-block CI) | -0.04 [-0.14, 0.07] (n = 2,208 h, 92 days) |
| V2 Model vs EAGLE-I, non-storm hours | -0.05 [-0.15, 0.05] (n = 1,994 h, 92 days) |
| V3 Air temperature vs EAGLE-I, non-storm hours (data only) | 0.19 [0.10, 0.28] (n = 1,994 h, 92 days) |
| V3 Daily max air temperature vs daily max outages (data only) | 0.22 [0.02, 0.42] (n = 92 days) |
| Model daily max vs observed daily max | 0.10 [-0.11, 0.32] (n = 92 days) |
| V4 Pavement requests (2023-07-01 – 2023-07-21, 71 of 4,137 segments): AUC of P(T7 > x50) (Eq. 15) | 0.746 |
| V4 Same, T7 itself / single-day peak LST | 0.746 / 0.744 |
| V5 Same, segment length only (baseline) | 0.808 |
| V5 Same, T7 within segment-length quintiles | 0.641 |
| V4 All road requests (pavement + other road), LST period, 341 segments | 0.703 (length only 0.787; within length quintiles 0.608) |
| V4 Pavement requests, Jun–Aug (233 segments) | 0.664 (length only 0.759; within length quintiles 0.576) |

Observed customers out (Davidson County, EAGLE-I) on non-storm hours, by air temperature:

| Air temperature | Hours | Median | 90th percentile | Share of hours > 1,000 customers |
| --- | --- | --- | --- | --- |
| (20, 24] °C | 559 | 11 | 564 | 8.8% |
| (24, 28] °C | 630 | 13 | 710 | 6.5% |
| (28, 30] °C | 262 | 17 | 339 | 4.6% |
| (30, 32] °C | 166 | 16 | 552 | 7.8% |
| (32, 34] °C | 119 | 17 | 619 | 4.2% |
| (34, 36] °C | 40 | 46 | 238 | 7.5% |
| (36, 40] °C | 14 | 44 | 242 | 0.0% |

## 5. Substations with the highest expected outage hours (observed 2023)

| Substation | Type | Max kV | Expected hours down | Peak mean hot-spot (°C) |
| --- | --- | --- | --- | --- |
| Green Hills Substation | distribution | 69.0 | 2.28 | 104.7 |
| Battlefield Substation | distribution | 69.0 | 2.23 | 104.5 |
| Edgehill Substation | distribution | 69.0 | 2.23 | 102.9 |
| Harding Pike Substation | minor_distribution | 23.9 | 2.20 | 103.5 |
| Peabody Substation | distribution | 69.0 | 2.19 | 105.9 |
| Sharondale Substation | distribution | 69.0 | 2.17 | 103.4 |
| w207878703 | distribution | 69.0 | 2.16 | 98.1 |
| w1489136127 | minor_distribution | 23.9 | 2.16 | 100.8 |
| w207869586 | distribution | 69.0 | 2.16 | 103.8 |
| 11th Avenue Substation | — | 69.0 | 2.15 | 106.2 |

## 6. Pavement module

4,137 segments with hourly LST. Maximum 7-day running mean of daily-max LST (T7): 5th / 50th / 95th percentile 60.1 / 63.2 / 67.0 °C. Mean P(T7 > x50) = 0.424; 1,222 segments with P > 0.5.

## 7. Urban air-temperature field (M-6)

Regressions on the 2022 heat-mapping traverses (aggregated to 100 m cells, 1 km spatial-block cross-validation). Predictors: impervious share and forest share within 90 m and 510 m, water share within 990 m, distance to water, elevation and topographic position.

| Period | Anchor (local hour) | Cells | CV RMSE | Null RMSE | CV R² | Anomaly at BNA |
| --- | --- | --- | --- | --- | --- | --- |
| morning | 6.5 | 2,630 | 0.656 °C | 1.008 °C | 0.576 | +1.46 °C |
| afternoon | 15.5 | 2,104 | 0.585 °C | 0.668 °C | 0.232 | -0.01 °C |
| evening | 19.5 | 1,984 | 0.444 °C | 0.63 °C | 0.505 | +0.10 °C |

The traverse files carry no date. Closest BNA match: 2022-08-14 (RMSE 1.03 °C over the three periods); next 2022-06-29, 2022-07-14. To be confirmed with the campaign organisers.

Substation temperature offsets relative to BNA: -3.03 to 0.85 °C (mean -0.61); zones -2.54 to 0.61 °C.

| Observed 2023, same random draws | Urban field (M-6) | BNA everywhere (A-D4) |
| --- | --- | --- |
| Thermal failures, mean | 1.7 | 1.8 |
| Overload trips, mean | 5.2 | 5.3 |
| Person-hours without power, mean | 142,118.4 | 147,730.4 |
| Compound person-hours, mean | 48,136.1 | 46,564.4 |

## 8. River temperature → thermal derating → system supply (M-18)

Stream temperature (Mohseni et al. 1998) fitted on 161 TDEC main-stem samples against the 7-day mean BNA air temperature: RMSE 2.38 °C, R² 0.86, upper asymptote 30.2 °C. Excluded: Clay County (CUMBE381.1CY) is cold tailwater below Wolf Creek Dam.

| Plant | Cooling | Summer capacity |
| --- | --- | --- |
| Cumberland (TN) (Stewart Co.) | ON (once-through) | 2,470 MW |
| Gallatin (TN) (Sumner Co.) | ON (once-through) | 1,556 MW |

TVA operable summer capacity 38,472 MW (EIA-860 2022).

| Summer | Max modelled river temp. | Min discharge | TVA peak demand |
| --- | --- | --- | --- |
| 2014 | 26.11 °C | 6,610 cfs | — MW |
| 2015 | 26.54 °C | 6,040 cfs | 29,041 MW |
| 2016 | 26.81 °C | 5,930 cfs | 29,751 MW |
| 2017 | 27.07 °C | 7,510 cfs | 29,845 MW |
| 2018 | 26.78 °C | 6,720 cfs | 28,764 MW |
| 2019 | 26.6 °C | 8,550 cfs | 29,568 MW |
| 2020 | 27.03 °C | 6,320 cfs | 28,926 MW |
| 2021 | 26.77 °C | 6,250 cfs | 30,340 MW |
| 2022 | 27.07 °C | 5,840 cfs | 31,617 MW |
| 2023 | 27.1 °C | 4,420 cfs | 31,846 MW |
| 2024 | 27.1 °C | 5,710 cfs | 30,926 MW |
| 2025 | 27.32 °C | 6,090 cfs | 32,126 MW |

| Scenario | Runs with any system shed | Mean shed hours | Mean peak derate | Mean derate hours |
| --- | --- | --- | --- | --- |
| +0 °C | 0.0% | 0.0 | 192 MW | 4.42 |
| +2 °C | 0.0% | 0.0 | 192 MW | 4.42 |
| +4 °C | 4.2% | 0.23 | 192 MW | 4.42 |

Shed in the warming scenarios comes from TVA demand rising with the C-P1 load slope against a placeholder supply margin (C-P9.avail, C-P9.imp), not from river derating. Section 10 rejects parameter sets that shed load in an observed summer.

## 9. Network access (M-28 / M-29)

Road network from TIGER segments in the AOI: 12,526 edges, 9,332 nodes, 97.8% of nodes in the main component. HPMS 2024 AADT matched to 25.9% of edges (24.5% of length); the rest use class defaults. Hourly profile from TMAS weekdays. 115,203 residents in 1,585 cells of 250 m; 32.8% of edges are signal-controlled.

Population-weighted travel time to the nearest available facility (minutes; 90th percentile in brackets).

| Condition | Local hour | Expected degraded segments | Hospital | Dialysis | Fire / EMS | Share > 8 min to EMS |
| --- | --- | --- | --- | --- | --- | --- |
| night | 3 | — | 3.96 [7.93] (6 open) | 3.72 [6.22] (5 open) | 2.84 [4.46] (7 open) | 0.0% |
| am_peak | 8 | — | 3.98 [7.97] (6 open) | 3.73 [6.24] (5 open) | 2.85 [4.48] (7 open) | 0.0% |
| pm_peak | 17 | — | 3.99 [7.99] (6 open) | 3.74 [6.25] (5 open) | 2.86 [4.48] (7 open) | 0.0% |
| all_signals_dark_pm | 17 | — | 4.14 [8.31] (6 open) | 3.81 [6.42] (5 open) | 2.95 [4.65] (7 open) | 0.0% |
| stress_+0 | 18 | 15.1 | 3.98 [7.97] (6 open) | 3.73 [6.24] (5 open) | 2.85 [4.48] (7 open) | 0.0% |
| stress_+2 | 18 | 73.0 | 3.98 [7.98] (6 open) | 3.73 [6.25] (5 open) | 2.85 [4.48] (7 open) | 0.0% |
| stress_+4 | 18 | 198.0 | 3.99 [7.99] (6 open) | 3.74 [6.26] (5 open) | 2.86 [4.49] (7 open) | 0.0% |

Stress conditions use expected capacity, 1 − (1 − φ_dark)·P(signal dark), and drop facilities with P(down) ≥ 0.5. `all_signals_dark_pm` is an upper bound: every signal-controlled link at φ_dark in the evening peak.

## 10. Multi-year calibration against EAGLE-I (M-43)

Run `calibration-20261030T213618Z-45a0e28623`: summers 2015–2025, 2,000 prior runs (same parameter draws every year). Years left out for EAGLE-I coverage (background < 100 customers): 2018. 0 runs rejected because they shed TVA load in an observed summer (A-C3).

**Summary statistic (ABC).** S = mean daily max customers out, hot (Tmax >= 35 C) minus cool (< 32 C) non-storm days. Observed S = **693 ± 429** customers (93 hot and 329 cool days). The prior runs give S = 0 / 0 / 27,407 (5th / 50th / 95th percentile); 78.6% of runs lie within 2 SE of the observation. Weights w ∝ exp(−(S_r − S_obs)² / 2 SE²) give an effective sample size of **1441.8** and a posterior mean S of 77.

Diagnostic: the full daily negative-binomial likelihood collapses onto a few runs (ESS 1.4, largest weight 0.8558), so it is not used for the posterior.

| Summer | Non-storm days | Hot non-storm days (Tmax ≥ 35 °C) | Background (customers) | NB shape k | Max observed | Model mean on hot days |
| --- | --- | --- | --- | --- | --- | --- |
| 2015 | 71 | 2 | 876 | 0.561 | 30,336 | 2,044 |
| 2016 | 56 | 9 | 814 | 0.5 | 6,835 | 2,184 |
| 2017 | 69 | 5 | 820 | 0.371 | 10,955 | 2,639 |
| 2018 | 60 | 6 | 4 | 50.0 | 12 | 2,878 |
| 2019 | 59 | 6 | 1,246 | 0.861 | 5,307 | 1,599 |
| 2020 | 56 | 2 | 855 | 0.653 | 4,276 | 3,885 |
| 2021 | 74 | 8 | 1,575 | 0.788 | 8,260 | 2,205 |
| 2022 | 69 | 15 | 901 | 0.394 | 6,120 | 7,360 |
| 2023 | 63 | 6 | 1,562 | 0.395 | 20,111 | 6,728 |
| 2024 | 80 | 24 | 1,421 | 0.589 | 7,342 | 8,453 |
| 2025 | 70 | 16 | 1,391 | 0.559 | 11,130 | 4,638 |

| Parameter | Basis | Prior 5 / 50 / 95 | Posterior 5 / 50 / 95 | Shift (prior SD) |
| --- | --- | --- | --- | --- |
| `C-P1.Kd` K_design | assumption | 0.7475 / 0.8481 / 0.9527 | 0.7422 / 0.8348 / 0.931 | -0.22 |
| `C-P3` theta_50 | assumption | 133.393 / 139.96 / 146.956 | 133.642 / 140.429 / 147.149 | +0.10 |
| `C-P3.sigma` sigma | assumption | 5.996 / 8.1939 / 10.7431 | 5.9314 / 8.04 / 10.6 | -0.10 |
| `C-P2.dTOR` dTheta_TO_R | standard | 51.6688 / 55.0304 / 58.4033 | 51.5637 / 54.9348 / 58.2193 | -0.07 |
| `C-P2.dHR` dTheta_H_R | standard | 21.625 / 25.0092 / 28.3105 | 21.5567 / 24.9047 / 28.2048 | -0.04 |
| `C-POP2` T_heat | assumption | 30.7631 / 32.2415 / 34.0585 | 30.7718 / 32.1847 / 34.0814 | -0.04 |
| `C-H2` p_backup_fail | assumption | 0.1632 / 0.2991 / 0.4394 | 0.1668 / 0.3013 / 0.4401 | +0.04 |
| `C-P1.Td` T_design | assumption | 93.636 / 94.984 / 96.359 | 93.6382 / 95.0099 / 96.4009 | +0.03 |
| `C-P6` repair_hours | assumption | 6.0854 / 11.6624 / 19.6721 | 6.0846 / 11.4701 / 19.7263 | -0.03 |
| `C-P9` T_lim | assumption | 29.716 / 31.0528 / 32.378 | 29.6839 / 31.0364 / 32.358 | -0.03 |
| `C-W2` p_backup_fail | assumption | 0.0872 / 0.1647 / 0.2573 | 0.0851 / 0.1624 / 0.2578 | -0.02 |
| `C-P2.tau` tau_TO | standard | 2.3073 / 3.0058 / 3.6966 | 2.3131 / 3.0091 / 3.6995 | +0.02 |
| `C-H1` p_backup_fail | assumption | 0.033 / 0.0677 / 0.1264 | 0.0322 / 0.0674 / 0.1261 | -0.02 |
| `C-P4` alpha | internal | 0.2727 / 0.5982 / 1.1817 | 0.278 / 0.6001 / 1.1767 | +0.01 |
| `C-P9.flow` f_low | assumption | 0.1573 / 0.2742 / 0.4321 | 0.1575 / 0.2735 / 0.4332 | +0.01 |
| `C-W3` storage_hours | assumption | 8.2917 / 13.7264 / 20.7413 | 8.301 / 13.7462 / 20.825 | +0.01 |
| `C-P9.span` span | assumption | 3.6698 / 5.2656 / 7.0886 | 3.6881 / 5.2578 / 7.1064 | +0.01 |
| `C-P9.avail` a | assumption | 0.8373 / 0.8764 / 0.9115 | 0.8373 / 0.876 / 0.9116 | -0.01 |
| `C-T2` p_no_battery | assumption | 0.5815 / 0.7497 / 0.9176 | 0.5866 / 0.7493 / 0.9187 | +0.01 |
| `C-P9.imp` P_imp | assumption | 515.911 / 1515.91 / 2564.06 | 498.826 / 1495.01 / 2564.76 | -0.01 |
| `C-P1` beta | internal | 0.0193 / 0.0257 / 0.0345 | 0.0192 / 0.0257 / 0.0345 | -0.01 |
| `C-P9.Qmin` Q_min | assumption | 3319.01 / 4006.34 / 4689.78 | 3319.05 / 4001.97 / 4686.25 | -0.00 |
| `C-P2.R` R | standard | 3.5247 / 4.4992 / 5.5095 | 3.5268 / 4.4973 / 5.5002 | -0.00 |

**Data only (no model).** Daily max air temperature vs daily max customers out on non-storm days, all summers pooled: -0.00 [-0.08, 0.06] (n = 667 days). Median daily max on hot days (≥ 35 °C, n = 93) 307 vs cool days (< 32 °C, n = 329) 395 customers; difference -88 [-258, 239].

| Daily max temperature | Days | Median | 90th percentile | Share of days > 1,000 customers |
| --- | --- | --- | --- | --- |
| (20, 28] °C | 59 | 417 | 3,580 | 30.5% |
| (28, 30] °C | 132 | 381 | 2,932 | 33.3% |
| (30, 32] °C | 137 | 364 | 3,642 | 32.8% |
| (32, 34] °C | 203 | 323 | 3,559 | 29.1% |
| (34, 36] °C | 102 | 383 | 3,629 | 29.4% |
| (36, 40] °C | 33 | 307 | 4,637 | 39.4% |

By-year Spearman ρ: 2015 -0.04, 2016 0.00, 2017 0.14, 2019 -0.27, 2020 0.04, 2021 -0.07, 2022 0.09, 2023 0.22, 2024 -0.10, 2025 -0.12.

## 11. Core skeleton model

Run `core-20261104T184037Z-e8e2407fbb`: 2,000 Monte Carlo runs per scenario, links K1, K2, K3, K4, K5, K6, K7, K8, K9; deferred D1, D2, D3, D5, D6, D7, D8. Selection and equations: [CORE_MODEL.md](CORE_MODEL.md). Population in zones 115,203 (65+ 10,873, below poverty 19,853).

| Output (mean per run) | +0 °C | +2 °C | +4 °C |
| --- | --- | --- | --- |
| Runs with any outage | 12.0% | 33.5% | 61.2% |
| Thermal failures (core) | 1.01 | 9.82 | 61.22 |
| Thermal failures + overload trips (full) | 6.85 | 63.84 | 339.12 |
| Person-hours without power (core) | 15,475 | 147,468 | 806,100 |
| Person-hours without power (full) | 142,118 | 1,350,404 | 6,629,059 |
| Person-hours without AC due to outages | 14,574 | 138,741 | 757,955 |
| Indoor heat person-hours from outages, all | 1,022 | 14,770 | 135,747 |
| … aged 65+ | 97 | 1,388 | 12,817 |
| … below poverty | 180 | 2,703 | 24,511 |
| Background indoor heat person-hours (homes without AC) | 5,750,791 | 10,000,535 | 13,223,521 |
| Highest indoor temperature in an AC home during an outage (°C) | 32.7 | 35.6 | 38.7 |
| Dialysis facility-hours lost (core) | 0.5 | 4.5 | 27.6 |
| Hospital facility-hours lost (core) | 0.02 | 0.38 | 2.27 |
| Runs with a TVA shortfall | 0.0% | 0.0% | 4.2% |
| K8 runs with degraded segments | 11.5% | 33.0% | 60.2% |
| K8 hospital Δ population mean, min (p99) | 0.004 (0.07) | 0.015 (0.21) | 0.041 (0.30) |
| K8 hospital largest cell increase p95, min | 0.6 | 1.4 | 2.2 |
| K8 dialysis Δ population mean, min (p99) | 0.030 (1.58) | 0.136 (1.79) | 0.313 (5.29) |
| K8 runs with no dialysis centre available | 0.0% | 0.8% | 8.8% |
| K8 EMS Δ population mean, min (p99) | 0.002 (0.04) | 0.008 (0.08) | 0.021 (0.13) |

Validation: ρ(model, EAGLE-I) all hours 0.04 [-0.03, 0.12] (n = 2,208 h, 92 days); non-storm 0.02 [-0.04, 0.08] (n = 1,994 h, 92 days).

| Parameter | Basis | ρ with person-hours without power | ρ with indoor heat person-hours from outages |
| --- | --- | --- | --- |
| `C-P1.Kd` K_design | assumption | 0.414 | 0.157 |
| `C-P3.sigma` sigma | assumption | 0.277 | 0.121 |
| `C-P3` theta_50 | assumption | -0.213 | -0.089 |
| `C-P2.dTOR` dTheta_TO_R | standard | 0.11 | 0.032 |
| `C-P2.dHR` dTheta_H_R | standard | 0.097 | 0.029 |
| `C-P1.Td` T_design | assumption | -0.061 | -0.023 |
| `C-P2.tau` tau_TO | standard | -0.042 | -0.025 |
| `C-P6` repair_hours | internal | 0.041 | 0.103 |

