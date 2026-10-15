"""Check repository result handling without requiring local credentials."""

import unittest
from unittest.mock import patch

from app.models.refund import RefundEvent
from app.repositories.refund_repository import RefundRepository


class RefundRepositoryTests(unittest.TestCase):
    def setUp(self):
        connection_patch = patch("app.repositories.refund_repository.connect_database")
        connection = connection_patch.start().return_value.__enter__.return_value
        self.cursor = connection.cursor.return_value.__enter__.return_value
        self.addCleanup(connection_patch.stop)
        self.refund = RefundEvent(
            ticket_id=1, customer_id="CUST-1842", refund_amount="29.99",
            refund_reason="Service outage", analyst="analyst_07",
            refund_date="2026-10-09T22:42:36-04:00", status="completed",
        )

    def test_new_refund_returns_inserted_record(self):
        self.cursor.fetchone.return_value = (7, 1)
        result = RefundRepository().save(self.refund, "delivery-1")
        self.assertTrue(result.created)
        self.assertEqual(result.record_id, 7)
        self.assertEqual(self.cursor.execute.call_count, 1)

    def test_new_delivery_for_existing_ticket_returns_existing_record(self):
        self.cursor.fetchone.side_effect = [None, (7, 1)]
        result = RefundRepository().save(self.refund, "new-delivery")
        self.assertFalse(result.created)
        self.assertEqual(result.record_id, 7)
        # The lookup must include the ticket even when the delivery ID is new.
        self.assertEqual(self.cursor.execute.call_args.args[1], ("new-delivery", 1, "new-delivery"))

    def test_conflict_without_existing_row_is_not_acknowledged(self):
        self.cursor.fetchone.side_effect = [None, None]
        with self.assertRaises(RuntimeError):
            RefundRepository().save(self.refund, "delivery-1")
