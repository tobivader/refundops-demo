"""Response schemas for refund reporting."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.refund import NonEmptyText


class RefundTotals(BaseModel):
    refund_count: int = Field(ge=0)
    total_refunded: Decimal = Field(ge=0)


class TodayStats(RefundTotals):
    date: date
    timezone: Literal["America/Toronto"] = "America/Toronto"


class AnalystStats(RefundTotals):
    analyst: NonEmptyText
