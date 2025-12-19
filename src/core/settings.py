from __future__ import annotations

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .dotenv import load_dotenv


class AppSettings(BaseSettings):
    """
    Central settings for the service.
    - Loads from environment variables (optionally from a dotenv file).
    - Keeps "state/models" separate: settings only stores configuration, not runtime state.
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # ---- dotenv ----
    dotenv_path: str = Field(default=".env", validation_alias="TTES_ENV_FILE")

    # ---- VikingDB ----
    vikingdb_ak: str = Field(validation_alias="VIKINGDB_AK")
    vikingdb_sk: str = Field(validation_alias="VIKINGDB_SK")
    vikingdb_host: str = Field(validation_alias="VIKINGDB_HOST")
    vikingdb_region: str = Field(default="cn-beijing", validation_alias="VIKINGDB_REGION")
    vikingdb_service: str = Field(default="vikingdb", validation_alias="VIKINGDB_SERVICE")
    vikingdb_timeout_s: int = Field(default=60, validation_alias="VIKINGDB_TIMEOUT_S")

    vikingdb_collection_name: str = Field(validation_alias="VIKINGDB_COLLECTION_NAME")
    vikingdb_index_name: str = Field(default="", validation_alias="VIKINGDB_INDEX_NAME")
    vikingdb_enable_influence_filter: bool = Field(default=True, validation_alias="VIKINGDB_ENABLE_INFLUENCE_FILTER")
    vikingdb_default_limit: int = Field(default=10, validation_alias="VIKINGDB_LIMIT")
    vikingdb_need_instruction: bool = Field(default=True, validation_alias="VIKINGDB_NEED_INSTRUCTION")
    vikingdb_default_output_fields: str = Field(
        default="video_id,landscape_video,influencer,video_duration,content_structure",
        validation_alias="VIKINGDB_OUTPUT_FIELDS",
    )

    # ---- Qwen (DashScope) ----
    dashscope_api_key: str = Field(validation_alias="DASHSCOPE_API_KEY")
    qwen_model: str = Field(default="qwen-turbo", validation_alias="QWEN_MODEL")
    qwen_temperature: float = Field(default=0.0, validation_alias="QWEN_TEMPERATURE")

    # ---- MySQL ----
    mysql_host: Optional[str] = Field(default=None, validation_alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, validation_alias="MYSQL_PORT")
    mysql_user: Optional[str] = Field(default=None, validation_alias="MYSQL_USER")
    mysql_password: Optional[str] = Field(default=None, validation_alias="MYSQL_PASSWORD")
    mysql_db: Optional[str] = Field(default=None, validation_alias="MYSQL_DB")
    mysql_charset: str = Field(default="utf8mb4", validation_alias="MYSQL_CHARSET")

    def resolve_index_name(self) -> str:
        idx = (self.vikingdb_index_name or "").strip()
        return idx or self.vikingdb_collection_name

    def ensure_dashscope_env(self) -> None:
        if os.getenv("DASHSCOPE_API_KEY"):
            return
        os.environ["DASHSCOPE_API_KEY"] = self.dashscope_api_key


def load_settings() -> AppSettings:
    dotenv_path = os.getenv("TTES_ENV_FILE", ".env")
    load_dotenv(dotenv_path, override=False)

    settings = AppSettings()
    settings.ensure_dashscope_env()
    return settings


