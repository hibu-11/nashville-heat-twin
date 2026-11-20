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

Run `core-20261120T192400Z-7f3fc1a6c4`: 2,000 Monte Carlo runs per scenario, links K1, K2, K3, K5, K6, K7, K8, K9, K10, K11; deferred D1, D2, D3, D5, D6, D7, D8, D9, D10, D12, D13; power model `load` (K2–K3), supply dependency off (D13). Selection and equations: [CORE_MODEL.md](CORE_MODEL.md). Population in zones 702,461 (65+ 89,379, below poverty 98,031).

Values are means per run unless marked median (p95; mean). Time to care is computed per ED visit on each run's peak day (pipeline.care): travel to the nearest open hospital plus waiting at per-hospital queues.

| Output | +0 °C | +2 °C | +4 °C |
| --- | --- | --- | --- |
| Runs with any outage | 15.3% | 39.4% | 65.6% |
| Thermal failures (core) | 1.59 | 16.16 | 106.38 |
| Thermal failures + overload trips (full) | 22.00 | 154.41 | 772.63 |
| Person-hours without power (core) | 38,392 | 356,322 | 2,353,478 |
| Person-hours without power (full) | 776,836 | 6,016,354 | 29,991,519 |
| Person-hours without AC due to outages | 36,187 | 335,379 | 2,213,192 |
| Indoor heat person-hours from outages, all | 1,759 | 25,904 | 296,545 |
| … aged 65+ | 192 | 3,053 | 36,119 |
| … below poverty | 274 | 3,883 | 43,101 |
| Background indoor heat person-hours (homes without AC) | 28,034,396 | 53,657,207 | 76,058,371 |
| Highest indoor temperature in an AC home during an outage (°C) | 33.6 | 35.9 | 39.2 |
| Hospital hours closed (core): all | 0.07 | 0.51 | 2.97 |
| … from power (backup failed) | 0.07 | 0.51 | 2.97 |
| … from water (on-site supply exhausted) | 0.00 | 0.00 | 0.00 |
| Water-out hours (system) | 0.00 | 0.00 | 0.00 |
| Runs with a TVA shortfall (deferred D12; only with --shortfall) | — | — | — |
| K8 runs with degraded segments or hospital closures | 15.4% | 39.5% | 65.8% |
| K8 hospital Δ population mean, min (p99) | 0.010 (0.18) | 0.042 (0.91) | 0.162 (1.99) |
| K8 hospital largest cell increase p95, min | 1.2 | 3.4 | 11.6 |
| K10 excess heat-illness ED visits (summer) | 121.4 | 232.5 | 330.7 |
| K10 visits by ventilator and other device users (summer) | 2.1 | 20.4 | 128.3 |
| K10 peak-day extra visits: heat illness / device users | 4.2 / 0.9 | 4.4 / 5.5 | 4.7 / 23.4 |
| Per ED visit: added travel (rerouting + congestion), min | 0.000 (0.000; mean 0.000) | 0.000 (0.000; mean 0.000) | 0.000 (0.000; mean 0.010) |
| Per ED visit: added congestion only, min | 0.000 (0.020; mean 0.000) | 0.000 (0.130; mean 0.020) | 0.010 (0.460; mean 0.090) |
| Per ED visit: added delay from rutting (K11), min | 0.0000 (0.0000; mean 0.0000) | 0.0000 (0.0000; mean 0.0000) | 0.0000 (0.0000; mean 0.0000) |
| Per ED visit: added waiting, min | 1.4 (4.8; mean 2.2) | 1.7 (18.8; mean 6.1) | 2.6 (134.3; mean 23.8) |
| **Time to care per ED visit (travel + waiting), min** | **1.4 (4.8; mean 2.2)** | **1.7 (18.8; mean 6.1)** | **2.6 (134.5; mean 23.9)** |
| Share of visits at hospitals at the queue cap (ρ = 0.95) | 0.000 (0.000; mean 0.000) | 0.000 (0.000; mean 0.000) | 0.000 (0.070; mean 0.020) |

Validation: ρ(model, EAGLE-I) all hours 0.06 [-0.02, 0.14] (n = 2,208 h, 92 days); non-storm 0.02 [-0.04, 0.09] (n = 1,994 h, 92 days).

| Parameter | Basis | ρ with person-hours without power | ρ with indoor heat person-hours from outages |
| --- | --- | --- | --- |
| `C-P1.Kd` K_design | assumption | 0.432 | 0.154 |
| `C-P3.sigma` sigma | assumption | 0.328 | 0.15 |
| `C-P3` theta_50 | assumption | -0.247 | -0.102 |
| `C-P2.dTOR` dTheta_TO_R | standard | 0.126 | 0.037 |
| `C-P2.dHR` dTheta_H_R | standard | 0.096 | 0.051 |
| `C-P6` repair_hours | internal | 0.06 | 0.11 |
| `C-H16` W0 | assumption | 0.056 | 0.063 |
| `C-P2.tau` tau_TO | standard | -0.051 | -0.013 |

### 11.1 Knockout contributions

`python -m pipeline.contrib` (500 runs, 2026-11-20): share of time to care (mean per ED visit) lost when only that relation is switched off (negative = buffer). Series links share values; figures do not add up. Method: CORE_MODEL §4.2.

| Relation | Switched off | time to care +2 °C | time to care +4 °C | travel part (last) | waiting part (last) |
| --- | --- | ---: | ---: | ---: | ---: |
| R01 | local temperature = background (airport) series everywhere (no urban field) | -35% | -32% | -23% | -32% |
| R14 | dark signals keep full capacity (R14–R16 are in series, so one knockout covers all three) | 0% | 0% | 0% | 0% |
| R17 | closed hospitals keep their patients and capacity (no rerouting, no capacity loss) | 6% | 7% | 100% | 7% |
| R22 | extra care demand does not lengthen waiting | 100% | 100% | 0% | 100% |
| R27 | rutting does not deepen with warming (no rutting delay) | 0% | 0% | 0% | 0% |
| R02 | cooling load does not respond to temperature (load = base load) | 73% | 92% | 100% | 92% |
| R03a | hot spot sees each station's period-mean ambient instead of the hourly value | 66% | 75% | 93% | 75% |
| R03b | hot spot sees each run's period-mean cooling load instead of the hourly load | 73% | 92% | 100% | 92% |
| R04 | no thermal failures (p = 0) | 73% | 92% | 100% | 92% |
| R07 | a failed station returns after one hour | 67% | 75% | 71% | 75% |
| R09 | water plants never lose power | 0% | 0% | 0% | 0% |
| R10 | no storage buffer: water is lost as soon as every plant stops | 0% | 0% | 0% | 0% |
| R11 | hospitals never lose function from a zone outage | 6% | 7% | 100% | 7% |
| R12 | hospitals ignore water loss | 0% | 0% | 0% | 0% |
| R13 | signals never go dark | 0% | 0% | 0% | 0% |
| R18 | homes with AC keep their set point during outages | 0% | 2% | 9% | 2% |
| R19 | indoor equilibrium is not driven by outdoor temperature (held at the AC set point) | 28% | 11% | 9% | 11% |
| R21 | heat exposure does not raise heat-illness visits (k = 0) | 28% | 11% | 9% | 11% |
| R24 | ventilator and other device users make no visits during outages | 71% | 85% | 45% | 86% |

### 11.2 Line B assumption variants

`python -m pipeline.contrib --variants` (300 runs): only the named T4 parameters are fixed; same random numbers.

| Variant (+4 °C) | Time to care median, min | p95 | mean | Runs over 30 min | Device-user visits |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 2.69 | 157.7 | 27.02 | 14.0% | 139.4 |
| q = 0 (no device-user visits) | 1.56 | 6.0 | 4.37 | 1.7% | 0.0 |
| q = 0.01 | 1.99 | 19.6 | 8.42 | 4.0% | 21.7 |
| q = 0.15 | 3.48 | 358.7 | 54.93 | 26.0% | 325.5 |
| ED slack (rho0 0.60, D0 1400, W0 20) | 0.41 | 15.3 | 3.94 | 3.3% | 139.4 |
| ED stretched (rho0 0.85, D0 700, W0 45) | 16.91 | 595.3 | 106.14 | 39.7% | 139.4 |
| queue cap 0.90 | 2.69 | 109.4 | 16.86 | 13.3% | 139.4 |
| queue cap 0.98 | 2.69 | 213.2 | 49.48 | 14.3% | 139.4 |

### 11.3 Observed heat waves

Hottest five days of the summer at BNA, with one day before and after; +0 °C uses observed temperatures.

| Heat wave | Scenario | Runs with outage | Person-hours without power | Excess heat-illness visits | Device-user visits | Time to care median (p95), min |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2022-06-20 – 2022-06-26 | +0 °C | 17.3% | 44,525 | 20.3 | 1.8 | 1.4 (5.3) |
| 2022-06-20 – 2022-06-26 | +2 °C | 41.4% | 313,654 | 24.2 | 13.7 | 1.7 (24.5) |
| 2023-08-21 – 2023-08-27 | +0 °C | 14.3% | 30,844 | 23.7 | 1.2 | 1.4 (4.7) |
| 2023-08-21 – 2023-08-27 | +2 °C | 35.8% | 270,550 | 28.1 | 11.7 | 1.6 (18.6) |
| 2024-08-25 – 2024-08-31 | +0 °C | 26.5% | 113,972 | 20.9 | 4.6 | 1.5 (9.6) |
| 2024-08-25 – 2024-08-31 | +2 °C | 52.5% | 683,796 | 26.1 | 32.2 | 1.9 (65.0) |
| 2025-08-14 – 2025-08-20 | +0 °C | 13.2% | 26,773 | 22.8 | 1.1 | 1.3 (4.7) |
| 2025-08-14 – 2025-08-20 | +2 °C | 34.3% | 222,944 | 27.0 | 9.3 | 1.6 (14.5) |

### 11.4 What drives the extreme runs

`python -m pipeline.extremes`. Each run's added time per ED visit is split by Shapley decomposition over four causes on the peak day (heat-illness visits, device-user visits, hospital capacity lost to power and to water); congestion and rutting are additive. Runs are grouped by their time to care.

**+2 °C — minutes per ED visit by cause**

| Runs (by time to care) | Runs | Total | heat-illness visits | device-user visits | hospital closed (power) | hospital closed (water) | dark-signal congestion | rutting (K11) | Visits at capped hospitals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| below p50 | 1000 | 1.1 | 1.00 | 0.04 | 0.00 | 0.00 | 0.01 | 0.00 | 0% |
| p50–75 | 500 | 2.3 | 2.06 | 0.23 | 0.00 | 0.00 | 0.02 | 0.00 | 0% |
| p75–90 | 300 | 4.5 | 2.88 | 1.56 | 0.00 | 0.00 | 0.03 | 0.00 | 0% |
| p90–95 | 100 | 11.9 | 2.48 | 8.94 | 0.42 | 0.00 | 0.07 | 0.00 | 0% |
| p95–99 | 80 | 42.6 | 2.93 | 35.26 | 4.29 | 0.00 | 0.16 | 0.00 | 2% |
| p99 and above | 20 | 201.5 | 4.80 | 182.70 | 13.70 | 0.00 | 0.27 | 0.00 | 22% |

**+2 °C — upstream chain (medians)**

| Variable | Middle 50% of runs | Worst 5% | Worst 1% |
| --- | ---: | ---: | ---: |
| thermal failures | 0 | 124.5 | 360 |
| person-hours without power | 0 | 2.608e+06 | 8.385e+06 |
| hospital hours closed (summer) | 0 | 4 | 7 |
| peak-day heat-illness visits | 4.484 | 4.541 | 4.649 |
| peak-day device-user visits | 0 | 59.44 | 145.6 |
| peak-day open share of hospitals | 1 | 1 | 1 |
| hospitals at the queue cap | 0 | 1 | 2 |
| share of visits at hospitals at the cap | 0 | 0.0142 | 0.073 |
| K_design | 0.8433 | 0.9422 | 0.9686 |
| theta_50 (°C) | 140.2 | 137.4 | 137 |
| sigma (K) | 8.09 | 8.947 | 9.27 |
| repair (h) | 5.035 | 6.306 | 5.027 |
| q (visit probability) | 0.0656 | 0.0839 | 0.0876 |
| battery (h) | 3.284 | 2.746 | 2.222 |
| rho0 | 0.7442 | 0.751 | 0.7584 |
| D0 | 1,014 | 974.5 | 1,007 |
| W0 (min) | 31.55 | 32.12 | 32.83 |

**+2 °C — path analysis** (outcome log(1 + time to care per ED visit, min); R² of the outcome equation 0.922; 2,000 runs). Standardised total effects with 95% bootstrap intervals and the main routes.

| Parameter | Total effect [95% CI] | Share of explained spread | Main route |
| --- | ---: | ---: | --- |
| rho0 | +0.37 [+0.34, +0.39] | 37% | rho0 → Y (+0.37) |
| K_design | +0.31 [+0.29, +0.33] | 26% | K_design → failures → outage → device_peak → Y (+0.35) |
| sigma | +0.19 [+0.18, +0.21] | 10% | sigma → failures → outage → device_peak → Y (+0.22) |
| theta50 | -0.17 [-0.18, -0.15] | 8% | theta50 → failures → outage → device_peak → Y (-0.19) |
| battery | -0.14 [-0.17, -0.12] | 6% | battery → device_peak → Y (-0.14) |
| W0 | +0.12 [+0.11, +0.14] | 4% | W0 → Y (+0.12) |
| D0 | -0.12 [-0.13, -0.10] | 4% | D0 → Y (-0.12) |
| k_heat | +0.10 [+0.09, +0.12] | 3% | k_heat → heat_peak → Y (+0.10) |
| q | +0.08 [+0.05, +0.10] | 2% | q → device_peak → Y (+0.08) |
| cool_slope | +0.03 [+0.02, +0.04] | 0% | cool_slope → failures → outage → device_peak → Y (+0.03) |
| hosp_backup | +0.01 [+0.01, +0.02] | 0% | hosp_backup → hosp_closed → Y (+0.01) |
| repair | +0.01 [+0.00, +0.03] | 0% | repair → outage → device_peak → Y (+0.01) |

**+4 °C — minutes per ED visit by cause**

| Runs (by time to care) | Runs | Total | heat-illness visits | device-user visits | hospital closed (power) | hospital closed (water) | dark-signal congestion | rutting (K11) | Visits at capped hospitals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| below p50 | 1000 | 1.4 | 1.25 | 0.14 | 0.00 | 0.00 | 0.02 | 0.00 | 0% |
| p50–75 | 500 | 4.7 | 2.30 | 2.32 | 0.03 | 0.00 | 0.08 | 0.00 | 0% |
| p75–90 | 300 | 21.4 | 2.53 | 17.61 | 1.10 | 0.00 | 0.14 | 0.00 | 0% |
| p90–95 | 100 | 78.2 | 3.89 | 63.07 | 10.93 | 0.00 | 0.26 | 0.00 | 3% |
| p95–99 | 80 | 251.7 | 7.74 | 227.41 | 16.12 | 0.00 | 0.39 | 0.00 | 28% |
| p99 and above | 20 | 486.9 | 5.19 | 459.46 | 21.66 | 0.00 | 0.54 | 0.00 | 75% |

**+4 °C — upstream chain (medians)**

| Variable | Middle 50% of runs | Worst 5% | Worst 1% |
| --- | ---: | ---: | ---: |
| thermal failures | 3 | 733 | 1,152 |
| person-hours without power | 4.726e+04 | 1.667e+07 | 2.92e+07 |
| hospital hours closed (summer) | 0 | 16 | 38 |
| peak-day heat-illness visits | 4.689 | 5.486 | 5.163 |
| peak-day device-user visits | 0 | 201.7 | 300.9 |
| peak-day open share of hospitals | 1 | 1 | 0.9931 |
| hospitals at the queue cap | 0 | 4 | 8 |
| share of visits at hospitals at the cap | 0 | 0.2682 | 0.7234 |
| K_design | 0.8395 | 0.9446 | 0.9516 |
| theta_50 (°C) | 140.3 | 137.4 | 136.6 |
| sigma (K) | 8.109 | 8.867 | 9.057 |
| repair (h) | 4.937 | 6.394 | 5.956 |
| q (visit probability) | 0.0644 | 0.089 | 0.0976 |
| battery (h) | 3.216 | 2.639 | 2.824 |
| rho0 | 0.7485 | 0.7528 | 0.7549 |
| D0 | 1,006 | 999.7 | 1,003 |
| W0 (min) | 32.03 | 32.69 | 34.99 |

**+4 °C — path analysis** (outcome log(1 + time to care per ED visit, min); R² of the outcome equation 0.937; 2,000 runs). Standardised total effects with 95% bootstrap intervals and the main routes.

| Parameter | Total effect [95% CI] | Share of explained spread | Main route |
| --- | ---: | ---: | --- |
| K_design | +0.40 [+0.38, +0.42] | 42% | K_design → failures → outage → device_peak → Y (+0.41) |
| rho0 | +0.26 [+0.24, +0.27] | 17% | rho0 → Y (+0.26) |
| theta50 | -0.21 [-0.23, -0.20] | 12% | theta50 → failures → outage → device_peak → Y (-0.22) |
| sigma | +0.21 [+0.20, +0.22] | 11% | sigma → failures → outage → device_peak → Y (+0.22) |
| battery | -0.18 [-0.21, -0.16] | 9% | battery → device_peak → Y (-0.18) |
| q | +0.11 [+0.09, +0.13] | 3% | q → device_peak → Y (+0.11) |
| D0 | -0.09 [-0.10, -0.08] | 2% | D0 → Y (-0.09) |
| W0 | +0.09 [+0.07, +0.10] | 2% | W0 → Y (+0.09) |
| cool_slope | +0.06 [+0.05, +0.07] | 1% | cool_slope → failures → outage → device_peak → Y (+0.06) |
| k_heat | +0.04 [+0.04, +0.05] | 0% | k_heat → heat_peak → Y (+0.04) |
| hosp_backup | +0.02 [+0.01, +0.03] | 0% | hosp_backup → hosp_closed → Y (+0.02) |
| repair | +0.02 [+0.00, +0.03] | 0% | repair → outage → device_peak → Y (+0.02) |

