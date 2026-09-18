import csv
import tempfile
import unittest
from pathlib import Path

from buy_or_wait.batch import OUTPUT_COLUMNS
from evaluation.evaluate import evaluate, to_markdown


class EvaluationTests(unittest.TestCase):
    def test_reports_exact_and_per_field_accuracy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prediction = root / "prediction.csv"
            expected = root / "expected.csv"
            row = {
                "request_id": "request_1",
                "amount_safe_to_pay": "100.00",
                "affordability_status": "affordable_now",
                "recommended_payment_method": "full_payment",
                "payment_plan": "2026-09-01:100.00",
                "earliest_date_for_full_payment": "2026-09-01",
                "spending_changes_needed": "none",
                "decision_explanation": "Safe.",
            }
            for path in (prediction, expected):
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
                    writer.writeheader()
                    writer.writerow(row)
            result = evaluate(prediction, expected)
            self.assertEqual(result["exact_row_accuracy"], 1.0)
            self.assertIn("100.0%", to_markdown(result))


if __name__ == "__main__":
    unittest.main()
