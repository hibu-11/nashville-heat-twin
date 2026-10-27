"""
【中文】adapter 注册表：datasets.yaml 里的 kind → 适配器类。
新增数据类型时在这里加一行。
Adapter registry: maps `kind` in datasets.yaml to an adapter class.
"""
from .dependencies import DependencyRulesAdapter
from .events import EventsAdapter
from .raster import RasterAdapter, RgbRasterAdapter
from .series import RasterSeriesAdapter
from .table import TableAdapter
from .timeseries import OutageSeriesAdapter, StationSeriesAdapter
from .vector import VectorAdapter

REGISTRY = {
    "raster": RasterAdapter,
    "raster_rgb": RgbRasterAdapter,
    "raster_series": RasterSeriesAdapter,
    "vector": VectorAdapter,
    "events": EventsAdapter,
    "table": TableAdapter,
    "station_series": StationSeriesAdapter,
    "outage_series": OutageSeriesAdapter,
    "dependency_rules": DependencyRulesAdapter,
}
