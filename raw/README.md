# raw/

【中文】把下面这些文件从 Google Drive 复制到这个文件夹（文件名保持不变），然后运行 `python -m pipeline.build`。
这个文件夹不会提交到 git。装了 Google Drive 桌面版的话，文件在
`~/Library/CloudStorage/GoogleDrive-<账号>/My Drive/` 下面；parquet 请先复制到本地再读（直接读云端文件可能读坏）。

Copy these files from Google Drive into this folder (keep the names), then run `python -m pipeline.build`.

| 文件 | Drive 位置（My Drive/…） |
| --- | --- |
| `lst_hourly_2023/LST10m_2023-07-*_UTC*.tif`（165 个） | `01_Nashville_LST/Nashville_LST_Hourly_2023/` |
| `Nashville_Sentinel2_RGB.tif` | `01_Nashville_LST/Nashville_LST_Results/` |
| `Nashville_LST_10m_Final.tif` | `01_Nashville_LST/Nashville_LST_Results/` |
| `LST_Nashville_JJA2023_mean.tif` | `01_Nashville_LST/Nashville_LST_Mean/` |
| `LST10m_2024-07-31_UTC22.tif` | `01_Nashville_LST/Nashville_LST_Hourly/` |
| `Nash_ampMap_2023.tif` | `01_Nashville_LST/Nashville_LST_Spatial/` |
| `nashville_roads_lst_full.shp` / `.dbf` / `.shx` / `.prj` / `.cpg` | `03_Road_Temp_Cascade/nashville_road_temp/` |
| `nashville_surface_parking.geojson` | `handover/data/` |
| `events_hub311.parquet` | `06_Digital_Twin/twin_demo/l2/` |
| `buildings_aoi.parquet`（twin_demo 的 assets_buildings） | `06_Digital_Twin/twin_demo/l2/` |
| `health/{hospitals,dialysis,nursing_homes}.geojson`、`health/zcta_health.gpkg` | 共享目录 `cascading-heat_data/06_health/` |
| `tdot_bridge_condition_davidson.geojson` | `cascading-heat_data/04_transportation/` |
| `noaa_BNA_daily_2017-07_2024-11.csv` | `cascading-heat_data/01_temperature/` |
| `eaglei/eaglei_outages_2023.csv`（约 1.2 GB）+ 引用文件 | `cascading-heat_data/02_power/power_outage/` |
| `davidson_county.parquet`（twin_demo 的 `_county_47037.parquet`） | `06_Digital_Twin/twin_demo/l1_std/ntad/` |
| `osm/*.geojson`、`asos_bna_hourly.csv` | 运行 `python scripts/fetch_open_data.py` 自动下载 |

共享目录 `cascading-heat_data` 在 Drive 里位于 `.shortcut-targets-by-id/…/cascading-heat_data`（`digital_nashville` 的快捷方式）。

单个文件的直接链接见 `datasets.yaml` 里的 `drive_url`，文件夹见 `drive_folder`。

【中文】已知问题 / known issues：
`Nashville_Sentinel2_RGB.tif` 和 `Nashville_LST_10m_Final.tif` 目前只覆盖西南角约 5%，downtown AOI 内没有像元，需要从 GEE 按 AOI 重新导出。
Both files currently cover only the south-west ~5% and have no pixels in the downtown AOI; re-export them from GEE.
