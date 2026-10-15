"""Verify Slack requests and build read-only command responses."""

import hashlib
import hmac
import time

from app.repositories.refund_repository import RefundRepository


def verify_slack_signature(body: bytes, secret: str, timestamp: str | None,
                           signature: str | None, *, now: float | None = None) -> bool:
    if not timestamp or not timestamp.isascii() or not timestamp.isdecimal():
        return False
    if len(timestamp) > 12 or not signature or not signature.isascii():
        return False
    clock = time.time() if now is None else now
    if abs(clock - int(timestamp)) > 300:
        return False
    base = b"v0:" + timestamp.encode("ascii") + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class SlackService:
    def __init__(self, repository: RefundRepository):
        self.repository = repository

    def handle_command(self, text: str) -> dict[str, str]:
        if text.strip().lower() == "today":
            stats = self.repository.get_today_stats()
            message = (
                f"Refund Summary — {stats.date} ({stats.timezone})\n"
                f"Refunds: {stats.refund_count}\n"
                f"Total refunded: {stats.total_refunded:,.2f}"
            )
        else:
            message = "Usage: /refunds today — today's refund count and total (America/Toronto)."
        return {"response_type": "ephemeral", "text": message}
