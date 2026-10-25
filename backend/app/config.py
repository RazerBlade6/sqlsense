from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    aws_region: str = Field(default="ap-southeast-2", alias="AWS_REGION")
    sql_model_id: str = Field(default="apac.amazon.nova-pro-v1:0", alias="SQL_MODEL_ID")
    planner_model_id: str = Field(default="apac.amazon.nova-micro-v1:0", alias="PLANNER_MODEL_ID")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    database_url: str = Field(alias="DATABASE_URL")
    db_include_schemas: str = Field(default="public", alias="DB_INCLUDE_SCHEMAS")
    max_result_rows: int = Field(default=100, alias="MAX_RESULT_ROWS")
    sql_statement_timeout_ms: int = Field(default=8000, alias="SQL_STATEMENT_TIMEOUT_MS")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def schema_names(self) -> list[str]:
        return [schema.strip() for schema in self.db_include_schemas.split(",") if schema.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
