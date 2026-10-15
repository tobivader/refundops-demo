"""The data required to record a completed refund."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RefundEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: int = Field(gt=0, strict=True)
    customer_id: NonEmptyText
    refund_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    refund_reason: NonEmptyText
    analyst: NonEmptyText
    refund_date: AwareDatetime
    status: Literal["completed"]


class RefundRecord(RefundEvent):
    """A validated refund plus the metadata PostgreSQL saves."""

    id: int = Field(gt=0)
    github_delivery_id: NonEmptyText
    created_at: AwareDatetime
