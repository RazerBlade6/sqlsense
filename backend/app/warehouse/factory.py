from functools import lru_cache

from app.config import Settings, get_settings
from app.warehouse.base import Warehouse
from app.warehouse.catalog import load_catalog


def build_warehouse(settings: Settings) -> Warehouse:
    if settings.warehouse == "athena":
        from app.warehouse.athena import AthenaWarehouse

        return AthenaWarehouse(
            region=settings.aws_region,
            workgroup=settings.athena_workgroup,
            database=settings.glue_database,
        )
    from app.warehouse.duckdb_local import DuckDBWarehouse

    catalog = load_catalog(settings.catalog_path)
    if settings.duckdb_data_path:
        return DuckDBWarehouse(catalog, settings.duckdb_data_path)
    return DuckDBWarehouse(catalog)


@lru_cache
def get_warehouse() -> Warehouse:
    return build_warehouse(get_settings())
