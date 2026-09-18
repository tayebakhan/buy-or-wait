import unittest
from decimal import Decimal

from evaluation.build_evidence_cache import extract_amount, normalize_number


class EvidenceCacheTests(unittest.TestCase):
    def test_normalizes_common_currency_formats(self):
        self.assertEqual(normalize_number("42,750,000"), Decimal("42750000"))
        self.assertEqual(normalize_number("1.422,85"), Decimal("1422.85"))
        self.assertEqual(normalize_number("1,422.85"), Decimal("1422.85"))

    def test_prefers_labelled_currency_amount(self):
        text = "Invoice 2026-09-01\nTotal due: EUR 625.40\nReference 88422"
        self.assertEqual(extract_amount(text), Decimal("625.40"))


if __name__ == "__main__":
    unittest.main()
