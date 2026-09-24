import csv
import tempfile
import unittest
from pathlib import Path

from buy_or_wait.batch import OUTPUT_COLUMNS
from evaluation.evaluate import evaluate, field_equal, to_markdown


class EvaluationTests(unittest.TestCase):
    def test_semantic_money_fields_ignore_formatting_and_change_order(self):
        self.assertTrue(field_equal("amount_safe_to_pay", "100.00", "100"))
        self.assertTrue(field_equal("payment_plan", "2026-09-01:100.00", "2026-09-01:100"))
        self.assertTrue(field_equal(
            "spending_changes_needed",
            "stop:event_2|reduce_to:event_1:23.50",
            "reduce_to:event_1:23.5|stop:event_2",
        ))

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

    def test_reports_request_normalized_money_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prediction = root / "prediction.csv"
            expected = root / "expected.csv"
            predicted_row = {
                "request_id": "request_1", "amount_safe_to_pay": "90", "affordability_status": "affordable_now",
                "recommended_payment_method": "full_payment", "payment_plan": "2026-09-01:100",
                "earliest_date_for_full_payment": "2026-09-01", "spending_changes_needed": "none",
                "decision_explanation": "Safe.",
            }
            expected_row = {**predicted_row, "amount_safe_to_pay": "100", "requested_amount": "200"}
            with prediction.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
                writer.writeheader()
                writer.writerow(predicted_row)
            with expected.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=(*OUTPUT_COLUMNS, "requested_amount"))
                writer.writeheader()
                writer.writerow(expected_row)
            result = evaluate(prediction, expected)
            self.assertEqual(result["amount_quality"]["mean_request_normalized_absolute_error"], 0.05)
            self.assertEqual(result["amount_quality"]["within_5_percent_of_request"], 1.0)


if __name__ == "__main__":
    unittest.main()
