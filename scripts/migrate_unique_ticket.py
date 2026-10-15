"""Archive duplicate tickets and enforce one active refund per ticket."""

import getpass
import os
from pathlib import Path

import psycopg

from app.db.database import connect_database


def main() -> int:
    password = os.environ.get("PGPASSWORD")
    if password is None:
        password = getpass.getpass("PostgreSQL password (input is hidden): ")
    migration = Path(__file__).resolve().parents[1] / "app/db/migrations/001_unique_ticket.sql"
    try:
        with connect_database(password=password) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '30s'")
                cursor.execute(migration.read_text(encoding="utf-8"))
                cursor.execute("SELECT COUNT(*) FROM public.refunds")
                active = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM public.refunds_duplicate_archive")
                archived = cursor.fetchone()[0]
        print(f"Migration complete: active refunds={active}, archived duplicates={archived}")
        return 0
    except psycopg.Error as error:
        print(f"Migration failed and rolled back (SQLSTATE: {error.sqlstate or 'unavailable'}). "
              "Check database setup, permissions, and server logs.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
