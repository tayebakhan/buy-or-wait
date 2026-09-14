from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .models import Payment
from .money import ZERO, add_months, rounded
from calendar import monthrange
from decimal import ROUND_DOWN


@dataclass(frozen=True)
class Scenario:
    today: date
    balance: Decimal
    minimum_balance: Decimal
    purchase_amount: Decimal
    deadline: date
    next_salary_date: date
    monthly_salary: Decimal
    monthly_rent: Decimal
    monthly_essentials: Decimal
    pending_payments: Decimal = ZERO
    allows_partial: bool = True
    allows_installments: bool = True
    installment_months: int = 3
    installment_fee: Decimal = ZERO
    next_rent_date: date | None = None


def _events(scenario: Scenario):
    events: dict[date, list[tuple[Decimal, str]]] = {}

    def add(day: date, amount: Decimal, label: str):
        if scenario.today <= day <= scenario.today + timedelta(days=90):
            events.setdefault(day, []).append((amount, label))

    if scenario.pending_payments:
        add(scenario.today, -scenario.pending_payments, "Pending payments")
    salary_day = scenario.next_salary_date
    rent_day = scenario.next_rent_date or add_months(scenario.today)
    salary_index = rent_index = 0
    rent_anchor = rent_day
    while salary_day <= scenario.today + timedelta(days=90):
        add(salary_day, scenario.monthly_salary, "Salary")
        salary_index += 1
        salary_day = add_months(scenario.next_salary_date, salary_index)
    while rent_day <= scenario.today + timedelta(days=90):
        add(rent_day, -scenario.monthly_rent, "Rent")
        rent_index += 1
        rent_day = add_months(rent_anchor, rent_index)
    for offset in range(91):
        day = scenario.today + timedelta(days=offset)
        days = Decimal(monthrange(day.year, day.month)[1])
        # Cumulative rounding allocates exactly the monthly budget over a full month.
        spent = rounded(scenario.monthly_essentials * Decimal(day.day) / days)
        previous = rounded(scenario.monthly_essentials * Decimal(day.day - 1) / days)
        add(day, -(spent - previous), "Essentials")
    return events


def simulate(scenario: Scenario, payments: list[Payment] | None = None):
    events = _events(scenario)
    for payment in payments or []:
        events.setdefault(payment.day, []).append((-payment.amount, "Requested expense"))
    balance = scenario.balance
    minimum = balance
    timeline = []
    for offset in range(91):
        day = scenario.today + timedelta(days=offset)
        # Credits post before debits on a shared settlement date.
        for amount, _ in sorted(events.get(day, []), key=lambda item: item[0], reverse=True):
            balance += amount
        minimum = min(minimum, balance)
        timeline.append({"date": day, "balance": float(rounded(balance)),
                         "floor": float(scenario.minimum_balance)})
    return minimum >= scenario.minimum_balance, rounded(minimum), timeline


def analyse(scenario: Scenario):
    for value in (scenario.balance, scenario.minimum_balance, scenario.purchase_amount,
                  scenario.monthly_salary, scenario.monthly_rent, scenario.monthly_essentials,
                  scenario.pending_payments, scenario.installment_fee):
        if not value.is_finite() or value < ZERO:
            raise ValueError("Amounts must be finite and non-negative.")
    if scenario.purchase_amount <= ZERO:
        raise ValueError("Enter a purchase amount greater than zero.")
    end = scenario.today + timedelta(days=90)
    if not scenario.today <= scenario.deadline <= end:
        raise ValueError("Choose a deadline within the next 90 days.")
    if scenario.next_salary_date < scenario.today or (
            scenario.next_rent_date and scenario.next_rent_date < scenario.today):
        raise ValueError("Next payment dates cannot be in the past.")
    if scenario.installment_months not in (2, 3):
        raise ValueError("Choose two or three monthly payments.")
    baseline_safe, baseline_low, baseline = simulate(scenario)
    safe_today = rounded(max(ZERO, min(scenario.purchase_amount,
                                      baseline_low - scenario.minimum_balance))).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    earliest = None
    for offset in range(91):
        day = scenario.today + timedelta(days=offset)
        if simulate(scenario, [Payment(day, scenario.purchase_amount)])[0]:
            earliest = day
            break

    candidates = []
    full = [Payment(scenario.today, scenario.purchase_amount)]
    if simulate(scenario, full)[0]:
        candidates.append((scenario.purchase_amount, scenario.today, 1, "full_payment", full))
    if scenario.allows_partial and ZERO < safe_today < scenario.purchase_amount and earliest and earliest <= scenario.deadline:
        partial = [Payment(scenario.today, safe_today),
                   Payment(earliest, scenario.purchase_amount - safe_today)]
        if simulate(scenario, partial)[0]:
            candidates.append((scenario.purchase_amount, scenario.today, 2, "partial_payment", partial))
    if scenario.allows_installments and scenario.installment_months > 1:
        total = scenario.purchase_amount + scenario.installment_fee
        payment_amount = rounded(total / Decimal(scenario.installment_months))
        installments = [Payment(add_months(scenario.today, index), payment_amount)
                        for index in range(scenario.installment_months)]
        # Put any rounding remainder into the last payment.
        installments[-1] = Payment(installments[-1].day,
                                   installments[-1].amount + total - sum(p.amount for p in installments))
        if installments[-1].day <= scenario.deadline and simulate(scenario, installments)[0]:
            candidates.append((total, installments[0].day, len(installments), "installments", installments))
    if earliest and scenario.today < earliest <= scenario.deadline:
        wait = [Payment(earliest, scenario.purchase_amount)]
        candidates.append((scenario.purchase_amount, earliest, 1, "wait", wait))

    if candidates:
        _, _, _, method, payments = min(candidates, key=lambda item: item[:3])
        status = ("affordable_now" if method == "full_payment" else
                  "affordable_later" if method == "wait" else "affordable_with_plan")
        safe, projected_low, chart = simulate(scenario, payments)
        explanation = {
            "full_payment": "Based on these numbers, you can pay today and still keep your bills covered and savings buffer intact.",
            "partial_payment": "Pay some today and the rest on the date below. Both payments fit within your budget.",
            "installments": "These monthly payments fit around your bills while keeping your buffer intact.",
            "wait": f"Wait until {earliest.isoformat()}, when the full payment becomes safe.",
        }[method]
    else:
        method, payments, status = "not_recommended", [], "not_affordable"
        safe, projected_low, chart = True, baseline_low, baseline
        explanation = "None of these payment options fit your budget by the deadline. Try a lower price or a later date."
    return {
        "status": status, "method": method, "safe_today": safe_today,
        "earliest": earliest, "payments": payments, "projected_low": projected_low,
        "timeline": chart, "explanation": explanation, "baseline_safe": baseline_safe,
    }
