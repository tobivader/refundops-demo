"""Open PostgreSQL connections using environment configuration."""

import os

import psycopg


def connect_database(*, password: str | None = None) -> psycopg.Connection:
    """The caller should use a with-block to close the connection afterward."""
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "refundops"),
        user=os.environ.get("PGUSER", "postgres"),
        password=password if password is not None else os.environ.get("PGPASSWORD"),
        connect_timeout=5,
    )
