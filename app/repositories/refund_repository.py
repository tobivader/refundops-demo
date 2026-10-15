"""Persist refunds with database-enforced delivery idempotency."""

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from app.db.database import connect_database
from app.models.refund import RefundEvent, RefundRecord
from app.models.stats import AnalystStats, TodayStats


def today_window(now: datetime) -> tuple[date, datetime, datetime]:
    """Return Toronto's date and UTC bounds, including daylight-saving days."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    toronto = ZoneInfo("America/Toronto")
    local_date = now.astimezone(toronto).date()
    start = datetime.combine(local_date, time.min, tzinfo=toronto)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=toronto)
    return local_date, start.astimezone(timezone.utc), end.astimezone(timezone.utc)


@dataclass(frozen=True)
class SaveResult:
    record_id: int
    ticket_id: int
    created: bool


class RefundRepository:
    @contextmanager
    def reporting_snapshot(self):
        """Serialize report writers and read one complete committed snapshot."""
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SELECT pg_advisory_xact_lock(724019)")
                cursor.execute(
                    """
                    SELECT id, ticket_id, customer_id, refund_amount, refund_reason,
                           analyst, refund_date, status, github_delivery_id, created_at
                    FROM public.refunds ORDER BY id
                    """
                )
                records = [RefundRecord.model_validate(row) for row in cursor.fetchall()]
            # Keep the advisory lock until the external write finishes.
            yield records

    def get_today_stats(self, now: datetime | None = None) -> TodayStats:
        local_date, start, end = today_window(now if now is not None else datetime.now(timezone.utc))
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                # Include local midnight; exclude the following midnight.
                cursor.execute(
                    """
                    SELECT COUNT(*) AS refund_count,
                           COALESCE(SUM(refund_amount), 0) AS total_refunded
                    FROM public.refunds
                    WHERE refund_date >= %s AND refund_date < %s
                    """,
                    (start, end),
                )
                return TodayStats(date=local_date, **cursor.fetchone())

    def get_analyst_stats(self) -> list[AnalystStats]:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT analyst, COUNT(*) AS refund_count,
                           COALESCE(SUM(refund_amount), 0) AS total_refunded
                    FROM public.refunds
                    GROUP BY analyst
                    ORDER BY analyst
                    """
                )
                return [AnalystStats.model_validate(row) for row in cursor.fetchall()]

    def list_refunds(self, limit: int = 50, offset: int = 0) -> list[RefundRecord]:
        with connect_database() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT id, ticket_id, customer_id, refund_amount, refund_reason,
                           analyst, refund_date, status, github_delivery_id, created_at
                    FROM public.refunds
                    ORDER BY id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                return [RefundRecord.model_validate(row) for row in cursor.fetchall()]

    def save(self, refund: RefundEvent, delivery_id: str) -> SaveResult:
        with connect_database() as connection:
            with connection.cursor() as cursor:
                # Parameters keep issue text separate from executable SQL.
                cursor.execute(
                    """
                    INSERT INTO public.refunds (
                        ticket_id, customer_id, refund_amount, refund_reason,
                        analyst, refund_date, status, github_delivery_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING id, ticket_id
                    """,
                    (refund.ticket_id, refund.customer_id, refund.refund_amount,
                     refund.refund_reason, refund.analyst, refund.refund_date,
                     refund.status, delivery_id),
                )
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(
                        """
                        SELECT id, ticket_id FROM public.refunds
                        WHERE github_delivery_id = %s OR ticket_id = %s
                        ORDER BY (github_delivery_id = %s) DESC
                        LIMIT 1
                        """,
                        (delivery_id, refund.ticket_id, delivery_id),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("Duplicate refund record could not be retrieved")
                result = SaveResult(record_id=row[0], ticket_id=row[1], created=created)
        # Exiting the connection block commits; failures roll back automatically.
        return result
