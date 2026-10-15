"""Exercise the business rules at the data boundary."""

import unittest
from decimal import Decimal

from pydantic import ValidationError

from app.models.refund import RefundEvent


class RefundEventTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "ticket_id": 1842,
            "customer_id": "CUST-1842",
            "refund_amount": "29.99",
            "refund_reason": "Service outage",
            "analyst": "analyst_07",
            "refund_date": "2026-10-06T21:30:00Z",
            "status": "completed",
        }

    def test_valid_refund_preserves_exact_amount_and_timezone(self):
        refund = RefundEvent.model_validate(self.payload)
        self.assertEqual(refund.refund_amount, Decimal("29.99"))
        self.assertIsNotNone(refund.refund_date.tzinfo)

    def test_invalid_field_values_are_rejected(self):
        invalid_values = {
            "ticket_id": [0, -1, True, "1842"],
            "refund_amount": ["-1", "0", "29.999", "NaN", "Infinity"],
            "customer_id": ["", "   "],
            "refund_reason": ["", "   "],
            "analyst": ["", "   "],
            "refund_date": ["not-a-date", "2026-10-06T21:30:00"],
            "status": ["pending", "refund-completed"],
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        RefundEvent.model_validate({**self.payload, field: value})

    def test_every_field_is_required(self):
        for field in self.payload:
            with self.subTest(field=field):
                payload = self.payload.copy()
                del payload[field]
                with self.assertRaises(ValidationError):
                    RefundEvent.model_validate(payload)

    def test_unexpected_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            RefundEvent.model_validate({**self.payload, "customer_age": 32})

    def test_text_is_trimmed(self):
        refund = RefundEvent.model_validate({**self.payload, "analyst": " analyst_07 "})
        self.assertEqual(refund.analyst, "analyst_07")
