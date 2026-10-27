# Results — heat-cascade model v0

Generated from cascade run `cascade-20261027T181442Z-48723ea5b7` (build `20261027T181135Z-053157f7`, code `git:78173d6-dirty`, seed 20261027, 2,000 Monte Carlo runs per scenario plus 500 runs at mid parameters). Period 2023-06-01 – 2023-08-31, 2,208 hours. Methods: [HANDBOOK.md](HANDBOOK.md).

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
| 2023 observed | 36.7 °C | 15.2% | 2.3 [9] | 6.5 [18] | 0.30 | 413,515 [1,092,010] | 81,202 [342,207] | 26.4 |
| +2 °C | 38.7 °C | 38.3% | 16.8 [105] | 50.2 [271] | 1.03 | 3,035,025 [15,762,381] | 844,080 [5,241,692] | 191.4 |
| +4 °C | 40.7 °C | 65.7% | 79.2 [455] | 224.7 [1,273] | 2.36 | 12,924,108 [74,200,790] | 4,917,847 [26,984,010] | 784.8 |

With every parameter at its mid value (observed 2023), the mean is 0.00 thermal failures and 0 person-hours without power. Most of the risk in the full Monte Carlo therefore comes from the tails of the parameter ranges, not from the Bernoulli draws.

## 3. Sensitivity (observed 2023 scenario)

Spearman ρ between each sampled parameter and the season totals of a run. Sorted by |ρ| with person-hours without power.

| Parameter | Name | Basis | ρ person-hours | ρ compound person-hours | ρ thermal failures | ρ overload trips |
| --- | --- | --- | --- | --- | --- | --- |
| `C-P1.Kd` | K_design | assumption | 0.40 | 0.40 | 0.43 | 0.37 |
| `C-P3.sigma` | sigma | assumption | 0.29 | 0.29 | 0.32 | 0.25 |
| `C-P3` | theta_50 | assumption | -0.24 | -0.24 | -0.25 | -0.22 |
| `C-P2.dTOR` | dTheta_TO_R | standard | 0.12 | 0.11 | 0.12 | 0.11 |
| `C-P2.dHR` | dTheta_H_R | standard | 0.08 | 0.08 | 0.09 | 0.09 |
| `C-P2.tau` | tau_TO | standard | -0.08 | -0.08 | -0.07 | -0.08 |
| `C-P6` | repair_hours | assumption | 0.06 | 0.06 | 0.06 | 0.03 |
| `C-P1.Td` | T_design | assumption | -0.05 | -0.05 | -0.05 | -0.06 |
| `C-POP2` | T_heat | assumption | 0.03 | 0.03 | 0.04 | 0.04 |
| `C-W3` | storage_hours | assumption | 0.03 | 0.03 | 0.03 | 0.03 |
| `C-W2` | p_backup_fail | assumption | 0.03 | 0.03 | 0.02 | 0.03 |
| `C-T2` | p_no_battery | assumption | -0.03 | -0.03 | -0.02 | -0.03 |
| `C-H1` | p_backup_fail | assumption | 0.03 | 0.02 | 0.01 | 0.02 |
| `C-P2.R` | R | standard | -0.02 | -0.02 | -0.03 | -0.02 |
| `C-H2` | p_backup_fail | assumption | -0.02 | -0.01 | -0.02 | -0.03 |
| `C-P4` | alpha | internal | 0.01 | 0.01 | 0.01 | 0.01 |
| `C-P1` | beta | internal | -0.01 | -0.01 | -0.01 | -0.01 |

## 4. Validation

| Check | Result |
| --- | --- |
| V1 Model vs EAGLE-I, all hours (Spearman ρ, 95% day-block CI) | -0.02 [-0.13, 0.09] (n = 2,208 h, 92 days) |
| V2 Model vs EAGLE-I, non-storm hours | -0.04 [-0.14, 0.07] (n = 1,994 h, 92 days) |
| V3 Air temperature vs EAGLE-I, non-storm hours (data only) | 0.19 [0.10, 0.28] (n = 1,994 h, 92 days) |
| V3 Daily max air temperature vs daily max outages (data only) | 0.22 [0.02, 0.42] (n = 92 days) |
| Model daily max vs observed daily max | 0.04 [-0.16, 0.25] (n = 92 days) |
| V4 Pavement requests (2023-07-01 – 2023-07-21, 71 of 4,137 segments): AUC of P(T7 > x50) (Eq. 15) | 0.746 |
| V4 Same, T7 itself / single-day peak LST | 0.746 / 0.744 |
| V5 Same, segment length only (baseline) | 0.808 |
| V5 Same, T7 within segment-length quintiles | 0.641 |
| V4 All road requests (pavement + other road), LST period, 341 segments | 0.703 (length only 0.787; within length quintiles 0.608) |
| V4 Pavement requests, Jun–Aug (233 segments) | 0.664 (length only 0.759; within length quintiles 0.576) |

Observed customers out (Davidson County, EAGLE-I) on non-storm hours, by air temperature:

| Air temperature | Hours | Median | 90th percentile | Share of hours > 1,000 customers |
| --- | --- | --- | --- | --- |
| (20, 24] °C | 556 | 12 | 566 | 8.8% |
| (24, 28] °C | 634 | 13 | 710 | 6.5% |
| (28, 30] °C | 262 | 17 | 339 | 4.6% |
| (30, 32] °C | 166 | 16 | 552 | 7.8% |
| (32, 34] °C | 119 | 17 | 619 | 4.2% |
| (34, 36] °C | 40 | 46 | 238 | 7.5% |
| (36, 40] °C | 14 | 44 | 242 | 0.0% |

## 5. Substations with the highest expected outage hours (observed 2023)

| Substation | Type | Max kV | Expected hours down | Peak mean hot-spot (°C) |
| --- | --- | --- | --- | --- |
| Harding Pike Substation | minor_distribution | 23.9 | 6.85 | 103.6 |
| Green Hills Substation | distribution | 69.0 | 6.84 | 103.7 |
| w207878703 | distribution | 69.0 | 6.79 | 103.7 |
| Battlefield Substation | distribution | 69.0 | 6.78 | 103.6 |
| w1489136127 | minor_distribution | 23.9 | 6.75 | 103.6 |
| Edgehill Substation | distribution | 69.0 | 6.59 | 103.6 |
| w207869586 | distribution | 69.0 | 6.54 | 103.7 |
| w1489136194 | minor_distribution | 23.9 | 6.52 | 103.6 |
| w1088464206 | minor_distribution | 23.9 | 6.51 | 103.6 |
| w1489136079 | minor_distribution | 23.9 | 6.51 | 103.6 |

## 6. Pavement module

4,137 segments with hourly LST. Maximum 7-day running mean of daily-max LST (T7): 5th / 50th / 95th percentile 60.1 / 63.2 / 67.0 °C. Mean P(T7 > x50) = 0.424; 1,222 segments with P > 0.5.

