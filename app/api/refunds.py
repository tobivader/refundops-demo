"""Read saved refunds through HTTP."""

import logging
from typing import Annotated

import psycopg
from fastapi import APIRouter, HTTPException, Query

from app.models.refund import RefundRecord
from app.repositories.refund_repository import RefundRepository

router = APIRouter(prefix="/refunds", tags=["refunds"])
logger = logging.getLogger("uvicorn.error")


@router.get("", response_model=list[RefundRecord])
def list_refunds(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RefundRecord]:
    """Return a page of saved refunds, newest first."""
    try:
        return RefundRepository().list_refunds(limit=limit, offset=offset)
    except psycopg.Error as error:
        logger.error("refund_list_failed sqlstate=%s", error.sqlstate)
        raise HTTPException(503, "Refunds are temporarily unavailable") from None
