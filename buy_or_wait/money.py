import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")

def rounded(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def display(value: Decimal, *, fixed: bool = False) -> str:
    text = f"{rounded(value):.2f}"
    return text if fixed else text.rstrip("0").rstrip(".")

def add_months(day: date, months: int = 1) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
