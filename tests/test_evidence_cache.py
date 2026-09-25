import unittest
from decimal import Decimal

from evaluation.build_evidence_cache import extract_amount, extract_consensus_amount, normalize_number


class EvidenceCacheTests(unittest.TestCase):
    def test_normalizes_common_currency_formats(self):
        self.assertEqual(normalize_number("42,750,000"), Decimal("42750000"))
        self.assertEqual(normalize_number("1.422,85"), Decimal("1422.85"))
        self.assertEqual(normalize_number("1,422.85"), Decimal("1422.85"))

    def test_prefers_labelled_currency_amount(self):
        text = "Invoice 2026-09-01\nTotal due: EUR 625.40\nReference 88422"
        self.assertEqual(extract_amount(text, "Outstanding invoice"), Decimal("625.40"))

    def test_uses_event_context_for_balance_and_net_pay(self):
        receipt = "Total Amount 200,000\nAmount Received 100,000\nBalance Due 100,000"
        payslip = "Total Earnings IDR 4,780,800\nNet Pay IDR 4,365,000"
        self.assertEqual(extract_amount(receipt, "Outstanding rent balance"), Decimal("100000"))
        self.assertEqual(extract_amount(payslip, "August net salary", direction="credit"), Decimal("4365000"))

    def test_uses_consensus_across_ocr_layout_modes(self):
        texts = [
            "Grand Total ₹2.00",
            "Grand Total ₹2,298",
            "TOTAL AMOUNT ₹2,298",
        ]
        self.assertEqual(extract_consensus_amount(texts, "Grocery receipt"), Decimal("2298"))


if __name__ == "__main__":
    unittest.main()
