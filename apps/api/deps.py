"""Shared dependencies for Agent API routers."""

from __future__ import annotations

import uuid

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from apps.composer.models import Post
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.social_accounts.models import SocialAccount

ORG_ROLE_LEVEL = {
    OrgMembership.OrgRole.OWNER: 3,
    OrgMembership.OrgRole.ADMIN: 2,
    OrgMembership.OrgRole.MEMBER: 1,
}


def require_perm(request: HttpRequest, key: str) -> None:
    membership = getattr(request, "workspace_membership", None)
    if membership is None or not membership.effective_permissions.get(key, False):
        raise HttpError(403, f"Permission denied: {key}")


def require_org_role(request: HttpRequest, minimum: str) -> OrgMembership:
    """Require the API key issuer to hold at least ``minimum`` org role."""
    api_key = request.api_key  # type: ignore[attr-defined]
    if api_key.issued_by_id is None:
        raise HttpError(403, "Organization action requires a user-issued API key.")
    org = api_key.workspace.organization
    membership = OrgMembership.objects.filter(user_id=api_key.issued_by_id, organization=org).first()
    if membership is None:
        raise HttpError(403, "Issuer is not a member of this organization.")
    need = ORG_ROLE_LEVEL.get(minimum, 0)
    have = ORG_ROLE_LEVEL.get(membership.org_role, 0)
    if have < need:
        raise HttpError(403, f"Organization role '{minimum}' or higher required.")
    return membership


def actor_user(request: HttpRequest):
    """User performing the action (API key issuer)."""
    api_key = request.api_key  # type: ignore[attr-defined]
    if api_key.issued_by_id is None:
        raise HttpError(403, "This action requires a user-issued API key.")
    return api_key.issued_by


def resolve_account(request: HttpRequest, social_account_id: uuid.UUID) -> SocialAccount:
    api_key = request.api_key  # type: ignore[attr-defined]
    allowlist_ids = {sa.id for sa in api_key.social_accounts.all()}
    if social_account_id not in allowlist_ids:
        raise HttpError(403, "SocialAccount is not in this key's allowlist.")
    return SocialAccount.objects.get(id=social_account_id)


def get_workspace_post(request: HttpRequest, post_id: uuid.UUID) -> Post:
    api_key = request.api_key  # type: ignore[attr-defined]
    workspace = request.workspace  # type: ignore[attr-defined]
    allowlist_ids = {sa.id for sa in api_key.social_accounts.all()}
    post = get_object_or_404(Post, id=post_id, workspace=workspace)
    child_account_ids = set(post.platform_posts.values_list("social_account_id", flat=True))
    if not child_account_ids or not child_account_ids.issubset(allowlist_ids):
        raise HttpError(404, "Not found.")
    return post
