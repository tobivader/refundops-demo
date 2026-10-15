"""Check local date boundaries, exact money, and statistics HTTP responses."""

from datetime import datetime, timedelta
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

import psycopg

from app.main import app
from app.models.stats import AnalystStats, TodayStats
from app.repositories.refund_repository import RefundRepository, today_window


class TodayWindowTests(unittest.TestCase):
    def test_utc_date_can_differ_from_toronto_date(self):
        day, start, end = today_window(datetime.fromisoformat("2026-10-10T02:00:00+00:00"))
        self.assertEqual(day.isoformat(), "2026-10-09")
        self.assertEqual(start.isoformat(), "2026-10-09T04:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-10-10T04:00:00+00:00")

    def test_midnight_begins_next_local_day(self):
        day, _, _ = today_window(datetime.fromisoformat("2026-10-10T04:00:00+00:00"))
        self.assertEqual(day.isoformat(), "2026-10-10")

    def test_daylight_saving_days_are_not_always_24_hours(self):
        for instant, hours in [("2026-03-08T12:00:00+00:00", 23),
                               ("2026-11-01T12:00:00+00:00", 25)]:
            with self.subTest(instant=instant):
                _, start, end = today_window(datetime.fromisoformat(instant))
                self.assertEqual(end - start, timedelta(hours=hours))

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            today_window(datetime(2026, 10, 10))

    def test_repository_passes_utc_bounds_and_preserves_decimal(self):
        with patch("app.repositories.refund_repository.connect_database") as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = {"refund_count": 2, "total_refunded": Decimal("0.30")}
            now = datetime.fromisoformat("2026-10-10T12:00:00+00:00")
            result = RefundRepository().get_today_stats(now)
            _, start, end = today_window(now)
            self.assertEqual(cursor.execute.call_args.args[1], (start, end))
            self.assertEqual(result.total_refunded, Decimal("0.30"))


class StatisticsApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        repository_patch = patch("app.api.stats.RefundRepository", autospec=True)
        self.repository = repository_patch.start().return_value
        self.addCleanup(repository_patch.stop)
        self.repository.get_today_stats.return_value = TodayStats(
            date="2026-10-10", refund_count=0, total_refunded="0",
        )
        self.repository.get_analyst_stats.return_value = [AnalystStats(
            analyst="analyst_07", refund_count=1, total_refunded="29.99",
        )]

    async def get(self, path):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [], "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8000),
        }, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = json.loads(b"".join(m.get("body", b"") for m in messages
                                 if m["type"] == "http.response.body"))
        return status, body

    async def test_empty_today_is_zero_with_date_context(self):
        status, body = await self.get("/stats/today")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"refund_count": 0, "total_refunded": "0",
                                "date": "2026-10-10", "timezone": "America/Toronto"})

    async def test_analyst_totals_preserve_money(self):
        status, body = await self.get("/stats/analysts")
        self.assertEqual(status, 200)
        self.assertEqual(body[0]["refund_count"], 1)
        self.assertEqual(body[0]["total_refunded"], "29.99")

    async def test_no_analysts_returns_empty_list(self):
        self.repository.get_analyst_stats.return_value = []
        self.assertEqual(await self.get("/stats/analysts"), (200, []))

    async def test_failures_hide_database_details(self):
        for path, method in [("/stats/today", self.repository.get_today_stats),
                             ("/stats/analysts", self.repository.get_analyst_stats)]:
            with self.subTest(path=path):
                method.side_effect = psycopg.OperationalError("private details")
                status, body = await self.get(path)
                self.assertEqual(status, 503)
                self.assertNotIn("private", body["detail"])
