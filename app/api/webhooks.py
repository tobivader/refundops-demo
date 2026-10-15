"""Learning endpoints and the GitHub webhook receiver."""

import json
import logging
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_github_webhook_secret
from app.models.refund import RefundEvent
from app.models.webhook import GitHubIssueEvent
from app.repositories.refund_repository import RefundRepository
from app.services.github_service import verify_signature
from app.services.refund_service import InvalidRefundError, RefundService
from app.services.sheets_service import SheetsSyncError, sync_configured_reports

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("uvicorn.error")


@router.post("/test")
def receive_test_webhook(payload: dict[str, Any]) -> dict[str, bool]:
    # FastAPI reads the request body and checks that it is a JSON object.
    # Later, the GitHub route will validate and process a refund event.
    return {"received": True}


@router.post("/test/refund", response_model=RefundEvent)
def validate_test_refund(payload: RefundEvent) -> RefundEvent:
    """Validate and echo a refund for learning; no refund is stored."""
    return payload


@router.post("/github")
async def receive_github_webhook(request: Request) -> dict[str, Any]:
    secret = get_github_webhook_secret()
    if secret is None:
        raise HTTPException(503, "GitHub webhook secret is not configured")

    body = await request.body()
    if not verify_signature(body, secret, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "Invalid webhook signature")

    event_type = request.headers.get("x-github-event")
    delivery_id = request.headers.get("x-github-delivery")
    if not event_type or not delivery_id or not delivery_id.strip():
        raise HTTPException(400, "GitHub event and delivery headers are required")

    if event_type != "issues":
        return {"status": "ignored", "reason": "Not an issues event"}

    try:
        payload = json.loads(body)
        event = GitHubIssueEvent.model_validate(payload)
    except (ValueError, UnicodeDecodeError, ValidationError):
        raise HTTPException(422, "Invalid GitHub issue payload") from None

    label = event.label.name if event.label else None
    if event.action == "labeled" and event.label is None:
        raise HTTPException(422, "A labeled event requires a label")

    logger.info(
        "github_event event_type=%s action=%s ticket_id=%s label=%s delivery_id=%s",
        event_type, event.action, event.issue.number, label, delivery_id,
    )
    if event.issue.pull_request is not None:
        return {"status": "ignored", "reason": "Pull request event"}
    if event.action != "labeled" or label != "refund-completed":
        return {"status": "ignored", "reason": "Not a refund completion"}

    try:
        service = RefundService(RefundRepository())
        # PostgreSQL's synchronous driver runs outside the async event loop.
        result = await run_in_threadpool(service.process_refund, event.issue, delivery_id)
    except InvalidRefundError as error:
        logger.warning(
            "refund_invalid ticket_id=%s delivery_id=%s reason=%s",
            event.issue.number, delivery_id, error,
        )
        raise HTTPException(422, str(error)) from None
    except psycopg.Error as error:
        logger.error(
            "refund_save_failed ticket_id=%s delivery_id=%s sqlstate=%s",
            event.issue.number, delivery_id, error.sqlstate,
        )
        raise HTTPException(503, "Refund could not be saved; retry this delivery later") from None

    status = "saved" if result.created else "duplicate"
    logger.info("refund_%s ticket_id=%s delivery_id=%s record_id=%s",
                status, result.ticket_id, delivery_id, result.record_id)
    try:
        reporting_status = await run_in_threadpool(sync_configured_reports, RefundRepository())
    except SheetsSyncError:
        reporting_status = "failed"
        logger.error("sheets_sync_failed ticket_id=%s delivery_id=%s record_id=%s",
                     result.ticket_id, delivery_id, result.record_id)
    # Saving already committed. Reporting failure must not claim the refund failed.
    return {
        "status": status,
        "ticket_id": result.ticket_id,
        "delivery_id": delivery_id,
        "record_id": result.record_id,
        "reporting_status": reporting_status,
    }
