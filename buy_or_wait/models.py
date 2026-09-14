from dataclasses import dataclass
from datetime import date
from decimal import Decimal

@dataclass(frozen=True)
class Payment:
    day: date
    amount: Decimal
