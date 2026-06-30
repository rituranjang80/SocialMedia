"""``/api/v1/organization/*``, ``/workspaces/*``, ``/members/*`` — org admin."""

from __future__ import annotations

import uuid

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.api.deps import actor_user, require_org_role, require_perm
from apps.api.limits import enforce_http_rate_limits
from apps.api.middleware import log_audit_entry
from apps.api.runtime_config import api_cfg
from apps.api.schemas_domains import (
    InvitationCreateRequest,
    InvitationResponse,
    MemberRoleUpdateRequest,
    MembersListResponse,
    MemberSummary,
    OrganizationResponse,
    OrganizationUpdateRequest,
    WorkspaceAssignmentsUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceDetailResponse,
    WorkspacesListResponse,
    WorkspaceSummary,
    WorkspaceUpdateRequest,
)
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.members.services import (
    create_invitation,
    remove_member,
    resend_invitation,
    revoke_invitation,
    update_member_org_role,
    update_workspace_assignments,
)
from apps.workspaces.models import Workspace

org_router = Router(tags=["organization"])
workspaces_router = Router(tags=["workspaces"])
members_router = Router(tags=["members"])


def _org(request):
    return request.api_key.workspace.organization  # type: ignore[attr-defined]


@org_router.get("/", response=OrganizationResponse, summary="Get current organization")
def get_organization(request):
    enforce_http_rate_limits(request, is_write=False)
    require_org_role(request, OrgMembership.OrgRole.MEMBER)
    org = _org(request)
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        default_timezone=org.default_timezone,
        billing_email=org.billing_email or "",
        deletion_scheduled_for=org.deletion_scheduled_for,
    )


@org_router.patch("/", response=OrganizationResponse, summary="Update organization settings")
def patch_organization(request, body: OrganizationUpdateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    updates = []
    if body.name is not None:
        org.name = body.name
        updates.append("name")
    if body.default_timezone is not None:
        org.default_timezone = body.default_timezone
        updates.append("default_timezone")
    if body.billing_email is not None:
        org.billing_email = body.billing_email
        updates.append("billing_email")
    if updates:
        org.save(update_fields=updates + ["updated_at"])
    log_audit_entry(request, action="organization.update", target_id=org.id, status_code=200)
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        default_timezone=org.default_timezone,
        billing_email=org.billing_email or "",
        deletion_scheduled_for=org.deletion_scheduled_for,
    )


@workspaces_router.get("/", response=WorkspacesListResponse, summary="List organization workspaces")
def list_workspaces(request):
    enforce_http_rate_limits(request, is_write=False)
    require_org_role(request, OrgMembership.OrgRole.MEMBER)
    org = _org(request)
    workspaces = Workspace.objects.filter(organization=org).order_by("name")
    return WorkspacesListResponse(
        workspaces=[
            WorkspaceSummary(
                id=w.id,
                name=w.name,
                is_archived=w.is_archived,
                approval_workflow_mode=w.approval_workflow_mode,
            )
            for w in workspaces
        ]
    )


@workspaces_router.post("/", response={201: WorkspaceDetailResponse}, summary="Create a workspace")
def create_workspace(request, body: WorkspaceCreateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    allowed_modes = set(api_cfg().enum("approval_workflow_modes"))
    if body.approval_workflow_mode not in allowed_modes:
        raise HttpError(422, f"approval_workflow_mode must be one of {sorted(allowed_modes)}")
    ws = Workspace.objects.create(
        organization=org,
        name=body.name,
        timezone=body.timezone,
        approval_workflow_mode=body.approval_workflow_mode,
    )
    user = actor_user(request)
    WorkspaceMembership.objects.create(
        user=user,
        workspace=ws,
        workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
    )
    log_audit_entry(request, action="workspaces.create", target_id=ws.id, status_code=201)
    return 201, _workspace_detail(ws)


@workspaces_router.get("/current", response=WorkspaceDetailResponse, summary="Get API key workspace")
def get_current_workspace(request):
    enforce_http_rate_limits(request, is_write=False)
    workspace = request.workspace  # type: ignore[attr-defined]
    return _workspace_detail(workspace)


@workspaces_router.patch("/current", response=WorkspaceDetailResponse, summary="Update API key workspace")
def patch_current_workspace(request, body: WorkspaceUpdateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "manage_workspace_settings")
    workspace = request.workspace  # type: ignore[attr-defined]
    if body.name is not None:
        workspace.name = body.name
    if body.description is not None:
        workspace.description = body.description
    if body.timezone is not None:
        workspace.timezone = body.timezone
    if body.default_hashtags is not None:
        workspace.default_hashtags = body.default_hashtags
    if body.default_first_comment is not None:
        workspace.default_first_comment = body.default_first_comment
    if body.primary_color is not None:
        workspace.primary_color = body.primary_color
    if body.secondary_color is not None:
        workspace.secondary_color = body.secondary_color
    workspace.save()
    log_audit_entry(request, action="workspaces.update", target_id=workspace.id, status_code=200)
    return _workspace_detail(workspace)


def _workspace_detail(ws: Workspace) -> WorkspaceDetailResponse:
    return WorkspaceDetailResponse(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        timezone=ws.timezone,
        effective_timezone=ws.effective_timezone,
        approval_workflow_mode=ws.approval_workflow_mode,
        default_hashtags=ws.default_hashtags or [],
        default_first_comment=ws.default_first_comment,
        primary_color=ws.primary_color,
        secondary_color=ws.secondary_color,
        is_archived=ws.is_archived,
    )


@members_router.get("/", response=MembersListResponse, summary="List organization members")
def list_members(request):
    enforce_http_rate_limits(request, is_write=False)
    require_org_role(request, OrgMembership.OrgRole.MEMBER)
    org = _org(request)
    memberships = OrgMembership.objects.filter(organization=org).select_related("user")
    return MembersListResponse(
        members=[
            MemberSummary(
                membership_id=m.id,
                user_id=m.user_id,
                email=m.user.email,
                display_name=getattr(m.user, "display_name", m.user.email),
                org_role=m.org_role,
            )
            for m in memberships
        ]
    )


@members_router.post("/invitations", response={201: InvitationResponse}, summary="Invite a team member")
def invite_member(request, body: InvitationCreateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    user = actor_user(request)
    allowed_org = set(api_cfg().enum("org_roles_invitable"))
    if body.org_role not in allowed_org:
        raise HttpError(422, f"org_role must be one of {sorted(allowed_org)}")
    try:
        inv = create_invitation(
            org,
            body.email,
            body.org_role,
            body.workspace_assignments,
            invited_by=user,
            inviter=user,
        )
    except ValueError as exc:
        raise HttpError(422, str(exc)) from exc
    log_audit_entry(request, action="members.invite", target_id=inv.id, status_code=201)
    return 201, InvitationResponse(
        id=inv.id,
        email=inv.email,
        org_role=inv.org_role,
        expires_at=inv.expires_at,
    )


@members_router.post("/invitations/{invitation_id}/resend", response={204: None}, summary="Resend invitation")
def resend_invite(request, invitation_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    from apps.members.models import Invitation

    inv = get_object_or_404(Invitation, id=invitation_id, organization=org)
    resend_invitation(inv)
    return 204, None


@members_router.delete("/invitations/{invitation_id}", response={204: None}, summary="Revoke invitation")
def revoke_invite(request, invitation_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    from apps.members.models import Invitation

    inv = get_object_or_404(Invitation, id=invitation_id, organization=org)
    revoke_invitation(inv)
    return 204, None


@members_router.patch("/{membership_id}/org-role", response={204: None}, summary="Update member org role")
def update_org_role(request, membership_id: uuid.UUID, body: MemberRoleUpdateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    membership = get_object_or_404(OrgMembership, id=membership_id, organization=org)
    allowed = set(api_cfg().enum("org_roles_invitable"))
    if body.org_role not in allowed and body.org_role != OrgMembership.OrgRole.OWNER:
        raise HttpError(422, f"org_role must be one of {sorted(allowed | {OrgMembership.OrgRole.OWNER})}")
    try:
        update_member_org_role(org, membership, body.org_role, caller=actor_user(request))
    except ValueError as exc:
        raise HttpError(422, str(exc)) from exc
    return 204, None


@members_router.patch("/{membership_id}/workspaces", response={204: None}, summary="Update workspace assignments")
def patch_workspace_assignments(request, membership_id: uuid.UUID, body: WorkspaceAssignmentsUpdateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    membership = get_object_or_404(OrgMembership, id=membership_id, organization=org)
    assignments = [{"workspace_id": str(a.workspace_id), "role": a.role} for a in body.assignments]
    try:
        update_workspace_assignments(org, membership.user, assignments, inviter=actor_user(request))
    except ValueError as exc:
        raise HttpError(422, str(exc)) from exc
    return 204, None


@members_router.delete("/{membership_id}", response={204: None}, summary="Remove member from organization")
def delete_member(request, membership_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=True)
    require_org_role(request, OrgMembership.OrgRole.ADMIN)
    org = _org(request)
    membership = get_object_or_404(OrgMembership, id=membership_id, organization=org)
    try:
        remove_member(org, membership, actor_user(request))
    except ValueError as exc:
        raise HttpError(422, str(exc)) from exc
    return 204, None
