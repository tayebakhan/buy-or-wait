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
NUMBER = r"[0-9][0-9.,\s]*[0-9]|[0-9]"


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


def extract_amount(text: str) -> Decimal:
    labelled = re.findall(
        rf"(?:amount|total|due|payment|salary|rent|refund|balance)[^\n]{{0,35}}?({CURRENCY})?\s*({NUMBER})",
        text,
        flags=re.IGNORECASE,
    )
    currency_values = re.findall(rf"{CURRENCY}\s*({NUMBER})|({NUMBER})\s*{CURRENCY}", text, flags=re.IGNORECASE)
    candidates = []
    for match in labelled:
        candidates.append(match[-1])
    for left, right in currency_values:
        candidates.append(left or right)
    parsed = [amount for raw in candidates if (amount := normalize_number(raw)) is not None]
    if not parsed:
        numeric = re.findall(NUMBER, text)
        parsed = [amount for raw in numeric if (amount := normalize_number(raw)) is not None and amount >= 10]
    if not parsed:
        raise ValueError("No positive amount found in OCR text")
    return max(parsed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="dataset")
    parser.add_argument("--output", default="dataset/evidence_cache.json")
    args = parser.parse_args(argv)
    root = Path(args.dataset)
    with (root / "images.csv").open(newline="", encoding="utf-8-sig") as handle:
        images = list(csv.DictReader(handle))
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
            amount = extract_amount(result.stdout)
            cache[image_id] = {"amount": f"{amount:.2f}"}
            print(f"{image_id}: {amount:.2f}")
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            failures.append(f"{image_id}: {exc}")
    Path(args.output).write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("OCR failures:")
        print("\n".join(failures))
    print(f"Cached {len(cache)} of {len(images)} linked images")
    return 0 if len(cache) == len(images) else 1


if __name__ == "__main__":
    raise SystemExit(main())
