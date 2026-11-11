# Results — heat-cascade model v0

Generated from cascade run `cascade-20261110T212705Z-72f1c05324` (build `20261110T205908Z-b0b31216`, code `git:6e01edb-dirty`, seed 20261027, 2,000 Monte Carlo runs per scenario plus 500 runs at mid parameters). Period 2023-06-01 – 2023-08-31, 2,208 hours. Methods: [HANDBOOK.md](HANDBOOK.md).

> These are preliminary results from a model with placeholder links and parameters (HANDBOOK §3.4). They show how the coupled system responds under stated assumptions; they are not estimates of actual outages.

## 1. Network

| Element | Count |
| --- | --- |
| Substations (OSM, AOI + 4 km) | 159 |
| Service zones (placeholder) | 112 |
| Supply edges | 234 |
| Load-transfer peer pairs | 148 |
| Hospitals | 12 |
| Nursing homes | 24 |
| Dialysis facilities | 20 |
| Water works | 9 |
| Traffic signals | 1,425 |
| Road segments with a signal | 1,765 |
| Population in service zones | 702,461 (age 65+: 89,379) |

## 2. Scenarios (season totals, Jun–Aug)

Mean over runs, with the 95th percentile in brackets. Scenarios add a uniform offset to the observed 2023 air temperature.

| Scenario | Peak air temp. | Runs with any failure | Thermal failures | Overload trips | Trips per thermal failure | Person-hours without power | Compound heat–outage person-hours | Dialysis facility-hours down |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023 observed | 36.7 °C | 17.7% | 3.6 [10] | 18.4 [34] | 0.60 | 776,836 [1,253,057] | 210,031 [644,938] | 33.0 |
| +2 °C | 38.7 °C | 42.1% | 29.5 [187] | 124.9 [587] | 1.71 | 6,016,354 [30,019,375] | 2,249,047 [14,190,940] | 224.4 |
| +4 °C | 40.7 °C | 69.4% | 156.6 [882] | 616.1 [3,360] | 8.00 | 29,991,519 [154,859,910] | 13,965,117 [72,755,293] | 1,117.5 |

With every parameter at its mid value (observed 2023), the mean is 0.00 thermal failures and 0 person-hours without power. Most of the risk in the full Monte Carlo therefore comes from the tails of the parameter ranges, not from the Bernoulli draws.

## 3. Sensitivity (observed 2023 scenario)

Spearman ρ between each sampled parameter and the season totals of a run. Sorted by |ρ| with person-hours without power.

| Parameter | Name | Basis | ρ person-hours | ρ compound person-hours | ρ thermal failures | ρ overload trips |
| --- | --- | --- | --- | --- | --- | --- |
| `C-P1.Kd` | K_design | assumption | 0.45 | 0.45 | 0.46 | 0.41 |
| `C-P3.sigma` | sigma | assumption | 0.33 | 0.33 | 0.34 | 0.28 |
| `C-P3` | theta_50 | assumption | -0.25 | -0.25 | -0.25 | -0.23 |
| `C-P2.dTOR` | dTheta_TO_R | standard | 0.12 | 0.12 | 0.12 | 0.12 |
| `C-P2.dHR` | dTheta_H_R | standard | 0.11 | 0.11 | 0.12 | 0.10 |
| `C-POP2` | T_heat | assumption | 0.06 | 0.05 | 0.06 | 0.04 |
| `C-P1.Td` | T_design | assumption | -0.05 | -0.05 | -0.05 | -0.05 |
| `C-P6` | repair_hours | internal | 0.04 | 0.04 | 0.03 | 0.02 |
| `C-T2` | p_no_battery | literature | -0.04 | -0.04 | -0.04 | -0.05 |
| `C-P2.tau` | tau_TO | standard | -0.03 | -0.03 | -0.04 | -0.04 |
| `C-P1` | beta | internal | -0.03 | -0.03 | -0.02 | -0.03 |
| `C-P9.avail` | a | literature | 0.03 | 0.03 | 0.04 | 0.02 |
| `C-H2` | p_backup_fail | literature | -0.02 | -0.03 | -0.02 | -0.02 |
| `C-P9` | T_lim | assumption | 0.02 | 0.02 | 0.03 | -0.02 |
| `C-P9.imp` | P_imp | literature | -0.02 | -0.02 | -0.01 | 0.01 |
| `C-W2` | p_backup_fail | literature | 0.02 | 0.01 | 0.02 | 0.03 |
| `C-W3` | storage_hours | internal | 0.01 | 0.01 | 0.01 | 0.02 |
| `C-P2.R` | R | standard | -0.01 | -0.01 | -0.01 | -0.01 |
| `C-P9.flow` | f_low | assumption | -0.01 | -0.01 | -0.01 | -0.02 |
| `C-P4` | alpha | internal | 0.01 | 0.00 | 0.01 | -0.01 |
| `C-H1` | p_backup_fail | literature | -0.01 | -0.01 | 0.00 | 0.01 |
| `C-P9.span` | span | assumption | 0.00 | 0.01 | -0.00 | 0.01 |
| `C-P9.Qmin` | Q_min | assumption | -0.00 | -0.00 | -0.01 | 0.00 |

## 4. Validation

| Check | Result |
| --- | --- |
| V1 Model vs EAGLE-I, all hours (Spearman ρ, 95% day-block CI) | 0.02 [-0.07, 0.14] (n = 2,208 h, 92 days) |
| V2 Model vs EAGLE-I, non-storm hours | 0.01 [-0.09, 0.11] (n = 1,994 h, 92 days) |
| V3 Air temperature vs EAGLE-I, non-storm hours (data only) | 0.19 [0.10, 0.28] (n = 1,994 h, 92 days) |
| V3 Daily max air temperature vs daily max outages (data only) | 0.22 [0.02, 0.42] (n = 92 days) |
| Model daily max vs observed daily max | 0.17 [-0.04, 0.39] (n = 92 days) |
| V4 Pavement requests (2023-07-01 – 2023-07-21, 153 of 15,580 segments): AUC of P(T7 > x50) (Eq. 15) | 0.754 |
| V4 Same, T7 itself / single-day peak LST | 0.754 / 0.753 |
| V5 Same, segment length only (baseline) | 0.830 |
| V5 Same, T7 within segment-length quintiles | 0.677 |
| V4 All road requests (pavement + other road), LST period, 765 segments | 0.713 (length only 0.797; within length quintiles 0.645) |
| V4 Pavement requests, Jun–Aug (560 segments) | 0.722 (length only 0.797; within length quintiles 0.657) |

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
| Edgehill Substation | distribution | 69.0 | 4.87 | 103.1 |
| w207869586 | distribution | 69.0 | 4.80 | 102.9 |
| Green Hills Substation | distribution | 69.0 | 4.80 | 104.7 |
| w1088464206 | minor_distribution | 23.9 | 4.79 | 104.7 |
| Peabody Substation | distribution | 69.0 | 4.78 | 105.6 |
| Battlefield Substation | distribution | 69.0 | 4.77 | 104.3 |
| 11th Avenue Substation | — | 69.0 | 4.77 | 105.8 |
| Sharondale Substation | distribution | 69.0 | 4.75 | 103.4 |
| w208608293 | distribution | 69.0 | 4.73 | 99.8 |
| w207878703 | distribution | 69.0 | 4.72 | 97.9 |

## 6. Pavement module

15,580 segments with hourly LST. Maximum 7-day running mean of daily-max LST (T7): 5th / 50th / 95th percentile 58.8 / 62.5 / 66.5 °C. Mean P(T7 > x50) = 0.361; 2,289 segments with P > 0.5.

## 7. Urban air-temperature field (M-6)

Regressions on the 2022 heat-mapping traverses (aggregated to 100 m cells, 1 km spatial-block cross-validation). Predictors: impervious share and forest share within 90 m and 510 m, water share within 990 m, distance to water, elevation and topographic position.

| Period | Anchor (local hour) | Cells | CV RMSE | Null RMSE | CV R² | Anomaly at BNA |
| --- | --- | --- | --- | --- | --- | --- |
| morning | 6.5 | 3,253 | 0.627 °C | 0.954 °C | 0.569 | +1.23 °C |
| afternoon | 15.5 | 2,460 | 0.588 °C | 0.668 °C | 0.225 | +0.16 °C |
| evening | 19.5 | 2,286 | 0.443 °C | 0.694 °C | 0.592 | +0.15 °C |

The traverse files carry no date. Closest BNA match: 2022-08-14 (RMSE 0.99 °C over the three periods); next 2022-06-29, 2022-07-14. To be confirmed with the campaign organisers.

Substation temperature offsets relative to BNA: -2.81 to 0.86 °C (mean -0.68); zones -2.59 to 0.62 °C.

| Observed 2023, same random draws | Urban field (M-6) | BNA everywhere (A-D4) |
| --- | --- | --- |
| Thermal failures, mean | 3.6 | 4.9 |
| Overload trips, mean | 18.4 | 19.9 |
| Person-hours without power, mean | 776,835.7 | 1,003,772.2 |
| Compound person-hours, mean | 210,030.6 | 337,733.1 |

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

Road network from TIGER segments in the AOI: 69,707 edges, 59,400 nodes, 99.0% of nodes in the main component. HPMS 2024 AADT matched to 20.6% of edges (15.6% of length); the rest use class defaults. Hourly profile from TMAS weekdays. 695,003 residents in 14,602 cells of 250 m; 31.4% of edges are signal-controlled.

Population-weighted travel time to the nearest available facility (minutes; 90th percentile in brackets).

| Condition | Local hour | Expected degraded segments | Hospital | Dialysis | Fire / EMS | Share > 8 min to EMS |
| --- | --- | --- | --- | --- | --- | --- |
| night | 3 | — | 7.72 [14.21] (12 open) | 6.73 [11.70] (17 open) | 5.21 [9.27] (34 open) | 16.4% |
| am_peak | 8 | — | 7.77 [14.34] (12 open) | 6.76 [11.77] (17 open) | 5.24 [9.34] (34 open) | 16.8% |
| pm_peak | 17 | — | 7.81 [14.44] (12 open) | 6.78 [11.83] (17 open) | 5.26 [9.39] (34 open) | 17.1% |
| all_signals_dark_pm | 17 | — | 8.81 [16.87] (12 open) | 7.37 [13.47] (17 open) | 5.80 [10.79] (34 open) | 22.9% |
| stress_+0 | 18 | 37.5 | 7.77 [14.33] (12 open) | 6.76 [11.77] (17 open) | 5.23 [9.33] (34 open) | 16.8% |
| stress_+2 | 18 | 196.8 | 7.78 [14.36] (12 open) | 6.76 [11.78] (17 open) | 5.24 [9.34] (34 open) | 16.8% |
| stress_+4 | 18 | 562.8 | 7.82 [14.45] (12 open) | 6.78 [11.84] (17 open) | 5.26 [9.38] (34 open) | 17.1% |

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

Run `core-20261110T213942Z-72f1c05324`: 2,000 Monte Carlo runs per scenario, links K1, K2, K3, K4, K5, K6, K7, K8, K9, K10; deferred D1, D2, D3, D5, D6, D7, D8, D9. Selection and equations: [CORE_MODEL.md](CORE_MODEL.md). Population in zones 702,461 (65+ 89,379, below poverty 98,031).

| Output (mean per run) | +0 °C | +2 °C | +4 °C |
| --- | --- | --- | --- |
| Runs with any outage | 16.1% | 38.4% | 67.6% |
| Thermal failures (core) | 1.57 | 16.06 | 106.40 |
| Thermal failures + overload trips (full) | 22.00 | 154.41 | 772.63 |
| Person-hours without power (core) | 61,916 | 655,448 | 4,077,135 |
| Person-hours without power (full) | 776,836 | 6,016,354 | 29,991,519 |
| Person-hours without AC due to outages | 58,453 | 616,938 | 3,833,628 |
| Indoor heat person-hours from outages, all | 3,038 | 56,743 | 629,094 |
| … aged 65+ | 389 | 6,812 | 76,694 |
| … below poverty | 442 | 8,384 | 91,550 |
| Background indoor heat person-hours (homes without AC) | 28,034,396 | 53,657,207 | 76,058,371 |
| Highest indoor temperature in an AC home during an outage (°C) | 33.0 | 35.9 | 38.9 |
| Dialysis facility-hours lost (core) | 1.6 | 16.3 | 105.9 |
| Hospital facility-hours lost (core) | 0.07 | 0.66 | 4.42 |
| Runs with a TVA shortfall | 0.0% | 0.0% | 4.2% |
| K8 runs with degraded segments | 16.2% | 38.4% | 67.7% |
| K8 hospital Δ population mean, min (p99) | 0.009 (0.23) | 0.055 (1.10) | 0.190 (2.15) |
| K8 hospital largest cell increase p95, min | 1.4 | 4.0 | 10.0 |
| K8 dialysis Δ population mean, min (p99) | 0.047 (1.53) | 0.351 (5.93) | 1.437 (22.70) |
| K8 runs with no dialysis centre available | 0.0% | 0.1% | 2.7% |
| K8 EMS Δ population mean, min (p99) | 0.005 (0.13) | 0.025 (0.34) | 0.079 (0.65) |

Validation: ρ(model, EAGLE-I) all hours 0.03 [-0.04, 0.12] (n = 2,208 h, 92 days); non-storm -0.01 [-0.08, 0.06] (n = 1,994 h, 92 days).

| Parameter | Basis | ρ with person-hours without power | ρ with indoor heat person-hours from outages |
| --- | --- | --- | --- |
| `C-P1.Kd` K_design | assumption | 0.439 | 0.144 |
| `C-P3.sigma` sigma | assumption | 0.339 | 0.161 |
| `C-P3` theta_50 | assumption | -0.24 | -0.116 |
| `C-P2.dTOR` dTheta_TO_R | standard | 0.144 | 0.071 |
| `C-P2.dHR` dTheta_H_R | standard | 0.089 | 0.043 |
| `C-P6` repair_hours | internal | 0.048 | 0.133 |
| `C-P1.Td` T_design | assumption | -0.046 | -0.03 |
| `C-P2.tau` tau_TO | standard | -0.046 | -0.012 |

