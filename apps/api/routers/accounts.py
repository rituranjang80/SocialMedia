"""``/api/v1/accounts/*`` — social accounts and OAuth connect helpers."""

from __future__ import annotations

import uuid

from django.conf import settings
from ninja import Query, Router
from ninja.errors import HttpError

from apps.api.deps import require_perm, resolve_account
from apps.api.limits import enforce_http_rate_limits
from apps.api.middleware import log_audit_entry
from apps.api.runtime_config import api_cfg, query_enum_description
from apps.api.schemas import AccountsListResponse, AccountSummary
from apps.api.schemas_domains import AccountDetailResponse, ConnectOptionsResponse, ConnectPlatformOption, ConnectUrlResponse
from apps.credentials.models import PlatformCredential
from apps.social_accounts.oauth_aliases import to_url_slug

router = Router(tags=["accounts"])


def _configured_platforms(org_id) -> set[str]:
    from providers import PROVIDER_REGISTRY
    from providers.types import AuthType

    configured = set(
        PlatformCredential.objects.for_org(org_id).filter(is_configured=True).values_list("platform", flat=True)
    )
    env_creds = getattr(settings, "PLATFORM_CREDENTIALS_FROM_ENV", {})
    for platform in PROVIDER_REGISTRY:
        if platform in ("bluesky", "mastodon"):
            configured.add(platform)
            continue
        creds = env_creds.get(platform) or {}
        if any(str(v).strip() for v in creds.values()):
            configured.add(platform)
    return configured


@router.get(
    "/",
    response=AccountsListResponse,
    summary="List the SocialAccounts this API key is allowed to act on",
)
def list_accounts(request):
    enforce_http_rate_limits(request, is_write=False)
    api_key = request.api_key
    accounts = [AccountSummary.from_social_account(sa) for sa in api_key.social_accounts.all()]
    log_audit_entry(request, action="accounts.list", target_id=None, status_code=200)
    return AccountsListResponse(accounts=accounts)


@router.get(
    "/connect/options",
    response=ConnectOptionsResponse,
    summary="List connectable platforms",
)
def connect_options(request):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "manage_social_accounts")
    workspace = request.workspace  # type: ignore[attr-defined]
    org_id = workspace.organization_id
    configured = _configured_platforms(org_id)
    methods = api_cfg().enum("oauth_connect_methods")
    platforms = []
    for value, label in PlatformCredential.Platform.choices:
        if value not in api_cfg().enum("platforms"):
            continue
        if value == PlatformCredential.Platform.BLUESKY:
            method = "bluesky"
        elif value == PlatformCredential.Platform.MASTODON:
            method = "mastodon"
        else:
            method = "oauth"
        if method not in methods:
            method = methods[0] if methods else "oauth"
        platforms.append(
            ConnectPlatformOption(
                platform=value,
                label=label,
                configured=value in configured,
                connect_method=method,
            )
        )
    log_audit_entry(request, action="accounts.connect.options", target_id=None, status_code=200)
    return ConnectOptionsResponse(platforms=platforms)


@router.get(
    "/connect/url",
    response=ConnectUrlResponse,
    summary="Get OAuth connect URL for a platform",
)
def connect_url(
    request,
    platform: str = Query(..., description=query_enum_description("platforms")),
):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "manage_social_accounts")
    workspace = request.workspace  # type: ignore[attr-defined]
    allowed = set(api_cfg().enum("platforms"))
    if platform not in allowed:
        raise HttpError(422, f"platform must be one of {sorted(allowed)}")

    base = settings.APP_URL.rstrip("/")
    ws_id = workspace.id

    if platform == PlatformCredential.Platform.BLUESKY:
        url = f"{base}/social-accounts/{ws_id}/connect/bluesky/"
        return ConnectUrlResponse(
            platform=platform,
            connect_url=url,
            method="bluesky",
            instructions="Open in a browser session to enter Bluesky app password credentials.",
        )
    if platform == PlatformCredential.Platform.MASTODON:
        url = f"{base}/social-accounts/{ws_id}/connect/mastodon/"
        return ConnectUrlResponse(
            platform=platform,
            connect_url=url,
            method="mastodon",
            instructions="Open in a browser session to register OAuth with your Mastodon instance.",
        )

    slug = to_url_slug(platform)
    url = f"{base}/social-accounts/{ws_id}/connect/?platform={slug}"
    log_audit_entry(request, action="accounts.connect.url", target_id=None, status_code=200)
    return ConnectUrlResponse(
        platform=platform,
        connect_url=url,
        method="oauth",
        instructions=(
            "Open this URL in a browser while logged in as a workspace member with "
            "manage_social_accounts permission. Complete the OAuth flow; the account "
            "will appear in GET /accounts/ after connection."
        ),
    )


@router.get("/{account_id}", response=AccountDetailResponse, summary="Get social account details")
def get_account(request, account_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=False)
    account = resolve_account(request, account_id)
    return AccountDetailResponse(
        id=account.id,
        platform=account.platform,
        account_name=account.account_name,
        account_handle=getattr(account, "account_handle", "") or "",
        connection_status=account.connection_status,
        analytics_needs_reconnect=bool(account.analytics_needs_reconnect),
        char_limit=account.char_limit,
        supports_first_comment=account.supports_first_comment(),
    )


@router.post("/{account_id}/disconnect", response={204: None}, summary="Disconnect a social account")
def disconnect_account(request, account_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "manage_social_accounts")
    account = resolve_account(request, account_id)
    account.connection_status = "disconnected"
    account.oauth_access_token = ""
    account.oauth_refresh_token = ""
    account.token_expires_at = None
    account.save(
        update_fields=[
            "connection_status",
            "oauth_access_token",
            "oauth_refresh_token",
            "token_expires_at",
            "updated_at",
        ]
    )
    log_audit_entry(request, action="accounts.disconnect", target_id=account.id, status_code=204)
    return 204, None
