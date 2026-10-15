"""Publish two database-derived reporting views to Google Sheets."""

import os
import re
from decimal import Decimal
from zoneinfo import ZoneInfo

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from app.models.refund import RefundRecord
from app.repositories.refund_repository import RefundRepository


class SheetsSyncError(RuntimeError):
    """Reporting failed; the committed refund remains in PostgreSQL."""


def build_report_rows(records: list[RefundRecord]) -> dict[str, list[list[str]]]:
    log = [["Ticket ID", "Customer ID", "Amount", "Reason", "Analyst", "Date", "Status"]]
    daily = {}
    for refund in records:
        day = refund.refund_date.astimezone(ZoneInfo("America/Toronto")).date().isoformat()
        log.append([str(refund.ticket_id), refund.customer_id, format(refund.refund_amount, ".2f"),
                    refund.refund_reason, refund.analyst, day, refund.status])
        count, total = daily.get(day, (0, Decimal("0")))
        daily[day] = (count + 1, total + refund.refund_amount)
    summary = [["Date", "Refund Count", "Total Amount"]]
    for day, (count, total) in sorted(daily.items()):
        summary.append([day, str(count), format(total, ".2f")])
    return {"Refund Log": log, "Daily Summary": summary}


class SheetsService:
    def __init__(self, spreadsheet_id: str, session):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet_id):
            raise SheetsSyncError("Use the spreadsheet ID, not its full URL")
        self.url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        self.session = session

    @classmethod
    def from_environment(cls):
        key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
        if not key_path and not spreadsheet_id:
            return None
        if not key_path or not spreadsheet_id:
            raise SheetsSyncError("Both Google reporting settings are required")
        try:
            credentials = service_account.Credentials.from_service_account_file(
                key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            return cls(spreadsheet_id, AuthorizedSession(credentials, refresh_timeout=15))
        except SheetsSyncError:
            raise
        except Exception:
            raise SheetsSyncError("Could not load Google service account credentials") from None

    def _request(self, method: str, suffix: str = "", **kwargs):
        try:
            response = self.session.request(method, self.url + suffix, timeout=15, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception:
            # Do not log tokens, credential paths, or Google response payloads.
            raise SheetsSyncError("Google Sheets request failed; check permissions and API setup") from None

    def write_reports(self, reports: dict[str, list[list[str]]]):
        metadata = self._request("GET", params={"fields": "sheets(properties)"})
        sheets = {item["properties"]["title"]: item["properties"]
                  for item in metadata["sheets"]}
        requests = []
        next_id = max((item["sheetId"] for item in sheets.values()), default=-1) + 1
        for title, rows in reports.items():
            columns = len(rows[0])
            existing = sheets.get(title)
            if existing is None:
                sheet_id = next_id
                next_id += 1
                requests.append({"addSheet": {"properties": {
                    "sheetId": sheet_id, "title": title,
                    "gridProperties": {"rowCount": max(1000, len(rows)), "columnCount": max(26, columns)},
                }}})
            else:
                sheet_id = existing["sheetId"]
                grid = existing["gridProperties"]
                if len(rows) > grid["rowCount"] or columns > grid["columnCount"]:
                    requests.append({"updateSheetProperties": {
                        "properties": {"sheetId": sheet_id, "gridProperties": {
                            "rowCount": max(len(rows), grid["rowCount"]),
                            "columnCount": max(columns, grid["columnCount"]),
                        }}, "fields": "gridProperties.rowCount,gridProperties.columnCount",
                    }})
            # Writing literal strings prevents formula execution from ticket text.
            # The unbounded row range clears stale values below the new report.
            requests.append({"updateCells": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0,
                          "startColumnIndex": 0, "endColumnIndex": columns},
                "rows": [{"values": [{"userEnteredValue": {"stringValue": value}}
                                     for value in row]} for row in rows],
                "fields": "userEnteredValue",
            }})
        # Both worksheets change together in one atomic Google batch.
        self._request("POST", ":batchUpdate", json={"requests": requests})

    def sync(self, repository: RefundRepository):
        try:
            with repository.reporting_snapshot() as records:
                self.write_reports(build_report_rows(records))
        except SheetsSyncError:
            raise
        except Exception:
            raise SheetsSyncError("Could not synchronize the database report") from None


def sync_configured_reports(repository: RefundRepository) -> str:
    service = SheetsService.from_environment()
    if service is None:
        return "disabled"
    try:
        service.sync(repository)
    finally:
        service.session.close()
    return "synced"
