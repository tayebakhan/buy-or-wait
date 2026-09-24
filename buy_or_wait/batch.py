"""Batch CSV engine for the Buy or Wait challenge.

The AI layer reads ambiguous evidence. This module owns all money arithmetic,
forecasting and plan selection so the final recommendation is reproducible.
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import re
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from itertools import combinations
from pathlib import Path
from statistics import median
from typing import Callable, Iterable

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
FORECAST_DAYS = 90
OUTPUT_COLUMNS = (
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
)

FILE_ALIASES = {
    "profiles": ("financial_profiles.csv", "user_profiles.csv", "profiles.csv"),
    "requests": ("requests.csv",),
    "events": ("financial_events.csv", "events.csv"),
    "options": ("request_payment_options.csv", "payment_options.csv"),
    "rates": ("exchange_rates.csv",),
    "messages": ("messages.csv",),
    "images": ("images.csv",),
}

REQUIRED_COLUMNS = {
    "profiles": {"user_id", "home_currency", "current_available_balance", "minimum_balance_to_keep"},
    "requests": {"request_id", "user_id", "request_date", "requested_amount", "desired_completion_date", "allows_partial_payment"},
    "events": {"event_id", "user_id", "direction", "amount", "currency", "event_date", "settlement_date", "status"},
    "options": {"payment_option_id", "request_id", "payment_method", "payment_amount", "number_of_payments", "first_payment_date", "payment_frequency_days", "financing_fee", "total_payable_amount"},
    "rates": {"rate_date", "from_currency", "to_currency", "rate"},
    "messages": {"message_id", "user_id", "message_text"},
    "images": {"image_id", "user_id"},
}


class DatasetError(ValueError):
    """Raised when the input corpus cannot support a safe calculation."""


def money(value: object, *, blank: Decimal | None = None) -> Decimal:
    text = "" if value is None else str(value).strip().replace(",", "")
    if not text:
        if blank is not None:
            return blank
        raise DatasetError("A required money value is blank.")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise DatasetError(f"Invalid money value: {value!r}") from exc
    if not result.is_finite():
        raise DatasetError(f"Invalid money value: {value!r}")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def day(value: object, *, blank: date | None = None) -> date:
    text = "" if value is None else str(value).strip()
    if not text:
        if blank is not None:
            return blank
        raise DatasetError("A required date is blank.")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise DatasetError(f"Invalid ISO date: {value!r}") from exc


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def split_values(value: object) -> set[str]:
    return {part.strip().lower() for part in re.split(r"[|,;]", str(value or "")) if part.strip()}


def fmt(value: Decimal) -> str:
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _round_significant(value: Decimal, digits: int) -> Decimal:
    if value == ZERO:
        return value
    quantum = Decimal(f"1e{value.copy_abs().adjusted() - digits + 1}")
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def forecast_recurring_amount(category: str, amounts: list[Decimal]) -> Decimal:
    """Estimate a recurring debit from the most useful history for its category."""
    if not amounts:
        raise DatasetError("Recurring amount history cannot be empty.")
    category = category.lower()
    if category in {"groceries", "dining"}:
        estimate = _round_significant(Decimal(str(median(amounts[-3:]))), 2)
    elif category == "transport":
        estimate = _round_significant(sum(amounts, ZERO) / len(amounts), 2)
    elif category in {"utilities", "healthcare", "shopping", "entertainment"}:
        recent = amounts[-6:]
        estimate = _round_significant(sum(recent, ZERO) / len(recent), 3)
    else:
        estimate = Decimal(str(median(amounts[-3:])))
    return estimate.quantize(CENT, rounding=ROUND_HALF_UP)


def _load_csv(root: Path, kind: str, *, optional: bool = False) -> list[dict[str, str]]:
    selected = next((root / name for name in FILE_ALIASES[kind] if (root / name).exists()), None)
    if selected is None:
        if optional:
            return []
        raise DatasetError(f"Missing {FILE_ALIASES[kind][0]} in {root}")
    with selected.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headings = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS[kind] - headings
        if missing:
            raise DatasetError(f"{selected.name} is missing columns: {', '.join(sorted(missing))}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


@dataclass(frozen=True)
class Cashflow:
    event_id: str
    when: date
    amount: Decimal
    direction: str
    category: str = ""
    inferred: bool = False

    @property
    def signed(self) -> Decimal:
        return self.amount if self.direction == "credit" else -self.amount


@dataclass(frozen=True)
class Candidate:
    status: str
    method: str
    payments: tuple[tuple[date, Decimal], ...]
    changes: tuple[str, ...] = ()
    total: Decimal = ZERO
    option_id: str = ""


class Dataset:
    def __init__(self, root: Path, tables: dict[str, list[dict[str, str]]]):
        self.root = root
        self.profiles = {row["user_id"]: row for row in tables["profiles"]}
        self.requests = tables["requests"]
        self.events = tables["events"]
        self.options = tables["options"]
        self.rates = tables["rates"]
        self.messages = tables["messages"]
        self.images = tables["images"]
        self._validate_ids()

    @classmethod
    def load(cls, root: str | Path) -> "Dataset":
        folder = Path(root)
        tables = {
            kind: _load_csv(folder, kind, optional=kind in {"options", "rates", "messages", "images"})
            for kind in FILE_ALIASES
        }
        return cls(folder, tables)

    def _validate_ids(self) -> None:
        for table, key in ((self.requests, "request_id"), (self.events, "event_id"), (self.options, "payment_option_id")):
            values = [row.get(key, "") for row in table]
            if any(not value for value in values) or len(values) != len(set(values)):
                raise DatasetError(f"{key} values must be present and unique.")
        missing_users = sorted({row["user_id"] for row in self.requests} - set(self.profiles))
        if missing_users:
            raise DatasetError(f"Requests reference unknown users: {', '.join(missing_users)}")

    def convert(self, amount: Decimal, source: str, target: str, on: date) -> Decimal:
        source, target = source.upper(), target.upper()
        if source == target:
            return amount
        exact = [row for row in self.rates if day(row["rate_date"]) == on]
        for row in exact:
            if row["from_currency"].upper() == source and row["to_currency"].upper() == target:
                return (amount * Decimal(row["rate"])).quantize(CENT, rounding=ROUND_HALF_UP)
            if row["from_currency"].upper() == target and row["to_currency"].upper() == source:
                return (amount / Decimal(row["rate"])).quantize(CENT, rounding=ROUND_HALF_UP)
        raise DatasetError(f"No {source} to {target} exchange rate for {on.isoformat()}.")

    def image_amount(self, event: dict[str, str], request_date: date, currency: str) -> Decimal:
        linked = [row for row in self.images if row.get("related_event_id") == event["event_id"]]
        if not linked:
            raise DatasetError(f"Event {event['event_id']} has no amount or linked image.")
        cache_path = self.root / "evidence_cache.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        image = linked[0]
        image_id = image["image_id"]
        cached = cache.get(image_id, {})
        if cached.get("amount"):
            return money(cached["amount"])
        relative = image.get("file_path") or image.get("path") or image.get("filename") or f"{image_id}.png"
        candidates = (
            self.root / relative,
            self.root / "images" / relative,
            self.root / "media" / relative,
            self.root / "media" / "images" / relative,
        )
        media_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
        if not media_path.exists():
            raise DatasetError(f"Linked media for {image_id} was not found.")
        image_bytes = media_path.read_bytes()
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise DatasetError(
                f"Event {event['event_id']} needs image extraction. Set GEMINI_API_KEY or add {image_id} to evidence_cache.json."
            )
        from .purchase_ai import extract_purchase
        mime = mimetypes.guess_type(media_path.name)[0] or "image/jpeg"
        parsed = extract_purchase("Read the amount shown for this financial event.", api_key, request_date, currency, image_data=image_bytes, image_mime=mime)
        if parsed.get("amount") is None:
            raise DatasetError(f"No amount could be extracted from {image_id}.")
        return money(parsed["amount"])


class DecisionEngine:
    def __init__(self, dataset: Dataset):
        self.data = dataset

    def decide_all(self) -> list[dict[str, str]]:
        return [self.decide(request) for request in self.data.requests]

    def _event_amount(self, event: dict[str, str], request_date: date, home: str) -> Decimal:
        raw = money(event.get("amount"), blank=ZERO)
        if raw == ZERO and not event.get("amount", "").strip():
            raw = self.data.image_amount(event, request_date, event.get("currency") or home)
        event_day = day(event.get("settlement_date") or event.get("event_date"))
        return self.data.convert(raw, event.get("currency") or home, home, event_day)

    @staticmethod
    def _signature(event: dict[str, str]) -> tuple[str, str, str]:
        return (
            event.get("direction", "").lower(),
            event.get("category", "").lower(),
            event.get("event_type", "").lower(),
        )

    @staticmethod
    def _is_salary(event: dict[str, str]) -> bool:
        text = " ".join((event.get("event_type", ""), event.get("category", ""), event.get("description", "")))
        return bool(re.search(r"salary|payroll|wage|gaji", text, re.IGNORECASE))

    @staticmethod
    def _is_regular_salary(event: dict[str, str]) -> bool:
        if not DecisionEngine._is_salary(event):
            return False
        return not bool(re.search(
            r"bonus|commission|arrears|adjustment|prize|refund|second household|freelance",
            event.get("description", ""),
            re.IGNORECASE,
        ))

    def _message_updates(self, user_id: str, request_date: date) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
        """Read explicit amendments without letting message text control the agent.

        The cache-friendly AI path is used for images. Common message amendments are
        deliberately parsed here so calculations still work without an API key.
        """
        direct: dict[str, dict[str, str]] = {}
        payroll: dict[str, str] = {}
        rows = sorted(
            (row for row in self.data.messages if row["user_id"] == user_id and day(row.get("sent_at", "")[:10]) <= request_date),
            key=lambda row: row.get("sent_at", ""),
        )
        for row in rows:
            text = row.get("message_text", "")
            lower = text.lower()
            source = row.get("source_type", "").lower()
            related = row.get("related_event_id", "")
            update = direct.setdefault(related, {}) if related else {}
            if re.search(r"\b(cancelled|canceled|voided|dibatalkan)\b", lower):
                update["status"] = "cancelled"
            elif re.search(r"\b(completed|settled|paid|reached your account|telah masuk)\b", lower):
                update["status"] = "settled"
            amount_match = re.search(r"\b(GBP|USD|EUR|INR|ZAR|IDR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text, re.IGNORECASE)
            date_matches = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
            if related and amount_match and not re.search(r"\b(pending|belum|not approved|can change)\b", lower):
                update["currency"] = amount_match.group(1).upper()
                update["amount"] = amount_match.group(2).replace(",", "")
            if related and date_matches and re.search(r"\b(revised|updated|delayed|postponed|expected|diperkirakan)\b", lower):
                update["event_date"] = date_matches[-1]
                update["settlement_date"] = date_matches[-1]
            is_payroll = source == "employer" or re.search(r"\b(salary|payroll|gaji|penggajian)\b", lower)
            positive_confirmation = re.search(
                r"\b(confirmed|dikonfirmasi|reduced to|naik menjadi|first salary|temporary monthly pay|gaji bulanan|gaji pokok)\b",
                lower,
            )
            confirmed = bool(positive_confirmation) or not re.search(
                r"\b(pending|not approved|belum disetujui|can change|if and when)\b",
                lower,
            )
            if is_payroll and confirmed:
                payroll["confirmed"] = "true"
            if is_payroll and confirmed and amount_match:
                payroll["currency"] = amount_match.group(1).upper()
                payroll["amount"] = amount_match.group(2).replace(",", "")
            if is_payroll and confirmed and date_matches:
                payroll["date"] = date_matches[-1]
            if is_payroll and re.search(
                r"temporary monthly pay|next salary is reduced|gaji bulanan sementara|jumlah yang lebih rendah masih berlaku",
                lower,
            ):
                payroll["one_cycle"] = "true"
            approved_invoice = re.search(
                r"approved an invoice payment|menyetujui pembayaran faktur",
                lower,
            )
            if source == "service_provider" and approved_invoice and amount_match and date_matches:
                payroll["confirmed_credit_currency"] = amount_match.group(1).upper()
                payroll["confirmed_credit_amount"] = amount_match.group(2).replace(",", "")
                payroll["confirmed_credit_date"] = date_matches[-1]
            suppresses_earnings = (
                source in {"employer", "service_provider"}
                and re.search(
                    r"payout is still pending|isn't withdrawable|isn’t withdrawable|no off-season income|"
                    r"no renewal has been confirmed|employment has ended|employment record has ended|"
                    r"kontrak musiman saat ini telah berakhir|sumber pendapatan kerja rumah tangga telah berakhir",
                    lower,
                )
            )
            if suppresses_earnings:
                payroll["suppress_income"] = "true"
        return direct, payroll

    def _cashflows(self, user_id: str, request_date: date, home: str) -> tuple[list[Cashflow], dict[str, dict[str, str]]]:
        horizon = request_date + timedelta(days=FORECAST_DAYS)
        direct_updates, payroll_update = self._message_updates(user_id, request_date)
        user_events = [dict(row) for row in self.data.events if row["user_id"] == user_id]
        for event in user_events:
            event.update(direct_updates.get(event["event_id"], {}))
        by_id = {row["event_id"]: row for row in user_events}
        ignored = {"cancelled", "canceled", "failed", "rejected", "void"}
        terminal_by_link = {
            row.get("linked_event_id"): row
            for row in user_events
            if row.get("linked_event_id") and row.get("status", "").lower() in ignored | {"settled", "completed", "paid"}
        }
        flows: list[Cashflow] = []
        explicit_signatures: set[tuple[tuple[str, str, str], date]] = set()
        for event in user_events:
            status = event.get("status", "").lower()
            direction = event.get("direction", "").lower()
            event_kind = " ".join((event.get("event_type", ""), event.get("category", ""))).lower()
            when = day(event.get("settlement_date") or event.get("event_date"))
            if status in ignored or (direction == "credit" and status == "pending") or re.search(r"unrealized|market.?value|valuation", event_kind):
                continue
            if event["event_id"] in terminal_by_link and terminal_by_link[event["event_id"]] is not event:
                continue
            if request_date <= when <= horizon:
                amount = self._event_amount(event, request_date, home)
                flows.append(Cashflow(event["event_id"], when, amount, direction, event.get("category", "")))
                explicit_signatures.add((self._signature(event), when))

        history: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
        for event in user_events:
            when = day(event.get("settlement_date") or event.get("event_date"))
            if when < request_date and event.get("status", "").lower() in {"settled", "completed", "paid"}:
                history[self._signature(event)].append(event)
        for signature, rows in history.items():
            rows.sort(key=lambda row: day(row.get("settlement_date") or row.get("event_date")))
            if signature[0] != "debit" or len(rows) < 3:
                continue
            dates = [day(row.get("settlement_date") or row.get("event_date")) for row in rows[-6:]]
            gaps = [(right - left).days for left, right in zip(dates, dates[1:])]
            typical = int(median(gaps)) if gaps else 0
            template = rows[-1]
            if 5 <= typical <= 24:
                cadence = typical
            elif 26 <= typical <= 35:
                cadence = 30
            else:
                continue
            amount_history = [self._event_amount(row, request_date, home) for row in rows]
            recurring_amount = forecast_recurring_amount(signature[1], amount_history)
            cursor = dates[-1]
            while cursor < request_date:
                cursor = add_months(cursor, 1) if cadence == 30 else cursor + timedelta(days=cadence)
            while cursor <= horizon:
                if (signature, cursor) not in explicit_signatures:
                    flows.append(Cashflow(template["event_id"], cursor, recurring_amount, signature[0], template.get("category", ""), True))
                cursor = add_months(cursor, 1) if cadence == 30 else cursor + timedelta(days=cadence)

        confirmed_salary = [
            event for event in user_events
            if event.get("direction", "").lower() == "credit"
            and self._is_salary(event)
            and day(event.get("settlement_date") or event.get("event_date")) >= request_date
            and event.get("status", "").lower() in {"scheduled", "confirmed", "settled", "completed", "paid"}
        ]
        salary_template: dict[str, str] | None = None
        salary_date: date | None = None
        salary_amount: Decimal | None = None
        if payroll_update.get("confirmed"):
            regular_history = [
                event for event in user_events
                if self._is_regular_salary(event)
                and event.get("direction", "").lower() == "credit"
                and event.get("status", "").lower() in {"settled", "completed", "paid"}
                and day(event.get("settlement_date") or event.get("event_date")) < request_date
                and event.get("amount", "").strip()
            ]
            regular_history.sort(key=lambda event: day(event.get("settlement_date") or event.get("event_date")))
            salary_template = regular_history[-1] if regular_history else (confirmed_salary[0] if confirmed_salary else None)
            if payroll_update.get("date"):
                salary_date = day(payroll_update["date"])
            elif salary_template:
                salary_date = day(salary_template.get("settlement_date") or salary_template.get("event_date"))
                while salary_date < request_date:
                    salary_date = add_months(salary_date, 1)
            if payroll_update.get("amount"):
                raw = money(payroll_update["amount"])
                salary_amount = self.data.convert(raw, payroll_update.get("currency") or home, home, salary_date or request_date)
            elif salary_template:
                salary_amount = self._event_amount(salary_template, request_date, home)
        elif confirmed_salary:
            salary_template = min(confirmed_salary, key=lambda event: day(event.get("settlement_date") or event.get("event_date")))
            salary_date = day(salary_template.get("settlement_date") or salary_template.get("event_date"))
            salary_amount = self._event_amount(salary_template, request_date, home)

        if salary_template and salary_date and salary_amount is not None:
            regular_salary_ids = {
                event["event_id"] for event in user_events if self._is_regular_salary(event)
            }
            flows = [
                flow for flow in flows
                if not (flow.direction == "credit" and flow.event_id in regular_salary_ids and flow.when >= salary_date)
            ]
            historical_amounts = [
                self._event_amount(event, request_date, home)
                for event in user_events
                if event["event_id"] in regular_salary_ids
                and event.get("status", "").lower() in {"settled", "completed", "paid"}
                and day(event.get("settlement_date") or event.get("event_date")) < request_date
                and event.get("amount", "").strip()
            ]
            usual_salary = Counter(historical_amounts).most_common(1)[0][0] if historical_amounts else salary_amount
            cursor = salary_date
            cycle = 0
            while cursor <= horizon:
                cycle_amount = salary_amount if cycle == 0 or not payroll_update.get("one_cycle") else usual_salary
                flows.append(Cashflow(salary_template["event_id"], cursor, cycle_amount, "credit", salary_template.get("category", ""), True))
                cursor = add_months(cursor, 1)
                cycle += 1
        elif not payroll_update.get("suppress_income"):
            salary_history = [
                event for event in user_events
                if self._is_regular_salary(event)
                and event.get("direction", "").lower() == "credit"
                and event.get("amount", "").strip()
                and event.get("status", "").lower() in {"settled", "completed", "paid"}
                and day(event.get("settlement_date") or event.get("event_date")) < request_date
            ]
            salary_history.sort(key=lambda event: day(event.get("settlement_date") or event.get("event_date")))
            latest_salary_text = salary_history[-1].get("description", "") if salary_history else ""
            if re.search(r"\b(final|last)\b", latest_salary_text, re.IGNORECASE):
                salary_history = []

            stable_income: dict[int, list[dict[str, str]]] = defaultdict(list)
            for event in salary_history:
                when = day(event.get("settlement_date") or event.get("event_date"))
                stable_income[when.day].append(event)
            for rows in stable_income.values():
                rows.sort(key=lambda event: day(event.get("settlement_date") or event.get("event_date")))
                if len(rows) < 3:
                    continue
                recent = rows[-3:]
                amounts = [self._event_amount(event, request_date, home) for event in recent]
                dates = [day(event.get("settlement_date") or event.get("event_date")) for event in rows[-6:]]
                gaps = [(right - left).days for left, right in zip(dates, dates[1:])]
                if not gaps or not 26 <= int(median(gaps)) <= 35:
                    continue
                cursor = dates[-1]
                while cursor < request_date:
                    cursor = add_months(cursor, 1)
                recurring_amount = Decimal(str(median(amounts))).quantize(CENT, rounding=ROUND_HALF_UP)
                while cursor <= horizon:
                    flows.append(Cashflow(rows[-1]["event_id"], cursor, recurring_amount, "credit", rows[-1].get("category", ""), True))
                    cursor = add_months(cursor, 1)

        if payroll_update.get("confirmed_credit_amount") and payroll_update.get("confirmed_credit_date"):
            credit_day = day(payroll_update["confirmed_credit_date"])
            if request_date <= credit_day <= horizon:
                raw = money(payroll_update["confirmed_credit_amount"])
                converted = self.data.convert(
                    raw,
                    payroll_update.get("confirmed_credit_currency") or home,
                    home,
                    credit_day,
                )
                flows.append(Cashflow("message_confirmed_credit", credit_day, converted, "credit", "income", True))

        return sorted(flows, key=lambda flow: (flow.when, flow.direction != "credit", flow.event_id)), by_id

    @staticmethod
    def _lowest_balance(
        opening: Decimal,
        flows: Iterable[Cashflow],
        payments: Iterable[tuple[date, Decimal]],
        removed: set[str] = frozenset(),
        reduced: dict[str, Decimal] | None = None,
    ) -> Decimal:
        reduced = reduced or {}
        ledger: dict[date, list[Decimal]] = defaultdict(list)
        for flow in flows:
            if flow.event_id not in removed:
                value = reduced.get(flow.event_id, flow.amount) if flow.direction == "debit" else flow.amount
                ledger[flow.when].append(value if flow.direction == "credit" else -value)
        for when, amount in payments:
            ledger[when].append(-amount)
        balance = opening
        low = opening
        for when in sorted(ledger):
            credits = sum((value for value in ledger[when] if value > 0), ZERO)
            debits = sum((value for value in ledger[when] if value < 0), ZERO)
            balance += credits + debits
            low = min(low, balance)
        return low.quantize(CENT)

    def _safe(
        self,
        opening: Decimal,
        floor: Decimal,
        flows: list[Cashflow],
        payments: tuple[tuple[date, Decimal], ...],
        removed: set[str] = frozenset(),
        reduced: dict[str, Decimal] | None = None,
    ) -> bool:
        return self._lowest_balance(opening, flows, payments, removed, reduced) >= floor

    def _change_sets(
        self,
        profile: dict[str, str],
        flows: list[Cashflow],
        events: dict[str, dict[str, str]],
    ) -> list[tuple[tuple[str, ...], set[str], dict[str, Decimal]]]:
        stoppable_categories = split_values(profile.get("expense_categories_user_is_willing_to_stop"))
        reducible_categories = split_values(profile.get("expense_categories_user_is_willing_to_reduce"))
        candidates: list[tuple[str, str, Decimal | None]] = []
        for event_id in sorted({flow.event_id for flow in flows if flow.direction == "debit" and flow.inferred}):
            event = events.get(event_id, {})
            category = event.get("category", "").lower()
            flexibility = event.get("flexibility", "").lower()
            if category in stoppable_categories and ("stoppable" in flexibility or flexibility in {"flexible", "optional"}):
                candidates.append((f"stop:{event_id}", event_id, None))
            if category in reducible_categories and ("reducible" in flexibility or flexibility == "flexible"):
                minimum = money(event.get("minimum_allowed_amount"), blank=ZERO)
                candidates.append((f"reduce_to:{event_id}:{fmt(minimum)}", event_id, minimum))
        candidates = candidates[:8]
        result: list[tuple[tuple[str, ...], set[str], dict[str, Decimal]]] = [((), set(), {})]
        for count in range(1, min(3, len(candidates)) + 1):
            for group in combinations(candidates, count):
                if len({item[1] for item in group}) != len(group):
                    continue
                stopped = {item[1] for item in group if item[2] is None}
                reduced = {item[1]: item[2] for item in group if item[2] is not None}
                result.append((tuple(item[0] for item in group), stopped, reduced))
        return result

    @staticmethod
    def _option_schedule(option: dict[str, str]) -> tuple[tuple[date, Decimal], ...]:
        count = int(option["number_of_payments"])
        first = day(option["first_payment_date"])
        gap = int(option["payment_frequency_days"])
        amount = money(option["payment_amount"])
        total = money(option["total_payable_amount"])
        payments = [(first + timedelta(days=index * gap), amount) for index in range(count)]
        if payments:
            payments[-1] = (payments[-1][0], total - amount * (count - 1))
        return tuple(payments)

    def decide(self, request: dict[str, str]) -> dict[str, str]:
        profile = self.data.profiles[request["user_id"]]
        request_date = day(request["request_date"])
        deadline = day(request["desired_completion_date"])
        horizon = request_date + timedelta(days=FORECAST_DAYS)
        deadline = min(deadline, horizon)
        amount = money(request["requested_amount"])
        opening = money(profile["current_available_balance"])
        floor = money(profile["minimum_balance_to_keep"])
        home = profile["home_currency"].upper()
        flows, events = self._cashflows(request["user_id"], request_date, home)
        baseline_low = self._lowest_balance(opening, flows, ())
        safe_today = min(amount, max(ZERO, baseline_low - floor)).quantize(CENT, rounding=ROUND_DOWN)
        methods = split_values(profile.get("payment_methods_user_will_consider"))
        if not methods:
            methods = {"full_payment", "partial_payment", "installments"}

        earliest = ""
        for offset in range(FORECAST_DAYS + 1):
            when = request_date + timedelta(days=offset)
            if self._safe(opening, floor, flows, ((when, amount),)):
                earliest = when.isoformat()
                break

        candidates: list[Candidate] = []
        change_sets = self._change_sets(profile, flows, events)
        options = [row for row in self.data.options if row["request_id"] == request["request_id"]]
        max_months = int(profile.get("max_installment_months") or 999)
        for changes, removed, reduced in change_sets:
            if "full_payment" in methods and self._safe(opening, floor, flows, ((request_date, amount),), removed, reduced):
                candidates.append(Candidate("affordable_now" if not changes else "affordable_with_plan", "full_payment", ((request_date, amount),), changes, amount))
            if truthy(request.get("allows_partial_payment")) and safe_today > ZERO and safe_today < amount and "partial_payment" in methods and earliest and day(earliest) <= deadline:
                remainder = amount - safe_today
                plan = ((request_date, safe_today), (day(earliest), remainder))
                if self._safe(opening, floor, flows, plan, removed, reduced):
                    candidates.append(Candidate("affordable_with_plan", "partial_payment", plan, changes, amount))
            if "installments" in methods:
                for option in options:
                    if option.get("payment_method", "").lower() != "installments":
                        continue
                    schedule = self._option_schedule(option)
                    if not schedule or schedule[-1][0] > add_months(request_date, max_months) or schedule[-1][0] > deadline:
                        continue
                    if self._safe(opening, floor, flows, schedule, removed, reduced):
                        candidates.append(Candidate("affordable_with_plan", "installments", schedule, changes, money(option["total_payable_amount"]), option["payment_option_id"]))

        if earliest and day(earliest) <= deadline and "full_payment" in methods:
            wait_plan = ((day(earliest), amount),)
            candidates.append(Candidate("affordable_later", "wait", wait_plan, (), amount))

        candidates.sort(key=lambda item: (
            bool(item.changes),
            item.total,
            item.payments[0][0] if item.payments else date.max,
            len(item.payments),
            item.option_id,
        ))
        chosen = candidates[0] if candidates else None
        if chosen:
            plan_text = "|".join(f"{when.isoformat()}:{fmt(value)}" for when, value in chosen.payments)
            changes_text = "|".join(chosen.changes) if chosen.changes else "none"
            if chosen.status == "affordable_now":
                explanation = "The full payment is safe today while keeping essential commitments covered and the minimum balance intact."
            elif chosen.status == "affordable_later":
                explanation = f"Waiting until {chosen.payments[0][0].isoformat()} keeps the forecast above the minimum balance."
            else:
                explanation = "This payment plan completes by the requested date and keeps the forecast above the minimum balance."
            status, method = chosen.status, chosen.method
        else:
            status, method, plan_text, changes_text = "not_affordable", "not_recommended", "none", "none"
            explanation = "No permitted plan completes within the 90 day forecast while protecting essential commitments and the minimum balance."
        return {
            "request_id": request["request_id"],
            "amount_safe_to_pay": fmt(safe_today),
            "affordability_status": status,
            "recommended_payment_method": method,
            "payment_plan": plan_text,
            "earliest_date_for_full_payment": earliest,
            "spending_changes_needed": changes_text,
            "decision_explanation": explanation,
        }


def write_output(rows: Iterable[dict[str, str]], destination: str | Path) -> None:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate_output(path: str | Path, expected_ids: set[str] | None = None) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
            raise DatasetError("Output columns do not exactly match the challenge schema.")
        rows = list(reader)
    ids = [row["request_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise DatasetError("output.csv contains duplicate request_id values.")
    if expected_ids is not None and set(ids) != expected_ids:
        raise DatasetError("output.csv request IDs do not match requests.csv.")
    statuses = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
    methods = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
    payment_pattern = re.compile(r"^20\d{2}-\d{2}-\d{2}:[0-9]+(?:\.[0-9]{1,2})?(?:\|20\d{2}-\d{2}-\d{2}:[0-9]+(?:\.[0-9]{1,2})?)*$")
    change_pattern = re.compile(r"^(?:stop:[^|:]+|reduce_to:[^|:]+:[0-9]+(?:\.[0-9]{1,2})?)(?:\|(?:stop:[^|:]+|reduce_to:[^|:]+:[0-9]+(?:\.[0-9]{1,2})?)){0,2}$")
    for row in rows:
        amount = money(row["amount_safe_to_pay"])
        if amount < ZERO:
            raise DatasetError(f"{row['request_id']} has a negative amount_safe_to_pay.")
        if row["affordability_status"] not in statuses:
            raise DatasetError(f"{row['request_id']} has an invalid affordability_status.")
        if row["recommended_payment_method"] not in methods:
            raise DatasetError(f"{row['request_id']} has an invalid recommended_payment_method.")
        if row["payment_plan"] != "none" and not payment_pattern.fullmatch(row["payment_plan"]):
            raise DatasetError(f"{row['request_id']} has an invalid payment_plan.")
        if row["earliest_date_for_full_payment"]:
            day(row["earliest_date_for_full_payment"])
        if row["spending_changes_needed"] != "none" and not change_pattern.fullmatch(row["spending_changes_needed"]):
            raise DatasetError(f"{row['request_id']} has invalid spending_changes_needed.")
        if row["recommended_payment_method"] == "not_recommended" and row["payment_plan"] != "none":
            raise DatasetError(f"{row['request_id']} recommends a payment with no approved method.")
    return rows


def run(dataset_dir: str | Path, output_path: str | Path) -> list[dict[str, str]]:
    dataset = Dataset.load(dataset_dir)
    rows = DecisionEngine(dataset).decide_all()
    write_output(rows, output_path)
    validate_output(output_path, {row["request_id"] for row in dataset.requests})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Buy or Wait predictions from the challenge CSV files.")
    parser.add_argument("--dataset", default="dataset", help="Folder containing the challenge CSV and media files")
    parser.add_argument("--output", default="output.csv", help="Destination CSV path")
    args = parser.parse_args(argv)
    rows = run(args.dataset, args.output)
    print(f"Wrote {len(rows)} decisions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
