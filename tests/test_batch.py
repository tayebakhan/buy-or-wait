import csv
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from buy_or_wait.batch import Dataset, DecisionEngine, OUTPUT_COLUMNS, forecast_recurring_amount, run, validate_output


def write_csv(root, name, fieldnames, rows):
    with (root / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class BatchEngineTests(unittest.TestCase):
    def test_category_specific_recurring_amounts(self):
        values = [Decimal(value) for value in ("10", "20", "30", "40", "50", "94")]
        self.assertEqual(forecast_recurring_amount("groceries", values), Decimal("50.00"))
        self.assertEqual(forecast_recurring_amount("transport", values), Decimal("41.00"))
        self.assertEqual(forecast_recurring_amount("dining", values), Decimal("50.00"))
        self.assertEqual(forecast_recurring_amount("utilities", values), Decimal("40.70"))
        self.assertEqual(forecast_recurring_amount("rent", values), Decimal("50.00"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        profile_fields = [
            "user_id", "home_currency", "current_available_balance", "minimum_balance_to_keep",
            "financial_priorities", "expense_categories_to_protect",
            "expense_categories_user_is_willing_to_reduce", "expense_categories_user_is_willing_to_stop",
            "payment_methods_user_will_consider", "max_installment_months",
        ]
        write_csv(self.root, "financial_profiles.csv", profile_fields, [
            {"user_id": "full", "home_currency": "GBP", "current_available_balance": "1000", "minimum_balance_to_keep": "200", "payment_methods_user_will_consider": "full_payment", "max_installment_months": "6"},
            {"user_id": "wait", "home_currency": "GBP", "current_available_balance": "500", "minimum_balance_to_keep": "200", "payment_methods_user_will_consider": "full_payment", "max_installment_months": "6"},
            {"user_id": "split", "home_currency": "GBP", "current_available_balance": "500", "minimum_balance_to_keep": "200", "payment_methods_user_will_consider": "installments", "max_installment_months": "6"},
        ])
        request_fields = ["request_id", "user_id", "request_date", "request_type", "requested_amount", "desired_completion_date", "allows_partial_payment", "request_text"]
        write_csv(self.root, "requests.csv", request_fields, [
            {"request_id": "r_full", "user_id": "full", "request_date": "2026-09-01", "request_type": "purchase", "requested_amount": "300", "desired_completion_date": "2026-09-20", "allows_partial_payment": "false", "request_text": "Laptop"},
            {"request_id": "r_wait", "user_id": "wait", "request_date": "2026-09-01", "request_type": "purchase", "requested_amount": "400", "desired_completion_date": "2026-09-20", "allows_partial_payment": "false", "request_text": "Bike"},
            {"request_id": "r_split", "user_id": "split", "request_date": "2026-09-01", "request_type": "purchase", "requested_amount": "400", "desired_completion_date": "2026-09-20", "allows_partial_payment": "false", "request_text": "Desk"},
        ])
        event_fields = ["event_id", "user_id", "event_type", "description", "category", "direction", "amount", "currency", "event_date", "settlement_date", "status", "linked_event_id", "flexibility", "minimum_allowed_amount"]
        write_csv(self.root, "financial_events.csv", event_fields, [
            {"event_id": "salary_wait", "user_id": "wait", "event_type": "salary", "description": "Confirmed salary", "category": "income", "direction": "credit", "amount": "500", "currency": "GBP", "event_date": "2026-09-10", "settlement_date": "2026-09-10", "status": "scheduled"},
            {"event_id": "salary_split", "user_id": "split", "event_type": "salary", "description": "Confirmed salary", "category": "income", "direction": "credit", "amount": "500", "currency": "GBP", "event_date": "2026-09-05", "settlement_date": "2026-09-05", "status": "scheduled"},
        ])
        option_fields = ["payment_option_id", "request_id", "payment_method", "payment_amount", "number_of_payments", "first_payment_date", "payment_frequency_days", "financing_fee", "total_payable_amount"]
        write_csv(self.root, "request_payment_options.csv", option_fields, [
            {"payment_option_id": "opt_1", "request_id": "r_split", "payment_method": "installments", "payment_amount": "200", "number_of_payments": "2", "first_payment_date": "2026-09-01", "payment_frequency_days": "10", "financing_fee": "0", "total_payable_amount": "400"},
        ])
        write_csv(self.root, "exchange_rates.csv", ["rate_date", "from_currency", "to_currency", "rate"], [])
        write_csv(self.root, "messages.csv", ["message_id", "user_id", "request_id", "related_event_id", "sent_at", "source_type", "message_text"], [])
        write_csv(self.root, "images.csv", ["image_id", "user_id", "request_id", "related_event_id"], [])

    def tearDown(self):
        self.temp.cleanup()

    def test_generates_exact_schema_and_three_plan_types(self):
        output = self.root / "output.csv"
        rows = run(self.root, output)
        self.assertEqual(tuple(rows[0]), OUTPUT_COLUMNS)
        by_id = {row["request_id"]: row for row in rows}
        self.assertEqual(by_id["r_full"]["affordability_status"], "affordable_now")
        self.assertEqual(by_id["r_full"]["recommended_payment_method"], "full_payment")
        self.assertEqual(by_id["r_wait"]["amount_safe_to_pay"], "300.00")
        self.assertEqual(by_id["r_wait"]["recommended_payment_method"], "wait")
        self.assertEqual(by_id["r_wait"]["earliest_date_for_full_payment"], "2026-09-10")
        self.assertEqual(by_id["r_split"]["recommended_payment_method"], "installments")
        self.assertEqual(by_id["r_split"]["payment_plan"], "2026-09-01:200.00|2026-09-11:200.00")
        self.assertEqual(len(validate_output(output, {"r_full", "r_wait", "r_split"})), 3)

    def test_reads_blank_event_amount_from_evidence_cache(self):
        with (self.root / "financial_events.csv").open("a", encoding="utf-8") as handle:
            handle.write("bill,full,bill,Phone bill,utilities,debit,,GBP,2026-09-02,2026-09-02,scheduled,,fixed,\n")
        write_csv(self.root, "images.csv", ["image_id", "user_id", "request_id", "related_event_id"], [
            {"image_id": "image_bill", "user_id": "full", "request_id": "", "related_event_id": "bill"},
        ])
        (self.root / "evidence_cache.json").write_text(json.dumps({"image_bill": {"amount": "75.50"}}), encoding="utf-8")
        result = DecisionEngine(Dataset.load(self.root)).decide_all()[0]
        self.assertEqual(result["amount_safe_to_pay"], "300.00")

    def test_infers_variable_monthly_income_from_a_stable_pay_date(self):
        path = self.root / "financial_events.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            fieldnames = csv.DictReader(handle).fieldnames
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            for index, (month, amount) in enumerate(((5, "400"), (6, "550"), (7, "450"), (8, "500")), start=1):
                writer.writerow({
                    "event_id": f"variable_salary_{index}", "user_id": "full", "event_type": "income",
                    "description": "Contract payment", "category": "salary", "direction": "credit",
                    "amount": amount, "currency": "GBP", "event_date": f"2026-{month:02d}-05",
                    "settlement_date": f"2026-{month:02d}-05", "status": "settled",
                    "linked_event_id": "", "flexibility": "fixed", "minimum_allowed_amount": "",
                })
        engine = DecisionEngine(Dataset.load(self.root))
        flows, _ = engine._cashflows("full", date(2026, 9, 1), "GBP")
        september_income = [flow for flow in flows if flow.direction == "credit" and flow.when == date(2026, 9, 5)]
        self.assertEqual([flow.amount for flow in september_income], [Decimal("500.00")])

    def test_does_not_repeat_a_salary_marked_final(self):
        path = self.root / "financial_events.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            fieldnames = csv.DictReader(handle).fieldnames
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            for index, month in enumerate((5, 6, 7, 8), start=1):
                writer.writerow({
                    "event_id": f"ending_salary_{index}", "user_id": "full", "event_type": "income",
                    "description": "Final payroll" if month == 8 else "Payroll", "category": "salary",
                    "direction": "credit", "amount": "500", "currency": "GBP",
                    "event_date": f"2026-{month:02d}-15", "settlement_date": f"2026-{month:02d}-15",
                    "status": "settled", "linked_event_id": "", "flexibility": "fixed",
                    "minimum_allowed_amount": "",
                })
        engine = DecisionEngine(Dataset.load(self.root))
        flows, _ = engine._cashflows("full", date(2026, 9, 1), "GBP")
        self.assertFalse(any(flow.direction == "credit" for flow in flows))

    def test_temporary_salary_applies_for_one_cycle_then_returns_to_usual_pay(self):
        event_path = self.root / "financial_events.csv"
        with event_path.open(newline="", encoding="utf-8") as handle:
            fieldnames = csv.DictReader(handle).fieldnames
        with event_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            for index, month in enumerate((5, 6, 7, 8), start=1):
                writer.writerow({
                    "event_id": f"usual_salary_{index}", "user_id": "wait", "event_type": "salary",
                    "description": "Payroll", "category": "salary", "direction": "credit", "amount": "1000",
                    "currency": "GBP", "event_date": f"2026-{month:02d}-10",
                    "settlement_date": f"2026-{month:02d}-10", "status": "settled",
                    "linked_event_id": "", "flexibility": "fixed", "minimum_allowed_amount": "",
                })
        write_csv(self.root, "messages.csv", ["message_id", "user_id", "request_id", "related_event_id", "sent_at", "source_type", "message_text"], [{
            "message_id": "temporary_pay", "user_id": "wait", "request_id": "r_wait", "related_event_id": "",
            "sent_at": "2026-08-28T09:00:00Z", "source_type": "employer",
            "message_text": "Your temporary monthly pay is GBP 500. The reduced amount continues for the next payroll.",
        }])
        engine = DecisionEngine(Dataset.load(self.root))
        flows, _ = engine._cashflows("wait", date(2026, 9, 1), "GBP")
        salaries = [(flow.when, flow.amount) for flow in flows if flow.direction == "credit"]
        self.assertIn((date(2026, 9, 10), Decimal("500.00")), salaries)
        self.assertIn((date(2026, 10, 10), Decimal("1000.00")), salaries)

    def test_adds_confirmed_invoice_credit_from_provider_message(self):
        write_csv(self.root, "messages.csv", ["message_id", "user_id", "request_id", "related_event_id", "sent_at", "source_type", "message_text"], [{
            "message_id": "invoice", "user_id": "full", "request_id": "r_full", "related_event_id": "",
            "sent_at": "2026-08-28T09:00:00Z", "source_type": "service_provider",
            "message_text": "The client approved an invoice payment of GBP 300. Settlement is expected on 2026-09-12.",
        }])
        engine = DecisionEngine(Dataset.load(self.root))
        flows, _ = engine._cashflows("full", date(2026, 9, 1), "GBP")
        self.assertIn((date(2026, 9, 12), Decimal("300.00")), [(flow.when, flow.amount) for flow in flows if flow.direction == "credit"])

    def test_adds_one_time_payroll_arrears_only_once(self):
        event_path = self.root / "financial_events.csv"
        with event_path.open(newline="", encoding="utf-8") as handle:
            fieldnames = csv.DictReader(handle).fieldnames
        with event_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            for index, month in enumerate((6, 7, 8), start=1):
                writer.writerow({
                    "event_id": f"arrears_salary_{index}", "user_id": "wait", "event_type": "salary",
                    "description": "Payroll", "category": "salary", "direction": "credit", "amount": "500",
                    "currency": "GBP", "event_date": f"2026-{month:02d}-10",
                    "settlement_date": f"2026-{month:02d}-10", "status": "settled",
                    "linked_event_id": "", "flexibility": "fixed", "minimum_allowed_amount": "",
                })
        write_csv(self.root, "messages.csv", ["message_id", "user_id", "request_id", "related_event_id", "sent_at", "source_type", "message_text"], [{
            "message_id": "arrears", "user_id": "wait", "request_id": "r_wait", "related_event_id": "",
            "sent_at": "2026-08-28T09:00:00Z", "source_type": "employer",
            "message_text": "Your regular salary for the next payroll is GBP 500. It also includes a one-time arrears adjustment of GBP 125.",
        }])
        flows, _ = DecisionEngine(Dataset.load(self.root))._cashflows("wait", date(2026, 9, 1), "GBP")
        credits = [(flow.when, flow.amount) for flow in flows if flow.direction == "credit"]
        self.assertEqual(credits.count((date(2026, 9, 10), Decimal("125.00"))), 1)
        self.assertNotIn((date(2026, 10, 10), Decimal("125.00")), credits)

    def test_applies_announced_rent_increase_to_next_cycle(self):
        event_path = self.root / "financial_events.csv"
        with event_path.open(newline="", encoding="utf-8") as handle:
            fieldnames = csv.DictReader(handle).fieldnames
        with event_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            for index, month in enumerate((6, 7, 8), start=1):
                writer.writerow({
                    "event_id": f"rent_{index}", "user_id": "full", "event_type": "bill",
                    "description": "Monthly rent", "category": "rent", "direction": "debit", "amount": "100",
                    "currency": "GBP", "event_date": f"2026-{month:02d}-01",
                    "settlement_date": f"2026-{month:02d}-01", "status": "settled",
                    "linked_event_id": "", "flexibility": "fixed", "minimum_allowed_amount": "",
                })
        write_csv(self.root, "messages.csv", ["message_id", "user_id", "request_id", "related_event_id", "sent_at", "source_type", "message_text"], [{
            "message_id": "rent_rise", "user_id": "full", "request_id": "r_full", "related_event_id": "",
            "sent_at": "2026-08-25T09:00:00Z", "source_type": "landlord",
            "message_text": "The renewed lease increases monthly rent by 12% from the next payment.",
        }])
        flows, _ = DecisionEngine(Dataset.load(self.root))._cashflows("full", date(2026, 9, 1), "GBP")
        rent = [flow.amount for flow in flows if flow.category == "rent" and flow.when == date(2026, 9, 1)]
        self.assertEqual(rent, [Decimal("112.00")])

    def test_retries_a_failed_bill_that_remains_outstanding(self):
        with (self.root / "financial_events.csv").open("a", encoding="utf-8") as handle:
            handle.write("failed_bill,full,bill,Energy bill,utilities,debit,75,GBP,2026-08-28,2026-08-28,failed,,fixed,\n")
        write_csv(self.root, "messages.csv", ["message_id", "user_id", "request_id", "related_event_id", "sent_at", "source_type", "message_text"], [{
            "message_id": "bill_retry", "user_id": "full", "request_id": "r_full", "related_event_id": "failed_bill",
            "sent_at": "2026-08-30T09:00:00Z", "source_type": "utility_provider",
            "message_text": "The bill is still outstanding and another debit will be attempted.",
        }])
        flows, _ = DecisionEngine(Dataset.load(self.root))._cashflows("full", date(2026, 9, 1), "GBP")
        self.assertIn(
            (date(2026, 9, 1), Decimal("75.00")),
            [(flow.when, flow.amount) for flow in flows if flow.event_id == "failed_bill"],
        )

    def test_ignores_a_bank_confirmed_transfer_between_own_accounts(self):
        event_path = self.root / "financial_events.csv"
        with event_path.open(newline="", encoding="utf-8") as handle:
            fieldnames = csv.DictReader(handle).fieldnames
        with event_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            for event_id, direction in (("own_transfer_out", "debit"), ("own_transfer_in", "credit")):
                writer.writerow({
                    "event_id": event_id, "user_id": "full", "event_type": "transfer",
                    "description": "Account transfer", "category": "transfer", "direction": direction,
                    "amount": "250", "currency": "GBP", "event_date": "2026-08-30",
                    "settlement_date": "2026-08-30", "status": "settled", "linked_event_id": "",
                    "flexibility": "fixed", "minimum_allowed_amount": "",
                })
        write_csv(self.root, "messages.csv", ["message_id", "user_id", "request_id", "related_event_id", "sent_at", "source_type", "message_text"], [{
            "message_id": "own_transfer", "user_id": "full", "request_id": "r_full", "related_event_id": "",
            "sent_at": "2026-08-31T09:00:00Z", "source_type": "bank",
            "message_text": "The matching debit and credit came from a transfer between your two accounts.",
        }])
        flows, events = DecisionEngine(Dataset.load(self.root))._cashflows("full", date(2026, 9, 1), "GBP")
        self.assertNotIn("own_transfer_out", events)
        self.assertNotIn("own_transfer_in", events)
        self.assertFalse(any(flow.event_id.startswith("own_transfer") for flow in flows))


if __name__ == "__main__":
    unittest.main()
