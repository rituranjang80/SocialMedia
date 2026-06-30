"""Runtime API configuration — loaded from JSON file + environment overrides.

Mount ``config/api_defaults.json`` (or a custom path via ``API_CONFIG_PATH``)
into the container and restart to change Swagger dropdowns, defaults, and
pagination limits without rebuilding the image.

Environment overrides (optional, take precedence over JSON):
  API_CONFIG_PATH              Path to JSON config file
  API_INBOX_DEFAULT_LIMIT      int
  API_INBOX_MAX_LIMIT          int
  API_ANALYTICS_DEFAULT_DAYS   int
  API_INBOX_DEFAULT_VIEW       str
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

LOG = logging.getLogger(__name__)

_BUILTIN_PATH = Path(settings.BASE_DIR) / "config" / "api_defaults.json"

_ENV_INT_OVERRIDES = {
    "API_INBOX_DEFAULT_LIMIT": ("pagination", "inbox_default_limit"),
    "API_INBOX_MAX_LIMIT": ("pagination", "inbox_max_limit"),
    "API_CALENDAR_MAX_DAYS": ("pagination", "calendar_max_days"),
    "API_MEMBERS_DEFAULT_LIMIT": ("pagination", "members_default_limit"),
    "API_ANALYTICS_DEFAULT_DAYS": ("defaults", "analytics_days"),
}

_ENV_STR_OVERRIDES = {
    "API_INBOX_DEFAULT_VIEW": ("defaults", "inbox_view"),
    "API_INVITATION_ORG_ROLE": ("defaults", "invitation_org_role"),
    "API_INVITATION_WORKSPACE_ROLE": ("defaults", "invitation_workspace_role"),
}


def _deep_get(data: dict, *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _deep_set(data: dict, keys: tuple[str, ...], value: Any) -> None:
    cur = data
    for key in keys[:-1]:
        cur = cur.setdefault(key, {})
    cur[keys[-1]] = value


def _load_json(path: Path) -> dict:
    if not path.is_file():
        LOG.warning("API config file not found at %s — using empty defaults.", path)
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _platform_choices_from_django() -> list[str]:
    from apps.credentials.models import PlatformCredential

    return [c[0] for c in PlatformCredential.Platform.choices]


@lru_cache(maxsize=1)
def get_api_runtime_config() -> dict[str, Any]:
    """Load merged API runtime config (cached until process restart)."""
    configured = getattr(settings, "API_CONFIG_PATH", None) or os.environ.get("API_CONFIG_PATH")
    path = Path(configured) if configured else _BUILTIN_PATH
    data = _load_json(path)

    for env_key, path_keys in _ENV_INT_OVERRIDES.items():
        raw = os.environ.get(env_key, "").strip()
        if raw.isdigit():
            _deep_set(data, path_keys, int(raw))

    for env_key, path_keys in _ENV_STR_OVERRIDES.items():
        raw = os.environ.get(env_key, "").strip()
        if raw:
            _deep_set(data, path_keys, raw)

    enums = data.setdefault("enums", {})
    if not enums.get("platforms"):
        enums["platforms"] = _platform_choices_from_django()

    return data


def reload_api_runtime_config() -> dict[str, Any]:
    get_api_runtime_config.cache_clear()
    return get_api_runtime_config()


class ApiConfig:
    """Typed accessor for runtime API configuration."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data if data is not None else get_api_runtime_config()

    def enum(self, key: str, *, fallback: list[str] | None = None) -> list[str]:
        values = _deep_get(self._data, "enums", key, default=None)
        if isinstance(values, list) and values:
            return [str(v) for v in values]
        return list(fallback or [])

    def pagination(self, key: str, *, default: int) -> int:
        val = _deep_get(self._data, "pagination", key, default=default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def default(self, key: str, *, fallback: Any = None) -> Any:
        return _deep_get(self._data, "defaults", key, default=fallback)

    def public_snapshot(self) -> dict[str, Any]:
        """Non-secret config for ``GET /config`` — safe to expose to agents."""
        return deepcopy(self._data)


def api_cfg() -> ApiConfig:
    return ApiConfig()


def enum_field_schema(key: str, *, fallback: list[str] | None = None) -> dict[str, Any]:
    """OpenAPI ``enum`` extra for Pydantic **body** Schema fields (not Ninja Query)."""
    return {"enum": api_cfg().enum(key, fallback=fallback)}


def query_enum_description(key: str, *, prefix: str = "", fallback: list[str] | None = None) -> str:
    """Swagger description for query params — Ninja Query does not accept json_schema_extra."""
    opts = api_cfg().enum(key, fallback=fallback)
    allowed = f"Allowed values (from API config): {', '.join(opts)}"
    return f"{prefix} {allowed}".strip() if prefix else allowed
