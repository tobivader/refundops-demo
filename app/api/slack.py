"""Slack slash commands use signed form bodies rather than GitHub JSON."""

import asyncio
import logging
from urllib.parse import parse_qs

import psycopg
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.core.config import get_slack_signing_secret
from app.repositories.refund_repository import RefundRepository
from app.services.slack_service import SlackService, verify_slack_signature

router = APIRouter(prefix="/slack", tags=["slack"])
logger = logging.getLogger("uvicorn.error")


@router.post("/commands")
async def slack_commands(request: Request) -> dict[str, str]:
    secret = get_slack_signing_secret()
    if secret is None:
        raise HTTPException(503, "Slack signing secret is not configured")
    body = await request.body()
    if not verify_slack_signature(body, secret,
                                  request.headers.get("x-slack-request-timestamp"),
                                  request.headers.get("x-slack-signature")):
        raise HTTPException(401, "Invalid Slack signature or timestamp")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected a Slack form payload")
    try:
        fields = parse_qs(body.decode("utf-8"), keep_blank_values=True,
                          strict_parsing=True, max_num_fields=50)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "Invalid Slack command payload") from None
    if fields.get("command") != ["/refunds"] or len(fields.get("text", [])) != 1:
        raise HTTPException(422, "Expected /refunds command and text")

    service = SlackService(RefundRepository())
    try:
        # Slack needs acknowledgement within 3 seconds. Bound this simple read.
        return await asyncio.wait_for(
            run_in_threadpool(service.handle_command, fields["text"][0]), timeout=2.0,
        )
    except (TimeoutError, psycopg.Error):
        logger.warning("slack_statistics_unavailable")
        return {"response_type": "ephemeral",
                "text": "Refund statistics are temporarily unavailable. Please try again."}
