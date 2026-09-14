import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D
from buy_or_wait.scenario import Scenario, analyse, simulate, _events
from buy_or_wait.models import Payment

def budget(**changes):
    base = Scenario(today=date(2026, 1, 1), balance=D("2000"),
        minimum_balance=D("500"), purchase_amount=D("900"),
        deadline=date(2026, 3, 20), next_salary_date=date(2026, 1, 15),
        monthly_salary=D("1800"), monthly_rent=D("700"),
        monthly_essentials=D("300"), next_rent_date=date(2026, 1, 7))
    return replace(base, **changes)

class ForecastTests(unittest.TestCase):
    def test_full_payment_when_budget_is_sufficient(self):
        self.assertEqual(analyse(budget(balance=D("10000")))["method"], "full_payment")

    def test_bill_before_salary_prevents_immediate_purchase(self):
        result = analyse(budget(balance=D("1200"), allows_partial=False, allows_installments=False))
        self.assertEqual(result["method"], "wait")
        self.assertTrue(simulate(budget(balance=D("1200")), result["payments"])[0])

    def test_deadline_is_enforced(self):
        result = analyse(budget(balance=D("1200"), deadline=date(2026, 1, 2),
                                allows_partial=False, allows_installments=False))
        self.assertEqual(result["method"], "not_recommended")
        self.assertEqual(result["payments"], [])

    def test_earliest_capacity_is_independent_of_deadline(self):
        result = analyse(budget(balance=D("1200"), deadline=date(2026, 1, 2),
                                allows_partial=False, allows_installments=False))
        self.assertGreater(result["earliest"], date(2026, 1, 2))

    def test_monthly_essentials_total_exactly(self):
        events = _events(budget(monthly_essentials=D("310")))
        total = sum(-amount for day, entries in events.items() if day.month == 1
                    for amount, label in entries if label == "Essentials")
        self.assertEqual(total, D("310"))

    def test_month_end_salary_does_not_drift(self):
        events = _events(budget(next_salary_date=date(2026, 1, 31)))
        salary_days = [day for day, entries in events.items()
                       if any(label == "Salary" for _, label in entries)]
        self.assertIn(date(2026, 2, 28), salary_days)
        self.assertIn(date(2026, 3, 31), salary_days)

    def test_floor_above_balance_is_reported(self):
        result = analyse(budget(minimum_balance=D("2500")))
        self.assertFalse(result["baseline_safe"])
        self.assertEqual(result["safe_today"], D("0"))

    def test_past_dates_rejected(self):
        with self.assertRaises(ValueError):
            analyse(budget(deadline=date(2025, 12, 31)))

    def test_non_finite_amount_rejected(self):
        with self.assertRaises(ValueError):
            analyse(budget(balance=D("NaN")))

    def test_all_recommended_plans_are_funded(self):
        for balance in ("800", "1200", "2000", "5000"):
            s = budget(balance=D(balance))
            r = analyse(s)
            self.assertGreaterEqual(r["safe_today"], D("0"))
            self.assertLessEqual(r["safe_today"], s.purchase_amount)
            if r["payments"]:
                self.assertTrue(simulate(s, r["payments"])[0])
                self.assertLessEqual(r["payments"][-1].day, s.deadline)
                self.assertGreaterEqual(sum(p.amount for p in r["payments"]), s.purchase_amount)

if __name__ == "__main__":
    unittest.main()
