"""Verify issue-to-refund transformation independently of HTTP."""

import unittest
from decimal import Decimal
from unittest.mock import Mock

from app.models.webhook import GitHubIssue
from app.services.refund_service import InvalidRefundError, RefundService
from app.repositories.refund_repository import RefundRepository, SaveResult


class RefundServiceTests(unittest.TestCase):
    def setUp(self):
        self.body = "Customer ID: CUST-1842\nRefund Amount: 29.99\nRefund Reason: Service outage: partial downtime\nAnalyst: analyst_07"
        self.service = RefundService()

    def issue(self, body):
        return GitHubIssue(number=1, body=body, updated_at="2026-10-07T12:00:00Z")

    def test_extracts_fields_and_uses_github_issue_number(self):
        refund = self.service.extract_refund(self.issue(self.body))
        self.assertEqual(refund.ticket_id, 1)
        self.assertEqual(refund.customer_id, "CUST-1842")
        self.assertEqual(refund.refund_amount, Decimal("29.99"))
        self.assertEqual(refund.refund_reason, "Service outage: partial downtime")
        self.assertEqual(refund.status, "completed")

    def test_ignores_description_and_normalizes_field_names(self):
        body = self.body.replace("Customer ID:", "  CUSTOMER ID : ") + "\nDescription: Please help"
        self.assertEqual(self.service.extract_refund(self.issue(body)).customer_id, "CUST-1842")

    def test_missing_empty_or_duplicate_fields_are_rejected(self):
        for body in [None, "", self.body.replace("Analyst: analyst_07", ""),
                     self.body.replace("analyst_07", "   "), self.body + "\nRefund Amount: 99.99"]:
            with self.subTest(body=body):
                with self.assertRaises(InvalidRefundError):
                    self.service.extract_refund(self.issue(body))

    def test_invalid_amounts_are_rejected(self):
        for amount in ["-1", "0", "29.999", "Not yet processed", "$29.99"]:
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(InvalidRefundError, "refund_amount"):
                    self.service.extract_refund(self.issue(self.body.replace("29.99", amount)))

    def test_missing_source_timestamp_is_rejected(self):
        with self.assertRaisesRegex(InvalidRefundError, "updated_at"):
            self.service.extract_refund(GitHubIssue(number=1, body=self.body))

    def test_redelivery_keeps_the_same_refund_date(self):
        issue = self.issue(self.body)
        self.assertEqual(self.service.extract_refund(issue).refund_date,
                         self.service.extract_refund(issue).refund_date)

    def test_processing_passes_validated_refund_to_repository(self):
        repository = Mock(spec=RefundRepository)
        repository.save.return_value = SaveResult(7, 1, True)
        result = RefundService(repository).process_refund(self.issue(self.body), "delivery-1")
        self.assertEqual(result.record_id, 7)
        refund, delivery = repository.save.call_args.args
        self.assertEqual(refund.refund_amount, Decimal("29.99"))
        self.assertEqual(delivery, "delivery-1")

    def test_invalid_refund_never_reaches_repository(self):
        repository = Mock(spec=RefundRepository)
        with self.assertRaises(InvalidRefundError):
            RefundService(repository).process_refund(self.issue(""), "delivery-1")
        repository.save.assert_not_called()
