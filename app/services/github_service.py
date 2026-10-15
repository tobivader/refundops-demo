"""Verify GitHub deliveries before trusting their content."""

import hashlib
import hmac


def verify_signature(body: bytes, secret: str, signature: str | None) -> bool:
    if not signature or not signature.isascii():
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
