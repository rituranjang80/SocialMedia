"""``/api/v1/calendar/*`` — events, queues, posting slots, custom events."""

from __future__ import annotations

import zoneinfo
from datetime import datetime

from django.shortcuts import get_object_or_404
from ninja import Query, Router
from ninja.errors import HttpError

from apps.api.deps import actor_user, require_perm, resolve_account
from apps.api.limits import enforce_http_rate_limits
from apps.api.middleware import log_audit_entry
from apps.api.runtime_config import api_cfg, query_enum_description
from apps.api.schemas_domains import (
    CalendarCustomEvent,
    CalendarEventsResponse,
    CalendarPlatformPostEvent,
    CustomEventCreateRequest,
    CustomEventResponse,
    PostingSlotResponse,
    PostingSlotsListResponse,
    QueueEntryRequest,
    QueueSummary,
    QueuesListResponse,
    RescheduleRequest,
)
from apps.calendar.models import CustomCalendarEvent, PostingSlot, Queue, QueueEntry
from apps.calendar.services import add_to_queue, remove_from_queue
from apps.composer.models import PlatformPost
from apps.composer.services import sync_post_scheduled_at

router = Router(tags=["calendar"])


@router.get("/events", response=CalendarEventsResponse, summary="List calendar events in a date range")
def list_events(
    request,
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    status: str | None = Query(None, description=query_enum_description("calendar_post_statuses")),
    platform: str | None = Query(None, description=query_enum_description("platforms")),
    include_custom_events: bool = Query(True),
):
    enforce_http_rate_limits(request, is_write=False)
    workspace = request.workspace  # type: ignore[attr-defined]
    try:
        start = datetime.fromisoformat(start_date).date()
        end = datetime.fromisoformat(end_date).date()
    except ValueError as exc:
        raise HttpError(422, "start_date and end_date must be YYYY-MM-DD.") from exc

    max_days = api_cfg().pagination("calendar_max_days", default=90)
    if (end - start).days > max_days:
        raise HttpError(422, f"Date range cannot exceed {max_days} days.")

    allowlist = {sa.id for sa in request.api_key.social_accounts.all()}  # type: ignore[attr-defined]
    pp_qs = (
        PlatformPost.objects.filter(
            post__workspace=workspace,
            social_account_id__in=allowlist,
            scheduled_at__date__gte=start,
            scheduled_at__date__lte=end,
        )
        .select_related("post", "social_account")
        .order_by("scheduled_at")
    )
    if status:
        pp_qs = pp_qs.filter(status=status)
    if platform:
        pp_qs = pp_qs.filter(social_account__platform=platform)

    platform_posts = [
        CalendarPlatformPostEvent(
            platform_post_id=pp.id,
            post_id=pp.post_id,
            social_account_id=pp.social_account_id,
            platform=pp.social_account.platform,
            account_name=pp.social_account.account_name,
            status=pp.status,
            scheduled_at=pp.scheduled_at,
            caption_snippet=(pp.effective_caption or pp.post.caption or "")[:120],
        )
        for pp in pp_qs
    ]

    custom_events: list[CalendarCustomEvent] = []
    if include_custom_events:
        for ev in CustomCalendarEvent.objects.filter(
            workspace=workspace,
            start_date__lte=end,
            end_date__gte=start,
        ):
            custom_events.append(
                CalendarCustomEvent(
                    id=ev.id,
                    title=ev.title,
                    description=ev.description,
                    start_date=ev.start_date,
                    end_date=ev.end_date,
                    color=ev.color,
                )
            )

    log_audit_entry(request, action="calendar.events.list", target_id=None, status_code=200)
    return CalendarEventsResponse(platform_posts=platform_posts, custom_events=custom_events)


@router.post("/reschedule", response={204: None}, summary="Reschedule a platform post")
def reschedule(request, body: RescheduleRequest):
    enforce_http_rate_limits(request, is_write=True)
    workspace = request.workspace  # type: ignore[attr-defined]
    pp = get_object_or_404(
        PlatformPost.objects.select_related("post"),
        id=body.platform_post_id,
        post__workspace=workspace,
    )
    resolve_account(request, pp.social_account_id)
    post = pp.post
    membership = request.workspace_membership  # type: ignore[attr-defined]
    perms = membership.effective_permissions if membership else {}
    is_own = post.author_id == request.api_key.issued_by_id  # type: ignore[attr-defined]
    if not (is_own or perms.get("edit_others_posts")):
        raise HttpError(403, "Permission denied: edit_others_posts")
    if pp.status not in ("draft", "approved", "scheduled"):
        raise HttpError(422, "Post cannot be rescheduled in its current status.")

    new_dt = body.new_datetime
    if new_dt.tzinfo is None:
        tz = zoneinfo.ZoneInfo(workspace.effective_timezone or "UTC")
        new_dt = new_dt.replace(tzinfo=tz)
    pp.scheduled_at = new_dt
    if pp.status == "draft":
        pp.transition_to("scheduled")
    pp.save(update_fields=["scheduled_at", "status", "updated_at"])
    sync_post_scheduled_at(post)
    log_audit_entry(request, action="calendar.reschedule", target_id=pp.id, status_code=204)
    return 204, None


@router.get("/queues", response=QueuesListResponse, summary="List publishing queues")
def list_queues(request):
    enforce_http_rate_limits(request, is_write=False)
    workspace = request.workspace  # type: ignore[attr-defined]
    allowlist = {sa.id for sa in request.api_key.social_accounts.all()}  # type: ignore[attr-defined]
    queues = Queue.objects.filter(workspace=workspace, social_account_id__in=allowlist).select_related(
        "social_account"
    )
    items = [
        QueueSummary(
            id=q.id,
            name=q.name,
            social_account_id=q.social_account_id,
            is_active=q.is_active,
            entry_count=q.entries.count(),
        )
        for q in queues
    ]
    log_audit_entry(request, action="calendar.queues.list", target_id=None, status_code=200)
    return QueuesListResponse(queues=items)


@router.post("/queues/{queue_id}/entries", response={201: dict}, summary="Add a post to a queue")
def add_queue_entry(request, queue_id, body: QueueEntryRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "create_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    queue = get_object_or_404(Queue, id=queue_id, workspace=workspace)
    resolve_account(request, queue.social_account_id)
    from apps.composer.models import Post

    post = get_object_or_404(Post, id=body.post_id, workspace=workspace)
    add_to_queue(post, queue, priority=body.priority)
    log_audit_entry(request, action="calendar.queue.add", target_id=post.id, status_code=201)
    return 201, {"post_id": str(post.id), "queue_id": str(queue.id)}


@router.delete("/queues/{queue_id}/entries/{entry_id}", response={204: None}, summary="Remove post from queue")
def remove_queue_entry(request, queue_id, entry_id):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "create_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    entry = get_object_or_404(QueueEntry, id=entry_id, queue_id=queue_id, queue__workspace=workspace)
    remove_from_queue(entry)
    log_audit_entry(request, action="calendar.queue.remove", target_id=entry.post_id, status_code=204)
    return 204, None


@router.get("/posting-slots", response=PostingSlotsListResponse, summary="List recurring posting slots")
def list_posting_slots(request, social_account_id: str | None = Query(None)):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "manage_social_accounts")
    workspace = request.workspace  # type: ignore[attr-defined]
    allowlist = {sa.id for sa in request.api_key.social_accounts.all()}  # type: ignore[attr-defined]
    qs = PostingSlot.objects.filter(social_account__workspace=workspace, social_account_id__in=allowlist)
    if social_account_id:
        qs = qs.filter(social_account_id=social_account_id)
    slots = [
        PostingSlotResponse(
            id=s.id,
            social_account_id=s.social_account_id,
            day_of_week=s.day_of_week,
            time=s.time.strftime("%H:%M"),
            is_active=s.is_active,
        )
        for s in qs.select_related("social_account")
    ]
    log_audit_entry(request, action="calendar.slots.list", target_id=None, status_code=200)
    return PostingSlotsListResponse(slots=slots)


@router.get("/custom-events", response=list[CustomEventResponse], summary="List custom calendar events")
def list_custom_events(request):
    enforce_http_rate_limits(request, is_write=False)
    workspace = request.workspace  # type: ignore[attr-defined]
    events = CustomCalendarEvent.objects.filter(workspace=workspace).order_by("start_date")
    return [
        CustomEventResponse(
            id=e.id,
            title=e.title,
            description=e.description,
            start_date=e.start_date,
            end_date=e.end_date,
            color=e.color,
        )
        for e in events
    ]


@router.post("/custom-events", response={201: CustomEventResponse}, summary="Create a custom calendar event")
def create_custom_event(request, body: CustomEventCreateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "create_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    ev = CustomCalendarEvent.objects.create(
        workspace=workspace,
        title=body.title,
        description=body.description,
        start_date=body.start_date,
        end_date=body.end_date,
        color=body.color,
        created_by=user,
    )
    log_audit_entry(request, action="calendar.event.create", target_id=ev.id, status_code=201)
    return 201, CustomEventResponse(
        id=ev.id,
        title=ev.title,
        description=ev.description,
        start_date=ev.start_date,
        end_date=ev.end_date,
        color=ev.color,
    )
