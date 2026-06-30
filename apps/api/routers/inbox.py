"""``/api/v1/inbox/*`` — unified social inbox."""

from __future__ import annotations

import logging
import uuid

from django.shortcuts import get_object_or_404
from ninja import Query, Router
from ninja.errors import HttpError

from apps.api.deps import actor_user, require_perm
from apps.api.limits import enforce_http_rate_limits
from apps.api.middleware import log_audit_entry
from apps.api.runtime_config import api_cfg, query_enum_description
from apps.api.schemas_domains import (
    InboxBulkRequest,
    InboxMessagePatchRequest,
    InboxMessageSummary,
    InboxMessagesResponse,
    InboxNoteRequest,
    InboxReplyRequest,
    SavedReplyCreateRequest,
    SavedReplyResponse,
    SLAConfigResponse,
    SLAConfigUpdateRequest,
)
from apps.inbox.models import InboxMessage, InboxReply, InboxSLAConfig, InternalNote, SavedReply
from apps.members.models import WorkspaceMembership
from providers import get_provider

logger = logging.getLogger(__name__)

router = Router(tags=["inbox"])


def _message_summary(msg: InboxMessage) -> InboxMessageSummary:
    return InboxMessageSummary(
        id=msg.id,
        social_account_id=msg.social_account_id,
        platform=msg.social_account.platform,
        message_type=msg.message_type,
        sender_name=msg.sender_name,
        sender_handle=msg.sender_handle,
        body_snippet=(msg.body or "")[:200],
        sentiment=msg.sentiment,
        status=msg.status,
        assigned_to_id=msg.assigned_to_id,
        received_at=msg.received_at,
    )


@router.get("/messages", response=InboxMessagesResponse, summary="List inbox messages")
def list_messages(
    request,
    view: str = Query("all", description=query_enum_description("inbox_views")),
    status: str | None = Query(None, description=query_enum_description("inbox_statuses")),
    message_type: str | None = Query(None, description=query_enum_description("inbox_message_types")),
    sentiment: str | None = Query(None, description=query_enum_description("inbox_sentiments")),
    limit: int = Query(50, ge=1),
):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "use_inbox")
    workspace = request.workspace  # type: ignore[attr-defined]
    max_limit = api_cfg().pagination("inbox_max_limit", default=100)
    default_limit = api_cfg().pagination("inbox_default_limit", default=50)
    if limit == 50:
        limit = default_limit
    limit = min(max(1, limit), max_limit)

    qs = InboxMessage.objects.for_workspace(workspace.id).select_related("social_account", "assigned_to")
    user = actor_user(request)
    if view == "mine":
        qs = qs.filter(assigned_to=user)
    elif view == "unassigned":
        qs = qs.filter(assigned_to__isnull=True)
    if status:
        qs = qs.filter(status=status)
    if message_type:
        qs = qs.filter(message_type=message_type)
    if sentiment:
        qs = qs.filter(sentiment=sentiment)

    items = [_message_summary(m) for m in qs.order_by("-received_at")[:limit]]
    log_audit_entry(request, action="inbox.messages.list", target_id=None, status_code=200)
    return InboxMessagesResponse(items=items, limit=limit)


@router.get("/messages/{message_id}", response=InboxMessageSummary, summary="Get a single inbox message")
def get_message(request, message_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "use_inbox")
    workspace = request.workspace  # type: ignore[attr-defined]
    msg = get_object_or_404(
        InboxMessage.objects.select_related("social_account"),
        id=message_id,
        workspace=workspace,
    )
    log_audit_entry(request, action="inbox.messages.read", target_id=msg.id, status_code=200)
    return _message_summary(msg)


@router.post("/messages/{message_id}/reply", response={201: dict}, summary="Reply to an inbox message")
def reply_to_message(request, message_id: uuid.UUID, body: InboxReplyRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "reply_from_inbox")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    message = get_object_or_404(InboxMessage, id=message_id, workspace=workspace)
    account = message.social_account
    platform_reply_id = ""
    try:
        from apps.publisher.engine import _resolve_publish_credentials

        provider = get_provider(account.platform, _resolve_publish_credentials(account))
        result = provider.reply_to_message(
            access_token=account.oauth_access_token,
            message_id=message.platform_message_id,
            text=body.body,
            extra=message.extra,
        )
        platform_reply_id = result.platform_message_id
    except NotImplementedError:
        logger.info("Provider %s does not support reply_to_message.", account.platform)
    except Exception:
        logger.exception("Failed to send inbox reply for %s", message.id)

    reply = InboxReply.objects.create(
        inbox_message=message,
        author=user,
        body=body.body,
        platform_reply_id=platform_reply_id,
    )
    sla = InboxSLAConfig.objects.filter(workspace=workspace, is_active=True).first()
    if sla and sla.auto_resolve_on_reply:
        message.status = InboxMessage.Status.RESOLVED
    elif message.status == InboxMessage.Status.UNREAD:
        message.status = InboxMessage.Status.OPEN
    message.save(update_fields=["status"])
    log_audit_entry(request, action="inbox.reply", target_id=message.id, status_code=201)
    return 201, {"reply_id": str(reply.id)}


@router.post("/messages/{message_id}/notes", response={201: dict}, summary="Add internal note")
def add_note(request, message_id: uuid.UUID, body: InboxNoteRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "reply_from_inbox")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    message = get_object_or_404(InboxMessage, id=message_id, workspace=workspace)
    note = InternalNote.objects.create(inbox_message=message, author=user, body=body.body)
    log_audit_entry(request, action="inbox.note", target_id=message.id, status_code=201)
    return 201, {"note_id": str(note.id)}


@router.patch("/messages/{message_id}", response=InboxMessageSummary, summary="Update status, sentiment, or assignee")
def patch_message(request, message_id: uuid.UUID, body: InboxMessagePatchRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "reply_from_inbox")
    workspace = request.workspace  # type: ignore[attr-defined]
    message = get_object_or_404(InboxMessage.objects.select_related("social_account"), id=message_id, workspace=workspace)
    updates = []
    if body.status is not None:
        allowed = set(api_cfg().enum("inbox_statuses"))
        if body.status not in allowed:
            raise HttpError(422, f"status must be one of {sorted(allowed)}")
        message.status = body.status
        updates.append("status")
    if body.sentiment is not None:
        allowed = set(api_cfg().enum("inbox_sentiments"))
        if body.sentiment not in allowed:
            raise HttpError(422, f"sentiment must be one of {sorted(allowed)}")
        message.sentiment = body.sentiment
        message.sentiment_source = InboxMessage.SentimentSource.MANUAL
        updates.extend(["sentiment", "sentiment_source"])
    if body.assigned_to_user_id is not None:
        if not WorkspaceMembership.objects.filter(workspace=workspace, user_id=body.assigned_to_user_id).exists():
            raise HttpError(422, "assignee is not a workspace member")
        message.assigned_to_id = body.assigned_to_user_id
        updates.append("assigned_to")
    if updates:
        message.save(update_fields=updates)
    log_audit_entry(request, action="inbox.patch", target_id=message.id, status_code=200)
    return _message_summary(message)


@router.post("/messages/bulk", response={200: dict}, summary="Bulk inbox actions")
def bulk_action(request, body: InboxBulkRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "reply_from_inbox")
    workspace = request.workspace  # type: ignore[attr-defined]
    allowed_actions = set(api_cfg().enum("inbox_bulk_actions"))
    if body.action not in allowed_actions:
        raise HttpError(422, f"action must be one of {sorted(allowed_actions)}")
    qs = InboxMessage.objects.filter(id__in=body.message_ids, workspace=workspace)
    count = 0
    if body.action == "mark_read":
        count = qs.filter(status=InboxMessage.Status.UNREAD).update(status=InboxMessage.Status.OPEN)
    elif body.action == "resolve":
        count = qs.exclude(status=InboxMessage.Status.ARCHIVED).update(status=InboxMessage.Status.RESOLVED)
    elif body.action == "archive":
        count = qs.update(status=InboxMessage.Status.ARCHIVED)
    elif body.action == "assign":
        if not body.assign_to_user_id:
            raise HttpError(422, "assign_to_user_id required for assign action")
        if not WorkspaceMembership.objects.filter(workspace=workspace, user_id=body.assign_to_user_id).exists():
            raise HttpError(422, "assignee is not a workspace member")
        count = qs.update(assigned_to_id=body.assign_to_user_id)
    log_audit_entry(request, action="inbox.bulk", target_id=None, status_code=200)
    return {"updated": count}


@router.get("/saved-replies", response=list[SavedReplyResponse], summary="List saved replies")
def list_saved_replies(request):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "manage_workspace_settings")
    workspace = request.workspace  # type: ignore[attr-defined]
    return [
        SavedReplyResponse(id=r.id, title=r.title, body=r.body)
        for r in SavedReply.objects.for_workspace(workspace.id)
    ]


@router.post("/saved-replies", response={201: SavedReplyResponse}, summary="Create saved reply")
def create_saved_reply(request, body: SavedReplyCreateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "manage_workspace_settings")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    reply = SavedReply.objects.create(
        workspace=workspace,
        title=body.title,
        body=body.body,
        created_by=user,
    )
    return 201, SavedReplyResponse(id=reply.id, title=reply.title, body=reply.body)


@router.get("/sla-config", response=SLAConfigResponse, summary="Get inbox SLA configuration")
def get_sla_config(request):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "manage_workspace_settings")
    workspace = request.workspace  # type: ignore[attr-defined]
    cfg, _ = InboxSLAConfig.objects.get_or_create(workspace=workspace)
    return SLAConfigResponse(
        target_response_minutes=cfg.target_response_minutes,
        is_active=cfg.is_active,
        auto_resolve_on_reply=cfg.auto_resolve_on_reply,
    )


@router.put("/sla-config", response=SLAConfigResponse, summary="Update inbox SLA configuration")
def update_sla_config(request, body: SLAConfigUpdateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "manage_workspace_settings")
    workspace = request.workspace  # type: ignore[attr-defined]
    cfg, _ = InboxSLAConfig.objects.get_or_create(workspace=workspace)
    cfg.target_response_minutes = body.target_response_minutes
    cfg.is_active = body.is_active
    cfg.auto_resolve_on_reply = body.auto_resolve_on_reply
    cfg.save()
    return SLAConfigResponse(
        target_response_minutes=cfg.target_response_minutes,
        is_active=cfg.is_active,
        auto_resolve_on_reply=cfg.auto_resolve_on_reply,
    )
