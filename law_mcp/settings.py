from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    law_api_oc: str | None
    law_api_oc_env_name: str | None
    law_api_base_url: str
    law_api_timeout_seconds: int
    mcp_auth_token: str | None
    stateless_http: bool


def get_settings() -> Settings:
    base_url = os.getenv("LAW_API_BASE_URL", "https://www.law.go.kr/DRF").rstrip("/")
    law_api_oc = os.getenv("LAW_OPEN_API_OC") or os.getenv("LAW_API_OC")
    law_api_oc_env_name = (
        "LAW_OPEN_API_OC"
        if os.getenv("LAW_OPEN_API_OC")
        else "LAW_API_OC"
        if os.getenv("LAW_API_OC")
        else None
    )
    return Settings(
        law_api_oc=law_api_oc,
        law_api_oc_env_name=law_api_oc_env_name,
        law_api_base_url=base_url,
        law_api_timeout_seconds=env_int("LAW_API_TIMEOUT_SECONDS", 20),
        mcp_auth_token=os.getenv("MCP_AUTH_TOKEN"),
        stateless_http=env_bool("FASTMCP_STATELESS_HTTP", True),
    )
