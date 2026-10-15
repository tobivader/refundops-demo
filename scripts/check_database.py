"""Check the configured database without creating or changing any tables."""

import getpass
import os

import psycopg

from app.db.database import connect_database


def main() -> int:
    password = os.environ.get("PGPASSWORD")
    if password is None:
        password = getpass.getpass("PostgreSQL password (input is hidden): ")
    try:
        with connect_database(password=password) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                database, user = cursor.fetchone()
        print(f"Connected successfully: database={database}, user={user}")
        return 0
    except psycopg.Error:
        # Don't print connection details or credentials from driver errors.
        print("Connection failed. Check PostgreSQL is running, the database exists, "
              "and the host, port, username, and password are correct.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
