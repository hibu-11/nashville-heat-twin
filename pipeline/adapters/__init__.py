"""
【中文】adapter 注册表：datasets.yaml 里的 kind → 适配器类。
新增数据类型时在这里加一行。
Adapter registry: maps `kind` in datasets.yaml to an adapter class.
"""
from .events import EventsAdapter
from .raster import RasterAdapter, RgbRasterAdapter
from .series import RasterSeriesAdapter
from .table import TableAdapter
from .vector import VectorAdapter

REGISTRY = {
    "raster": RasterAdapter,
    "raster_rgb": RgbRasterAdapter,
    "raster_series": RasterSeriesAdapter,
    "vector": VectorAdapter,
    "events": EventsAdapter,
    "table": TableAdapter,
}
