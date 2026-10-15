"""Verify refund reads, paging validation, and database failure responses."""

import json
import unittest
from unittest.mock import patch

import psycopg

from app.main import app
from app.models.refund import RefundRecord


class RefundReadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        repository_patch = patch("app.api.refunds.RefundRepository", autospec=True)
        self.repository = repository_patch.start().return_value
        self.addCleanup(repository_patch.stop)
        self.record = RefundRecord(
            id=1, ticket_id=1, customer_id="CUST-1842", refund_amount="29.99",
            refund_reason="Service outage", analyst="analyst_07",
            refund_date="2026-10-09T22:42:36-04:00", status="completed",
            github_delivery_id="demo-1", created_at="2026-10-10T02:42:37Z",
        )
        self.repository.list_refunds.return_value = [self.record]

    async def get(self, query=b""):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": "/refunds",
            "raw_path": b"/refunds", "query_string": query, "root_path": "",
            "headers": [], "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8000),
        }, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        response = json.loads(b"".join(m.get("body", b"") for m in messages
                                      if m["type"] == "http.response.body"))
        return status, response

    async def test_records_serialize_money_and_metadata(self):
        status, response = await self.get()
        self.assertEqual(status, 200)
        self.assertEqual(response[0]["refund_amount"], "29.99")
        self.assertEqual(response[0]["id"], 1)
        self.assertEqual(response[0]["github_delivery_id"], "demo-1")
        self.repository.list_refunds.assert_called_once_with(limit=50, offset=0)

    async def test_empty_database_returns_empty_list(self):
        self.repository.list_refunds.return_value = []
        self.assertEqual(await self.get(), (200, []))

    async def test_paging_is_passed_to_repository(self):
        status, _ = await self.get(b"limit=10&offset=20")
        self.assertEqual(status, 200)
        self.repository.list_refunds.assert_called_once_with(limit=10, offset=20)

    async def test_invalid_paging_is_rejected_before_database_access(self):
        for query in [b"limit=0", b"limit=101", b"offset=-1", b"limit=abc"]:
            with self.subTest(query=query):
                status, _ = await self.get(query)
                self.assertEqual(status, 422)
        self.repository.list_refunds.assert_not_called()

    async def test_database_failure_does_not_expose_driver_details(self):
        self.repository.list_refunds.side_effect = psycopg.OperationalError("private details")
        status, response = await self.get()
        self.assertEqual(status, 503)
        self.assertNotIn("private", response["detail"])
