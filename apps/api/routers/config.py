"""``GET /api/v1/config`` — public runtime API configuration snapshot."""

from __future__ import annotations

from ninja import Router

from apps.api.runtime_config import api_cfg
from apps.api.schemas_domains import ApiConfigResponse

router = Router(tags=["config"])


@router.get(
    "/",
    response=ApiConfigResponse,
    summary="Read runtime API config (dropdowns, defaults, pagination)",
    auth=None,
)
def get_config(request):
    """Returns the merged API config used for Swagger enums and defaults.

    Edit ``config/api_defaults.json`` or set ``API_CONFIG_PATH`` to a mounted
    file, then restart the app container — no image rebuild required.
    """
    snap = api_cfg().public_snapshot()
    return ApiConfigResponse(
        pagination=snap.get("pagination", {}),
        defaults=snap.get("defaults", {}),
        enums=snap.get("enums", {}),
    )
