from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.warehouse.catalog import DEFAULT_CATALOG_PATH


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    aws_region: str = Field(default="ap-southeast-2", alias="AWS_REGION")
    sql_model_id: str = Field(default="apac.amazon.nova-pro-v1:0", alias="SQL_MODEL_ID")
    planner_model_id: str = Field(default="apac.amazon.nova-micro-v1:0", alias="PLANNER_MODEL_ID")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")

    warehouse: Literal["duckdb", "athena"] = Field(default="duckdb", alias="WAREHOUSE")
    catalog_path: Path = Field(default=DEFAULT_CATALOG_PATH, alias="CATALOG_PATH")
    duckdb_data_path: Path | None = Field(default=None, alias="DUCKDB_DATA_PATH")
    athena_workgroup: str = Field(default="sqlsense", alias="ATHENA_WORKGROUP")
    glue_database: str = Field(default="retail", alias="GLUE_DATABASE")

    max_result_rows: int = Field(default=100, alias="MAX_RESULT_ROWS")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
