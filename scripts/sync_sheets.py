"""Rebuild both worksheets from PostgreSQL, including after a reporting failure."""

import getpass
import os
import sys

from app.repositories.refund_repository import RefundRepository
from app.services.sheets_service import SheetsSyncError, sync_configured_reports


def main() -> int:
    if not (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or
            os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")):
        print("Reporting disabled. Configure GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_SHEETS_SPREADSHEET_ID.")
        return 1
    if "PGPASSWORD" not in os.environ:
        if not sys.stdin.isatty():
            print("Run in an interactive terminal to enter the PostgreSQL password, or configure PGPASSWORD.")
            return 1
        os.environ["PGPASSWORD"] = getpass.getpass("PostgreSQL password (input is hidden): ")
    try:
        status = sync_configured_reports(RefundRepository())
        if status == "disabled":
            print("Reporting disabled. Configure GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_SHEETS_SPREADSHEET_ID.")
            return 1
        print("Synchronized Refund Log and Daily Summary from PostgreSQL.")
        return 0
    except SheetsSyncError as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
