"""``/api/v1/approvals/*`` — approval workflow."""

from __future__ import annotations

import uuid

from django.db.models import Max
from ninja import Router
from ninja.errors import HttpError

from apps.api.deps import actor_user, get_workspace_post, require_perm
from apps.api.limits import enforce_http_rate_limits
from apps.api.middleware import log_audit_entry
from apps.api.routers.posts import _post_to_response
from apps.api.schemas import PostResponse
from apps.api.schemas_domains import (
    ApprovalActionRequest,
    ApprovalQueueItem,
    ApprovalQueueResponse,
    ApprovalSettingsResponse,
    ApprovalSettingsUpdateRequest,
    BulkApprovalRequest,
    BulkApprovalResponse,
    BulkApprovalResult,
)
from apps.approvals.services import (
    approve_post,
    bulk_approve,
    bulk_reject,
    reject_post,
    request_changes,
    resubmit_post,
    submit_for_review,
)
from apps.composer.models import Post

router = Router(tags=["approvals"])


@router.get("/queue", response=ApprovalQueueResponse, summary="List posts pending approval")
def approval_queue(request):
    enforce_http_rate_limits(request, is_write=False)
    require_perm(request, "approve_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    allowlist = {sa.id for sa in request.api_key.social_accounts.all()}  # type: ignore[attr-defined]
    posts = (
        Post.objects.filter(
            workspace=workspace,
            platform_posts__status__in=["pending_review", "pending_client"],
            platform_posts__social_account_id__in=allowlist,
        )
        .distinct()
        .prefetch_related("platform_posts")
        .annotate(latest=Max("platform_posts__updated_at"))
        .order_by("-latest")[:50]
    )
    items = []
    for post in posts:
        statuses = list(post.platform_posts.values_list("status", flat=True).distinct())
        items.append(
            ApprovalQueueItem(
                post_id=post.id,
                title=post.title or "",
                caption_snippet=(post.caption or "")[:120],
                statuses=statuses,
                submitted_at=post.updated_at,
            )
        )
    log_audit_entry(request, action="approvals.queue", target_id=None, status_code=200)
    return ApprovalQueueResponse(items=items)


@router.post("/posts/{post_id}/submit", response=PostResponse, summary="Submit post for review")
def submit(request, post_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "create_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    post = get_workspace_post(request, post_id)
    submit_for_review(post, user, workspace)
    post.refresh_from_db()
    log_audit_entry(request, action="approvals.submit", target_id=post.id, status_code=200)
    return _post_to_response(request, post)


@router.post("/posts/{post_id}/approve", response=PostResponse, summary="Approve a post")
def approve(request, post_id: uuid.UUID, body: ApprovalActionRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "approve_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    post = get_workspace_post(request, post_id)
    approve_post(post, user, workspace, comment=body.comment)
    post.refresh_from_db()
    log_audit_entry(request, action="approvals.approve", target_id=post.id, status_code=200)
    return _post_to_response(request, post)


@router.post("/posts/{post_id}/request-changes", response=PostResponse, summary="Request changes on a post")
def request_changes_view(request, post_id: uuid.UUID, body: ApprovalActionRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "approve_posts")
    if not body.comment.strip():
        raise HttpError(422, "comment is required when requesting changes")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    post = get_workspace_post(request, post_id)
    try:
        request_changes(post, user, workspace, body.comment)
    except ValueError as exc:
        raise HttpError(422, str(exc)) from exc
    post.refresh_from_db()
    log_audit_entry(request, action="approvals.request_changes", target_id=post.id, status_code=200)
    return _post_to_response(request, post)


@router.post("/posts/{post_id}/reject", response=PostResponse, summary="Reject a post")
def reject(request, post_id: uuid.UUID, body: ApprovalActionRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "approve_posts")
    if not body.comment.strip():
        raise HttpError(422, "comment is required when rejecting")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    post = get_workspace_post(request, post_id)
    try:
        reject_post(post, user, workspace, body.comment)
    except ValueError as exc:
        raise HttpError(422, str(exc)) from exc
    post.refresh_from_db()
    log_audit_entry(request, action="approvals.reject", target_id=post.id, status_code=200)
    return _post_to_response(request, post)


@router.post("/posts/{post_id}/resubmit", response=PostResponse, summary="Resubmit after changes")
def resubmit(request, post_id: uuid.UUID):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "create_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    post = get_workspace_post(request, post_id)
    resubmit_post(post, user, workspace)
    post.refresh_from_db()
    log_audit_entry(request, action="approvals.resubmit", target_id=post.id, status_code=200)
    return _post_to_response(request, post)


@router.post("/bulk/approve", response=BulkApprovalResponse, summary="Bulk approve posts")
def bulk_approve_view(request, body: BulkApprovalRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "approve_posts")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    raw = bulk_approve(body.post_ids, user, workspace)
    results = [BulkApprovalResult(post_id=uuid.UUID(pid), success=ok, error=err) for pid, ok, err in raw]
    return BulkApprovalResponse(results=results)


@router.post("/bulk/reject", response=BulkApprovalResponse, summary="Bulk reject posts")
def bulk_reject_view(request, body: BulkApprovalRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "approve_posts")
    if not body.comment.strip():
        raise HttpError(422, "comment is required for bulk rejection")
    workspace = request.workspace  # type: ignore[attr-defined]
    user = actor_user(request)
    try:
        raw = bulk_reject(body.post_ids, user, workspace, body.comment)
    except ValueError as exc:
        raise HttpError(422, str(exc)) from exc
    results = [BulkApprovalResult(post_id=uuid.UUID(pid), success=ok, error=err) for pid, ok, err in raw]
    return BulkApprovalResponse(results=results)


@router.get("/settings", response=ApprovalSettingsResponse, summary="Read approval workflow mode")
def get_approval_settings(request):
    enforce_http_rate_limits(request, is_write=False)
    workspace = request.workspace  # type: ignore[attr-defined]
    return ApprovalSettingsResponse(approval_workflow_mode=workspace.approval_workflow_mode)


@router.put("/settings", response=ApprovalSettingsResponse, summary="Update approval workflow mode")
def update_approval_settings(request, body: ApprovalSettingsUpdateRequest):
    enforce_http_rate_limits(request, is_write=True)
    require_perm(request, "manage_workspace_settings")
    workspace = request.workspace  # type: ignore[attr-defined]
    workspace.approval_workflow_mode = body.approval_workflow_mode
    workspace.save(update_fields=["approval_workflow_mode", "updated_at"])
    log_audit_entry(request, action="approvals.settings", target_id=workspace.id, status_code=200)
    return ApprovalSettingsResponse(approval_workflow_mode=workspace.approval_workflow_mode)
