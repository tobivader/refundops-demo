"""Create the web application and connect its routes."""

from fastapi import FastAPI

from app.api.refunds import router as refund_router
from app.api.stats import router as stats_router
from app.api.slack import router as slack_router
from app.api.webhooks import router as webhook_router

app = FastAPI(title="RefundOps", version="0.1.0")
app.include_router(webhook_router)
app.include_router(refund_router)
app.include_router(stats_router)
app.include_router(slack_router)
