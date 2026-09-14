from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .models import Payment
from .money import ZERO, add_months, decimal, rounded


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


def _events(scenario: Scenario):
    events: dict[date, list[tuple[Decimal, str]]] = {}

    def add(day: date, amount: Decimal, label: str):
        if scenario.today <= day <= scenario.today + timedelta(days=90):
            events.setdefault(day, []).append((amount, label))

    if scenario.pending_payments:
        add(scenario.today, -scenario.pending_payments, "Pending payments")
    salary_day = scenario.next_salary_date
    rent_day = add_months(scenario.today)
    essentials_day = scenario.today + timedelta(days=7)
    while salary_day <= scenario.today + timedelta(days=90):
        add(salary_day, scenario.monthly_salary, "Salary")
        salary_day = add_months(salary_day)
    while rent_day <= scenario.today + timedelta(days=90):
        add(rent_day, -scenario.monthly_rent, "Rent")
        rent_day = add_months(rent_day)
    while essentials_day <= scenario.today + timedelta(days=90):
        add(essentials_day, -(scenario.monthly_essentials / Decimal("4")), "Essentials")
        essentials_day += timedelta(days=7)
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
    _, baseline_low, baseline = simulate(scenario)
    safe_today = rounded(max(ZERO, min(scenario.purchase_amount,
                                      baseline_low - scenario.minimum_balance)))
    earliest = None
    for offset in range(91):
        day = scenario.today + timedelta(days=offset)
        if day > scenario.deadline:
            break
        if simulate(scenario, [Payment(day, scenario.purchase_amount)])[0]:
            earliest = day
            break

    candidates = []
    full = [Payment(scenario.today, scenario.purchase_amount)]
    if simulate(scenario, full)[0]:
        candidates.append((scenario.purchase_amount, scenario.today, 1, "full_payment", full))
    if scenario.allows_partial and ZERO < safe_today < scenario.purchase_amount and earliest:
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
    if earliest and earliest > scenario.today:
        wait = [Payment(earliest, scenario.purchase_amount)]
        candidates.append((scenario.purchase_amount, earliest, 1, "wait", wait))

    if candidates:
        _, _, _, method, payments = min(candidates, key=lambda item: item[:3])
        status = ("affordable_now" if method == "full_payment" else
                  "affordable_later" if method == "wait" else "affordable_with_plan")
        safe, projected_low, chart = simulate(scenario, payments)
        explanation = {
            "full_payment": "You can pay in full today and remain above your safety buffer.",
            "partial_payment": "Pay the safe amount today and the remainder when a full payment becomes safe.",
            "installments": "The instalment schedule remains above your safety buffer for the full forecast.",
            "wait": f"Wait until {earliest.isoformat()}, when the full payment becomes safe.",
        }[method]
    else:
        method, payments, status = "not_recommended", [], "not_affordable"
        safe, projected_low, chart = True, baseline_low, baseline
        explanation = "No available plan completes the purchase safely before your deadline."
    return {
        "status": status, "method": method, "safe_today": safe_today,
        "earliest": earliest, "payments": payments, "projected_low": projected_low,
        "timeline": chart, "explanation": explanation,
    }
