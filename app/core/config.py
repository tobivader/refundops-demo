"""Read configuration from the server's environment."""

import os


def get_github_webhook_secret() -> str | None:
    return os.environ.get("GITHUB_WEBHOOK_SECRET") or None


def get_slack_signing_secret() -> str | None:
    return os.environ.get("SLACK_SIGNING_SECRET") or None
