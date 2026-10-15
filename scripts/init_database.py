"""Create the first RefundOps table without deleting existing data."""

import getpass
import os
from pathlib import Path

import psycopg

from app.db.database import connect_database


def main() -> int:
    password = os.environ.get("PGPASSWORD")
    if password is None:
        password = getpass.getpass("PostgreSQL password (input is hidden): ")
    schema_path = Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql"
    try:
        with connect_database(password=password) as connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_path.read_text(encoding="utf-8"))
                cursor.execute("SELECT current_database()")
                database = cursor.fetchone()[0]
        # Leaving the connection with-block commits the table creation.
        print(f"Refunds table ready in database={database}")
        return 0
    except psycopg.Error as error:
        print(f"Table setup failed (SQLSTATE: {error.sqlstate or 'unavailable'}). "
              "Check the connection, permissions, and PostgreSQL server log.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
