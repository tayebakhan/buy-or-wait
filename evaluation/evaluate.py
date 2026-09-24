"""Evaluate a predictions CSV against the public solved sample requests."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from buy_or_wait.batch import OUTPUT_COLUMNS, DatasetError, validate_output


def _decimal_equal(left: str, right: str) -> bool:
    try:
        return Decimal(left.strip()) == Decimal(right.strip())
    except InvalidOperation:
        return False


def _payment_plan(value: str) -> tuple[tuple[str, Decimal], ...] | None:
    if value.strip() == "none":
        return ()
    try:
        return tuple((part.split(":", 1)[0], Decimal(part.split(":", 1)[1])) for part in value.strip().split("|"))
    except (InvalidOperation, IndexError):
        return None


def _spending_changes(value: str) -> tuple[tuple[str, ...], ...] | None:
    if value.strip() == "none":
        return ()
    normalized = []
    try:
        for part in value.strip().split("|"):
            bits = part.split(":")
            if bits[0] == "stop" and len(bits) == 2:
                normalized.append(("stop", bits[1]))
            elif bits[0] == "reduce_to" and len(bits) == 3:
                normalized.append(("reduce_to", bits[1], str(Decimal(bits[2]).normalize())))
            else:
                return None
    except InvalidOperation:
        return None
    return tuple(sorted(normalized))


def field_equal(field: str, left: str, right: str) -> bool:
    if field == "amount_safe_to_pay":
        return _decimal_equal(left, right)
    if field == "payment_plan":
        return _payment_plan(left) == _payment_plan(right)
    if field == "spending_changes_needed":
        return _spending_changes(left) == _spending_changes(right)
    return left.strip() == right.strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def evaluate(predictions: Path, expected: Path) -> dict[str, object]:
    predicted_rows = validate_output(predictions)
    expected_rows = read_csv(expected)
    predicted = {row["request_id"]: row for row in predicted_rows}
    expected_by_id = {row["request_id"]: row for row in expected_rows}
    missing = sorted(set(expected_by_id) - set(predicted))
    extra = sorted(set(predicted) - set(expected_by_id))
    fields = [column for column in OUTPUT_COLUMNS if column not in {"request_id", "decision_explanation"}]
    per_field = {}
    for field in fields:
        matches = sum(
            field_equal(field, predicted[request_id].get(field, ""), expected_by_id[request_id].get(field, ""))
            for request_id in set(predicted) & set(expected_by_id)
        )
        per_field[field] = {
            "matches": matches,
            "total": len(expected_by_id),
            "accuracy": round(matches / len(expected_by_id), 4) if expected_by_id else 0,
        }
    exact_rows = sum(
        all(field_equal(field, predicted[request_id].get(field, ""), expected_by_id[request_id].get(field, "")) for field in fields)
        for request_id in set(predicted) & set(expected_by_id)
    )
    amount_errors = []
    for request_id in set(predicted) & set(expected_by_id):
        expected_row = expected_by_id[request_id]
        try:
            actual_amount = Decimal(predicted[request_id]["amount_safe_to_pay"])
            expected_amount = Decimal(expected_row["amount_safe_to_pay"])
            requested_amount = Decimal(expected_row.get("requested_amount", ""))
        except InvalidOperation:
            continue
        if requested_amount <= 0:
            continue
        amount_errors.append(abs(actual_amount - expected_amount) / requested_amount)
    amount_quality = {
        "rows_scored": len(amount_errors),
        "mean_request_normalized_absolute_error": round(float(sum(amount_errors) / len(amount_errors)), 6) if amount_errors else None,
        "within_1_percent_of_request": round(sum(error <= Decimal("0.01") for error in amount_errors) / len(amount_errors), 4) if amount_errors else None,
        "within_5_percent_of_request": round(sum(error <= Decimal("0.05") for error in amount_errors) / len(amount_errors), 4) if amount_errors else None,
    }
    return {
        "expected_rows": len(expected_by_id),
        "predicted_rows": len(predicted),
        "missing_request_ids": missing,
        "extra_request_ids": extra,
        "exact_rows": exact_rows,
        "exact_row_accuracy": round(exact_rows / len(expected_by_id), 4) if expected_by_id else 0,
        "per_field": per_field,
        "amount_quality": amount_quality,
        "note": "decision_explanation is excluded from exact matching because it is free text",
    }


def to_markdown(result: dict[str, object]) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"Exact rows: {result['exact_rows']} / {result['expected_rows']} ({result['exact_row_accuracy']:.1%})",
        "",
        "| Field | Matches | Accuracy |",
        "| --- | ---: | ---: |",
    ]
    for field, values in result["per_field"].items():
        lines.append(f"| `{field}` | {values['matches']} / {values['total']} | {values['accuracy']:.1%} |")
    amount_quality = result["amount_quality"]
    mean_error = amount_quality["mean_request_normalized_absolute_error"]
    within_one = amount_quality["within_1_percent_of_request"]
    within_five = amount_quality["within_5_percent_of_request"]
    lines.extend([
        "",
        "## Monetary error",
        "",
        f"Mean absolute error as a share of the requested amount: {mean_error:.2%}" if mean_error is not None else "Mean absolute error as a share of the requested amount: not available",
        "",
        f"Within 1% of the requested amount: {within_one:.1%}" if within_one is not None else "Within 1% of the requested amount: not available",
        "",
        f"Within 5% of the requested amount: {within_five:.1%}" if within_five is not None else "Within 5% of the requested amount: not available",
    ])
    lines.extend([
        "",
        f"Missing request IDs: {', '.join(result['missing_request_ids']) or 'none'}",
        "",
        f"Extra request IDs: {', '.join(result['extra_request_ids']) or 'none'}",
        "",
        str(result["note"]),
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Buy or Wait predictions with solved sample rows.")
    parser.add_argument("--predictions", default="output.csv")
    parser.add_argument("--expected", default="dataset/sample_requests.csv")
    parser.add_argument("--report", default="evaluation/report.md")
    parser.add_argument("--json", dest="json_path", default="evaluation/report.json")
    args = parser.parse_args(argv)
    try:
        result = evaluate(Path(args.predictions), Path(args.expected))
    except (OSError, DatasetError) as exc:
        parser.error(str(exc))
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(to_markdown(result), encoding="utf-8")
    json_path = Path(args.json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(to_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
