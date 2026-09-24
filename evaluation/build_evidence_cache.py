"""Build a reviewed-style amount cache from challenge images using local OCR.

This helper is intended for reproducible evaluation runs. Gemini remains the
preferred reader for the user-facing app, while OCR keeps public CI runs free.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path

CURRENCY = r"(?:GBP|USD|EUR|INR|ZAR|IDR|£|\$|€|₹)"
NUMBER = r"[0-9][0-9., \t]*[0-9]|[0-9]"


def normalize_number(raw: str) -> Decimal | None:
    value = re.sub(r"\s+", "", raw)
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        value = value.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in value:
        value = value.replace(",", ".") if len(value.rsplit(",", 1)[-1]) in {1, 2} else value.replace(",", "")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    elif "." in value and len(value.rsplit(".", 1)[-1]) == 3:
        value = value.replace(".", "")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def extract_amount(text: str, description: str = "", category: str = "", direction: str = "") -> Decimal:
    context = f"{description} {category}".lower()
    if direction.lower() == "credit" or re.search(r"salary|payroll|income", context):
        priority_labels = ("net pay", "amount paid", "total earnings")
    elif "balance" in context:
        priority_labels = ("balance due", "outstanding balance", "amount due")
    elif re.search(r"bill|invoice|grocer|receipt|order", context):
        priority_labels = ("amount due till", "net amount", "cash paid", "grand total", "item bill", "total amount", "total")
    else:
        priority_labels = ("amount due till", "net pay", "balance due", "net amount", "grand total", "item bill", "total amount", "amount due", "total")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for label in priority_labels:
        for index, line in enumerate(lines):
            if label not in line.lower():
                continue
            position = line.lower().find(label) + len(label)
            nearby = line[position:]
            if not re.search(NUMBER, nearby) and index + 1 < len(lines):
                nearby = lines[index + 1]
            values = [
                amount for raw in re.findall(NUMBER, nearby)
                if (amount := normalize_number(raw)) is not None
                and not (1900 <= amount <= 2100 and amount == amount.to_integral())
                and amount < Decimal("1000000000000")
            ]
            if values:
                return values[-1]
    labelled_candidates = []
    currency_candidates = []
    for line in text.splitlines():
        if re.search(r"\b(amount|total|due|payment|salary|rent|refund|balance)\b", line, re.IGNORECASE):
            labelled_candidates.extend(re.findall(NUMBER, line))
        for left, right in re.findall(rf"{CURRENCY}\s*({NUMBER})|({NUMBER})\s*{CURRENCY}", line, flags=re.IGNORECASE):
            currency_candidates.append(left or right)
    source = labelled_candidates or currency_candidates
    parsed = [
        amount for raw in source
        if (amount := normalize_number(raw)) is not None
        and not (1900 <= amount <= 2100 and amount == amount.to_integral())
        and amount < Decimal("1000000000000")
    ]
    if not parsed:
        numeric = re.findall(NUMBER, text)
        parsed = [
            amount for raw in numeric
            if (amount := normalize_number(raw)) is not None
            and amount >= 10
            and amount < Decimal("1000000000000")
            and not (1900 <= amount <= 2100 and amount == amount.to_integral())
        ]
    if not parsed:
        raise ValueError("No positive amount found in OCR text")
    return max(parsed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="dataset")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = Path(args.dataset)
    with (root / "images.csv").open(newline="", encoding="utf-8-sig") as handle:
        images = list(csv.DictReader(handle))
    with (root / "financial_events.csv").open(newline="", encoding="utf-8-sig") as handle:
        events = {row["event_id"]: row for row in csv.DictReader(handle)}
    cache = {}
    failures = []
    for row in images:
        image_id = row["image_id"]
        path = root / "media" / "images" / f"{image_id}.png"
        try:
            result = subprocess.run(
                ["tesseract", str(path), "stdout"],
                check=True,
                capture_output=True,
                text=True,
            )
            event = events.get(row.get("related_event_id", ""), {})
            amount = extract_amount(
                result.stdout,
                event.get("description", ""),
                event.get("category", ""),
                event.get("direction", ""),
            )
            cache[image_id] = {"amount": f"{amount:.2f}"}
            print(f"{image_id}: {amount:.2f}")
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            failures.append(f"{image_id}: {exc}")
    output = Path(args.output) if args.output else root / "evidence_cache.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("OCR failures:")
        print("\n".join(failures))
    print(f"Cached {len(cache)} of {len(images)} linked images")
    return 0 if len(cache) == len(images) else 1


if __name__ == "__main__":
    raise SystemExit(main())
