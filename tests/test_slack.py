"""Signed command requests and read-only reporting responses."""

import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

import psycopg

from app.main import app
from app.models.stats import TodayStats
from app.services.slack_service import SlackService, verify_slack_signature


def signature(body, timestamp="2000000000"):
    base = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(b"test-secret", base, hashlib.sha256).hexdigest()


class SignatureTests(unittest.TestCase):
    def test_signature_checks_original_body_and_recent_timestamp(self):
        body = b"command=%2Frefunds&text=today"
        self.assertTrue(verify_slack_signature(body, "test-secret", "2000000000",
                                              signature(body), now=2000000000))
        self.assertFalse(verify_slack_signature(body + b"x", "test-secret", "2000000000",
                                               signature(body), now=2000000000))
        for now in [1999999699, 2000000301]:
            self.assertFalse(verify_slack_signature(body, "test-secret", "2000000000",
                                                   signature(body), now=now))

    def test_missing_and_invalid_headers_fail(self):
        for timestamp, sig in [(None, None), ("abc", "v0=x"), ("2000000000", None),
                               ("2000000000", "é"), ("9" * 100, "v0=x")]:
            self.assertFalse(verify_slack_signature(b"", "test-secret", timestamp, sig,
                                                   now=2000000000))


class CommandTests(unittest.TestCase):
    def test_today_uses_database_and_formats_exact_amount(self):
        repository = Mock()
        repository.get_today_stats.return_value = TodayStats(
            date="2026-10-15", refund_count=1, total_refunded="29.99",
        )
        response = SlackService(repository).handle_command(" TODAY ")
        self.assertEqual(response["response_type"], "ephemeral")
        self.assertIn("29.99", response["text"])
        self.assertIn("2026-10-15", response["text"])
        repository.get_today_stats.assert_called_once()

    def test_help_does_not_query_database(self):
        repository = Mock()
        response = SlackService(repository).handle_command("help")
        self.assertIn("Usage", response["text"])
        repository.get_today_stats.assert_not_called()

    def test_empty_command_defaults_to_today(self):
        repository = Mock()
        repository.get_today_stats.return_value = TodayStats(
            date="2026-10-15", refund_count=1, total_refunded="29.99",
        )
        response = SlackService(repository).handle_command("   ")
        self.assertIn("Refunds: 1", response["text"])
        self.assertIn("29.99", response["text"])
        repository.get_today_stats.assert_called_once()


class SlackApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"SLACK_SIGNING_SECRET": "test-secret"})
        environment.start()
        self.addCleanup(environment.stop)
        clock = patch("app.services.slack_service.time.time", return_value=2000000000)
        clock.start()
        self.addCleanup(clock.stop)
        repository = patch("app.api.slack.RefundRepository", autospec=True)
        self.repository = repository.start().return_value
        self.addCleanup(repository.stop)
        self.repository.get_today_stats.return_value = TodayStats(
            date="2026-10-15", refund_count=0, total_refunded="0",
        )

    async def deliver(self, text="today", *, timestamp="2000000000", sig=None, body=None):
        body = body if body is not None else urlencode({"command": "/refunds", "text": text}).encode()
        messages = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/slack/commands",
            "raw_path": b"/slack/commands", "query_string": b"", "root_path": "",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded"),
                        (b"x-slack-request-timestamp", timestamp.encode()),
                        (b"x-slack-signature", (sig or signature(body, timestamp)).encode())],
            "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8000),
        }, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        result = json.loads(b"".join(m.get("body", b"") for m in messages
                                   if m["type"] == "http.response.body"))
        return status, result

    async def test_signed_command_returns_private_summary(self):
        status, response = await self.deliver()
        self.assertEqual(status, 200)
        self.assertEqual(response["response_type"], "ephemeral")
        self.assertIn("0.00", response["text"])

    async def test_bad_signature_and_stale_request_never_query_database(self):
        self.assertEqual((await self.deliver(sig="v0=wrong"))[0], 401)
        self.assertEqual((await self.deliver(timestamp="1999999000"))[0], 401)
        self.repository.get_today_stats.assert_not_called()

    async def test_missing_secret_fails_closed(self):
        with patch.dict("os.environ", {"SLACK_SIGNING_SECRET": ""}):
            self.assertEqual((await self.deliver())[0], 503)

    async def test_wrong_command_is_rejected(self):
        self.assertEqual((await self.deliver(body=b"command=%2Fother&text=today"))[0], 422)
        self.assertEqual((await self.deliver(body=b"command=%2Frefunds&text=today&text=help"))[0], 422)

    async def test_database_failure_returns_friendly_message(self):
        self.repository.get_today_stats.side_effect = psycopg.OperationalError("private information")
        status, response = await self.deliver()
        self.assertEqual(status, 200)
        self.assertIn("temporarily unavailable", response["text"])
        self.assertNotIn("private information", response["text"])

    async def test_slow_query_is_bounded(self):
        async def slow(*args):
            raise TimeoutError
        with patch("app.api.slack.run_in_threadpool", side_effect=slow):
            status, response = await self.deliver()
        self.assertEqual(status, 200)
        self.assertIn("temporarily unavailable", response["text"])
