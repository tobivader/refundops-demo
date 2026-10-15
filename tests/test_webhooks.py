"""Check signed deliveries through the application without a network server."""

import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

import psycopg

from app.main import app
from app.repositories.refund_repository import SaveResult
from app.services.sheets_service import SheetsSyncError


class GitHubWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def deliver(self, payload, event="issues", signature=None, delivery="demo-1"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        signed = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        headers = [(b"content-type", b"application/json"),
                   (b"x-hub-signature-256", (signature or signed).encode())]
        if event:
            headers.append((b"x-github-event", event.encode()))
        if delivery:
            headers.append((b"x-github-delivery", delivery.encode()))
        messages = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": "/webhooks/github", "raw_path": b"/webhooks/github",
            "query_string": b"", "root_path": "", "headers": headers,
            "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8000),
        }, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        response = json.loads(b"".join(m.get("body", b"") for m in messages
                                      if m["type"] == "http.response.body"))
        return status, response

    def setUp(self):
        reporting_patch = patch("app.api.webhooks.sync_configured_reports", return_value="disabled")
        self.reporting = reporting_patch.start()
        self.addCleanup(reporting_patch.stop)
        repository_patch = patch("app.api.webhooks.RefundRepository", autospec=True)
        self.repository = repository_patch.start().return_value
        self.repository.save.return_value = SaveResult(42, 1842, True)
        self.addCleanup(repository_patch.stop)
        environment = patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": "test-secret"})
        environment.start()
        self.addCleanup(environment.stop)
        self.payload = {"action": "labeled", "issue": {
            "number": 1842, "updated_at": "2026-10-07T12:00:00Z",
            "body": "Customer ID: CUST-1842\nRefund Amount: 29.99\nRefund Reason: Service outage\nAnalyst: analyst_07",
        },
                        "label": {"name": "refund-completed"}}

    async def test_completion_is_saved(self):
        status, response = await self.deliver(self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "saved")
        self.assertEqual(response["ticket_id"], 1842)
        self.assertEqual(response["delivery_id"], "demo-1")
        self.assertEqual(response["record_id"], 42)
        refund, delivery = self.repository.save.call_args.args
        self.assertEqual(str(refund.refund_amount), "29.99")
        self.assertEqual(refund.analyst, "analyst_07")
        self.assertEqual(delivery, "demo-1")

    async def test_duplicate_delivery_returns_existing_record(self):
        self.repository.save.return_value = SaveResult(42, 1842, False)
        status, response = await self.deliver(self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "duplicate")
        self.assertEqual(response["record_id"], 42)
        self.reporting.assert_called_once()

    async def test_reporting_failure_keeps_successful_refund_response(self):
        self.reporting.side_effect = SheetsSyncError("Google failed")
        status, response = await self.deliver(self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "saved")
        self.assertEqual(response["reporting_status"], "failed")

    async def test_reporting_success_is_visible(self):
        self.reporting.return_value = "synced"
        status, response = await self.deliver(self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(response["reporting_status"], "synced")

    async def test_database_failure_returns_retryable_error(self):
        self.repository.save.side_effect = psycopg.OperationalError("private connection information")
        status, response = await self.deliver(self.payload)
        self.assertEqual(status, 503)
        self.assertNotIn("private", response["detail"])

    async def test_incomplete_refund_is_rejected(self):
        payload = {**self.payload, "issue": {"number": 1842, "body": "Customer ID: CUST-1842"}}
        status, response = await self.deliver(payload)
        self.assertEqual(status, 422)
        self.assertIn("refund_amount", response["detail"])
        self.repository.save.assert_not_called()

    async def test_wrong_signature_is_rejected(self):
        status, _ = await self.deliver(self.payload, signature="sha256=wrong")
        self.assertEqual(status, 401)

    async def test_missing_signature_is_rejected(self):
        status, _ = await self.deliver(self.payload, signature=" ")
        self.assertEqual(status, 401)

    async def test_unrelated_events_are_ignored(self):
        variants = [({"zen": "hello"}, "ping"),
                    ({**self.payload, "action": "unlabeled"}, "issues"),
                    ({**self.payload, "label": {"name": "billing"}}, "issues"),
                    ({**self.payload, "issue": {"number": 1842, "pull_request": {}}}, "issues")]
        for payload, event in variants:
            with self.subTest(payload=payload, event=event):
                status, response = await self.deliver(payload, event=event)
                self.assertEqual(status, 200)
                self.assertEqual(response["status"], "ignored")

    async def test_invalid_issue_payload_is_rejected(self):
        for payload in [b"{broken", [], {"action": "labeled"},
                        {"action": "labeled", "issue": {"number": 1842}}]:
            with self.subTest(payload=payload):
                status, _ = await self.deliver(payload)
                self.assertEqual(status, 422)

    async def test_required_headers(self):
        for headers in [{"event": None}, {"delivery": None}]:
            with self.subTest(headers=headers):
                status, _ = await self.deliver(self.payload, **headers)
                self.assertEqual(status, 400)

    async def test_unconfigured_secret_fails_closed(self):
        with patch.dict("os.environ", {"GITHUB_WEBHOOK_SECRET": ""}):
            status, _ = await self.deliver(self.payload)
        self.assertEqual(status, 503)
