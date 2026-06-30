"""Public system endpoints — no API key required."""

from __future__ import annotations

from ninja import Router

from apps.api.schemas import HealthResponse

router = Router(tags=["system"])


@router.get(
    "/health",
    response=HealthResponse,
    summary="Liveness probe (no authentication)",
    auth=None,
)
def health(request):
    """Same payload as ``GET /health/`` but listed in the Agent API OpenAPI spec."""
    return HealthResponse(status="ok")
