"""Test projections and Google request construction without live credentials."""

from contextlib import contextmanager
import unittest
from unittest.mock import Mock, patch

from app.models.refund import RefundRecord
from app.services.sheets_service import (
    SheetsService, SheetsSyncError, build_report_rows, sync_configured_reports,
)


def record(ticket=1, amount="29.99", timestamp="2026-10-10T02:00:00Z", reason="Service outage"):
    return RefundRecord(id=ticket, ticket_id=ticket, customer_id=f"CUST-{ticket}",
                        refund_amount=amount, refund_reason=reason, analyst="analyst_07",
                        refund_date=timestamp, status="completed", github_delivery_id=f"delivery-{ticket}",
                        created_at=timestamp)


class ProjectionTests(unittest.TestCase):
    def test_empty_database_still_has_headers(self):
        reports = build_report_rows([])
        self.assertEqual(len(reports["Refund Log"]), 1)
        self.assertEqual(len(reports["Daily Summary"]), 1)

    def test_exact_totals_group_by_toronto_date(self):
        reports = build_report_rows([record(amount="0.10"), record(2, "0.20"),
                                     record(3, "1.00", "2026-10-10T04:00:00Z")])
        self.assertEqual(reports["Daily Summary"][1:],
                         [["2026-10-09", "2", "0.30"], ["2026-10-10", "1", "1.00"]])
        self.assertEqual(reports["Refund Log"][1][5], "2026-10-09")

    def test_same_snapshot_produces_same_report(self):
        records = [record()]
        self.assertEqual(build_report_rows(records), build_report_rows(records))


class SheetsWriteTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session.request.return_value.json.side_effect = [
            {"sheets": [{"properties": {"title": "Refund Log", "sheetId": 2,
                                        "gridProperties": {"rowCount": 1, "columnCount": 7}}}]}, {},
        ]
        self.service = SheetsService("demo-id", self.session)

    def test_creates_missing_summary_and_updates_both_in_one_batch(self):
        self.service.write_reports(build_report_rows([record(reason="=1+1")]))
        self.assertEqual(self.session.request.call_count, 2)
        call = self.session.request.call_args
        self.assertTrue(call.args[1].endswith(":batchUpdate"))
        requests = call.kwargs["json"]["requests"]
        self.assertTrue(any("updateSheetProperties" in request for request in requests))
        self.assertTrue(any("addSheet" in request for request in requests))
        writes = [request["updateCells"] for request in requests if "updateCells" in request]
        self.assertEqual(len(writes), 2)
        # No endRowIndex means old trailing values are cleared too.
        self.assertNotIn("endRowIndex", writes[0]["range"])
        self.assertEqual(writes[0]["fields"], "userEnteredValue")
        self.assertEqual(writes[0]["rows"][1]["values"][3],
                         {"userEnteredValue": {"stringValue": "=1+1"}})

    def test_google_failure_hides_response_details(self):
        self.session.request.side_effect = RuntimeError("secret token")
        with self.assertRaises(SheetsSyncError) as caught:
            self.service.write_reports(build_report_rows([]))
        self.assertNotIn("secret", str(caught.exception))

    def test_sync_writes_while_repository_snapshot_is_locked(self):
        locked = []

        @contextmanager
        def snapshot():
            locked.append(True)
            try:
                yield [record()]
            finally:
                locked.pop()

        repository = Mock()
        repository.reporting_snapshot.side_effect = snapshot
        with patch.object(self.service, "write_reports", side_effect=lambda reports: self.assertTrue(locked)):
            self.service.sync(repository)
        self.assertFalse(locked)

    def test_full_url_is_rejected_as_id(self):
        with self.assertRaises(SheetsSyncError):
            SheetsService("https://docs.google.com/spreadsheets/d/id/edit", self.session)

    def test_reporting_is_disabled_without_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(sync_configured_reports(Mock()), "disabled")

    def test_partial_configuration_is_an_error(self):
        with patch.dict("os.environ", {"GOOGLE_SHEETS_SPREADSHEET_ID": "demo"}, clear=True):
            with self.assertRaises(SheetsSyncError):
                SheetsService.from_environment()
