"""Read refund summaries from the system of record."""

import logging

import psycopg
from fastapi import APIRouter, HTTPException

from app.models.stats import AnalystStats, TodayStats
from app.repositories.refund_repository import RefundRepository

router = APIRouter(prefix="/stats", tags=["statistics"])
logger = logging.getLogger("uvicorn.error")


@router.get("/today", response_model=TodayStats)
def today_stats() -> TodayStats:
    try:
        return RefundRepository().get_today_stats()
    except psycopg.Error as error:
        logger.error("today_stats_failed sqlstate=%s", error.sqlstate)
        raise HTTPException(503, "Statistics are temporarily unavailable") from None


@router.get("/analysts", response_model=list[AnalystStats])
def analyst_stats() -> list[AnalystStats]:
    """All-time totals for each analyst, sorted by name."""
    try:
        return RefundRepository().get_analyst_stats()
    except psycopg.Error as error:
        logger.error("analyst_stats_failed sqlstate=%s", error.sqlstate)
        raise HTTPException(503, "Statistics are temporarily unavailable") from None
