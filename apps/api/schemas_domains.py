"""Pydantic schemas for extended Agent API domains (calendar, inbox, approvals, org).

Enum dropdowns in Swagger are driven by ``config/api_defaults.json`` (or
``API_CONFIG_PATH``) via ``apps.api.runtime_config``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from ninja import Field, Schema
from pydantic import field_validator

from apps.api.runtime_config import api_cfg, enum_field_schema


def _cfg_enum(key: str, *, fallback: list[str] | None = None, description: str = "") -> Any:
    opts = api_cfg().enum(key, fallback=fallback)
    desc = description or f"Configurable enum — edit API config file. Options: {', '.join(opts)}"
    return Field(..., description=desc, json_schema_extra={"enum": opts})


def _cfg_enum_optional(key: str, *, fallback: list[str] | None = None, description: str = "") -> Any:
    opts = api_cfg().enum(key, fallback=fallback)
    desc = description or f"Optional filter. Configurable via API config. Options: {', '.join(opts)}"
    return Field(None, description=desc, json_schema_extra={"enum": opts})


# ---------------------------------------------------------------------------
# Config (public snapshot)
# ---------------------------------------------------------------------------


class ApiConfigResponse(Schema):
    """Runtime API configuration (dropdowns, defaults, pagination). No secrets."""

    pagination: dict[str, int]
    defaults: dict[str, Any]
    enums: dict[str, list[str]]


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


class CalendarEventsQuery(Schema):
    start_date: dt.date = Field(..., description="Inclusive range start (YYYY-MM-DD).")
    end_date: dt.date = Field(..., description="Inclusive range end (YYYY-MM-DD).")
    status: str | None = Field(
        None,
        description="Filter scheduled posts by platform-post status.",
        json_schema_extra=enum_field_schema("calendar_post_statuses"),
    )
    platform: str | None = Field(
        None,
        description="Filter by social platform slug.",
        json_schema_extra=enum_field_schema("platforms"),
    )
    include_custom_events: bool = Field(
        True,
        description="Include workspace custom calendar events.",
    )


class CalendarPlatformPostEvent(Schema):
    platform_post_id: uuid.UUID
    post_id: uuid.UUID
    social_account_id: uuid.UUID
    platform: str
    account_name: str
    status: str
    scheduled_at: dt.datetime | None
    caption_snippet: str = ""


class CalendarCustomEvent(Schema):
    id: uuid.UUID
    title: str
    description: str
    start_date: dt.date
    end_date: dt.date
    color: str


class CalendarEventsResponse(Schema):
    platform_posts: list[CalendarPlatformPostEvent]
    custom_events: list[CalendarCustomEvent]


class RescheduleRequest(Schema):
    platform_post_id: uuid.UUID
    new_datetime: dt.datetime = Field(..., description="ISO 8601 datetime in workspace timezone or UTC.")


class QueueSummary(Schema):
    id: uuid.UUID
    name: str
    social_account_id: uuid.UUID
    is_active: bool
    entry_count: int


class QueuesListResponse(Schema):
    queues: list[QueueSummary]


class QueueEntryRequest(Schema):
    post_id: uuid.UUID
    priority: bool = Field(False, description="If true, jump to the front of the queue.")


class PostingSlotResponse(Schema):
    id: uuid.UUID
    social_account_id: uuid.UUID
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday … 6=Sunday")
    time: str
    is_active: bool


class PostingSlotsListResponse(Schema):
    slots: list[PostingSlotResponse]


class CustomEventCreateRequest(Schema):
    title: str = Field(..., max_length=200)
    description: str = ""
    start_date: dt.date
    end_date: dt.date
    color: str = Field("#3B82F6", pattern=r"^#[0-9A-Fa-f]{6}$")


class CustomEventResponse(CustomEventCreateRequest):
    id: uuid.UUID


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


class InboxMessageSummary(Schema):
    id: uuid.UUID
    social_account_id: uuid.UUID
    platform: str
    message_type: str
    sender_name: str
    sender_handle: str
    body_snippet: str
    sentiment: str
    status: str
    assigned_to_id: uuid.UUID | None
    received_at: dt.datetime


class InboxMessagesResponse(Schema):
    items: list[InboxMessageSummary]
    limit: int


class InboxReplyRequest(Schema):
    body: str = Field(..., min_length=1, max_length=10000)


class InboxNoteRequest(Schema):
    body: str = Field(..., min_length=1, max_length=10000)


class InboxMessagePatchRequest(Schema):
    status: str | None = Field(
        None,
        json_schema_extra=enum_field_schema("inbox_statuses"),
    )
    sentiment: str | None = Field(
        None,
        json_schema_extra=enum_field_schema("inbox_sentiments"),
    )
    assigned_to_user_id: uuid.UUID | None = None


class InboxBulkRequest(Schema):
    message_ids: list[uuid.UUID] = Field(..., min_length=1)
    action: str = Field(..., json_schema_extra=enum_field_schema("inbox_bulk_actions"))
    assign_to_user_id: uuid.UUID | None = Field(
        None,
        description="Required when action is ``assign``.",
    )


class SavedReplyResponse(Schema):
    id: uuid.UUID
    title: str
    body: str


class SavedReplyCreateRequest(Schema):
    title: str = Field(..., max_length=100)
    body: str = Field(..., max_length=10000)


class SLAConfigResponse(Schema):
    target_response_minutes: int
    is_active: bool
    auto_resolve_on_reply: bool


class SLAConfigUpdateRequest(Schema):
    target_response_minutes: int = Field(60, ge=5, le=10080)
    is_active: bool = True
    auto_resolve_on_reply: bool = False


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


class ApprovalQueueItem(Schema):
    post_id: uuid.UUID
    title: str
    caption_snippet: str
    statuses: list[str]
    submitted_at: dt.datetime | None


class ApprovalQueueResponse(Schema):
    items: list[ApprovalQueueItem]


class ApprovalCommentRequest(Schema):
    body: str = Field(..., min_length=1, max_length=5000)
    visibility: str = Field("internal", description="``internal`` or ``client``.")


class ApprovalActionRequest(Schema):
    comment: str = Field("", max_length=5000, description="Required for reject and request-changes.")


class BulkApprovalRequest(Schema):
    post_ids: list[uuid.UUID] = Field(..., min_length=1)
    comment: str = Field("", max_length=5000)


class BulkApprovalResult(Schema):
    post_id: uuid.UUID
    success: bool
    error: str | None = None


class BulkApprovalResponse(Schema):
    results: list[BulkApprovalResult]


class ApprovalSettingsResponse(Schema):
    approval_workflow_mode: str = Field(
        ...,
        json_schema_extra=enum_field_schema("approval_workflow_modes"),
    )


class ApprovalSettingsUpdateRequest(Schema):
    approval_workflow_mode: str = Field(
        ...,
        json_schema_extra=enum_field_schema("approval_workflow_modes"),
    )

    @field_validator("approval_workflow_mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        allowed = set(api_cfg().enum("approval_workflow_modes"))
        if v not in allowed:
            raise ValueError(f"approval_workflow_mode must be one of {sorted(allowed)}")
        return v


# ---------------------------------------------------------------------------
# Organization / workspace / members
# ---------------------------------------------------------------------------


class OrganizationResponse(Schema):
    id: uuid.UUID
    name: str
    default_timezone: str
    billing_email: str
    deletion_scheduled_for: dt.datetime | None


class OrganizationUpdateRequest(Schema):
    name: str | None = Field(None, max_length=100)
    default_timezone: str | None = Field(None, max_length=63)
    billing_email: str | None = None


class WorkspaceSummary(Schema):
    id: uuid.UUID
    name: str
    is_archived: bool
    approval_workflow_mode: str


class WorkspacesListResponse(Schema):
    workspaces: list[WorkspaceSummary]


class WorkspaceCreateRequest(Schema):
    name: str = Field(..., max_length=100)
    timezone: str = ""
    approval_workflow_mode: str = Field(
        "none",
        json_schema_extra=enum_field_schema("approval_workflow_modes"),
    )


class WorkspaceUpdateRequest(Schema):
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)
    timezone: str | None = None
    default_hashtags: list[str] | None = None
    default_first_comment: str | None = None
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class WorkspaceDetailResponse(Schema):
    id: uuid.UUID
    name: str
    description: str
    timezone: str
    effective_timezone: str
    approval_workflow_mode: str
    default_hashtags: list[str]
    default_first_comment: str
    primary_color: str
    secondary_color: str
    is_archived: bool


class MemberSummary(Schema):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    org_role: str


class MembersListResponse(Schema):
    members: list[MemberSummary]


class InvitationCreateRequest(Schema):
    email: str
    org_role: str = Field(
        default_factory=lambda: str(api_cfg().default("invitation_org_role", fallback="member")),
        json_schema_extra=enum_field_schema("org_roles_invitable"),
    )
    workspace_assignments: list[dict[str, str]] = Field(
        default_factory=list,
        description='List of {"workspace_id": "uuid", "role": "editor"} objects.',
    )


class InvitationResponse(Schema):
    id: uuid.UUID
    email: str
    org_role: str
    expires_at: dt.datetime


class MemberRoleUpdateRequest(Schema):
    org_role: str = Field(..., json_schema_extra=enum_field_schema("org_roles_invitable"))


class WorkspaceAssignmentItem(Schema):
    workspace_id: uuid.UUID
    role: str = Field(..., json_schema_extra=enum_field_schema("workspace_roles_invitable"))


class WorkspaceAssignmentsUpdateRequest(Schema):
    assignments: list[WorkspaceAssignmentItem]


# ---------------------------------------------------------------------------
# OAuth / social accounts (connect)
# ---------------------------------------------------------------------------


class AccountDetailResponse(Schema):
    id: uuid.UUID
    platform: str
    account_name: str
    account_handle: str
    connection_status: str
    analytics_needs_reconnect: bool
    char_limit: int
    supports_first_comment: bool


class ConnectPlatformOption(Schema):
    platform: str
    label: str
    configured: bool
    connect_method: str = Field(..., json_schema_extra=enum_field_schema("oauth_connect_methods"))


class ConnectOptionsResponse(Schema):
    platforms: list[ConnectPlatformOption]


class ConnectUrlResponse(Schema):
    platform: str
    connect_url: str
    method: str
    instructions: str
