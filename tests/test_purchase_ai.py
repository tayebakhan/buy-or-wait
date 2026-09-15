
import io
import json
import unittest
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError
from buy_or_wait.purchase_ai import validate_details, extract_purchase, ExtractionError

TODAY = date(2026, 9, 14)
def details(**changes):
    data = dict(item="Laptop", amount="900.00", currency="GBP", deadline="2026-09-30")
    data.update(changes)
    return data

class PurchaseAITests(unittest.TestCase):
    def test_valid_details(self):
        value = validate_details(details(), TODAY)
        self.assertEqual(value["amount"], 900)
        self.assertEqual(value["deadline"], date(2026, 9, 30))

    def test_unknowns_stay_unknown(self):
        self.assertEqual(validate_details(dict.fromkeys(details()), TODAY), dict.fromkeys(details()))

    def test_invalid_money(self):
        for amount in ("NaN", "Infinity", "-1", "0", "1.001", "1e999", True):
            with self.subTest(amount=amount), self.assertRaises(ExtractionError):
                validate_details(details(amount=amount), TODAY)

    def test_dates_currency_and_shape(self):
        for changes in ({"deadline":"2026-01-01"}, {"deadline":"2028-01-01"}, {"deadline":"soon"}, {"currency":"BDT"}, {"item":42}):
            with self.subTest(changes=changes), self.assertRaises(ExtractionError):
                validate_details(details(**changes), TODAY)
        with self.assertRaises(ExtractionError):
            validate_details({"safe_to_pay": 999999}, TODAY)

    def test_request_contract(self):
        response = {"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":json.dumps(details())}]}}]}
        with patch("buy_or_wait.purchase_ai.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as mock:
            result = extract_purchase("Laptop £900 by 30 September", "test-only", TODAY, "GBP")
        self.assertEqual(result["amount"], 900)
        req = mock.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertNotIn("test-only", req.full_url)
        self.assertEqual(mock.call_args.kwargs["timeout"], 25)

    def test_errors_do_not_expose_provider_details(self):
        error = HTTPError("https://example.test", 429, "secret-provider-message", {}, None)
        with patch("buy_or_wait.purchase_ai.urlopen", side_effect=error):
            with self.assertRaises(ExtractionError) as caught:
                extract_purchase("Laptop", "test-only", TODAY, "GBP")
        self.assertNotIn("secret", str(caught.exception))
        self.assertIn("limit", str(caught.exception))

    def test_invalid_response(self):
        for raw in ({}, {"candidates":[{"finishReason":"MAX_TOKENS"}]}):
            with patch("buy_or_wait.purchase_ai.urlopen", return_value=io.BytesIO(json.dumps(raw).encode())):
                with self.assertRaises(ExtractionError):
                    extract_purchase("Laptop", "test-only", TODAY, "GBP")

    def test_no_call_without_key_or_text(self):
        with patch("buy_or_wait.purchase_ai.urlopen") as mock:
            for text, key in (("", "key"), ("Laptop", ""), ("a"*2001, "key")):
                with self.assertRaises(ExtractionError):
                    extract_purchase(text, key, TODAY, "GBP")
            mock.assert_not_called()

    def test_http_diagnostics_without_secret_details(self):
        for code in (401, 418):
            with self.subTest(code=code):
                error = HTTPError("https://example.test", code, "private-key-value", {}, None)
                with patch("buy_or_wait.purchase_ai.urlopen", side_effect=error):
                    with self.assertRaises(ExtractionError) as caught:
                        extract_purchase("Dyson USD 600", "test-only", TODAY, "GBP")
                self.assertIn(f"HTTP {code}", str(caught.exception))
                self.assertNotIn("private-key-value", str(caught.exception))

    def test_server_outage_uses_local_reader(self):
        unavailable = HTTPError("https://example.test", 503, "busy", {}, None)
        with patch("buy_or_wait.purchase_ai.urlopen", side_effect=unavailable), patch(
            "buy_or_wait.purchase_ai.time.sleep"
        ):
            result = extract_purchase(
                "Can I buy a $600 Dyson before Sep 20?",
                "test-only",
                TODAY,
                "GBP",
            )
        self.assertEqual(result["item"], "Dyson")
        self.assertEqual(result["amount"], 600)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["deadline"], date(2026, 9, 20))
        self.assertTrue(result["_used_local_fallback"])

    def test_retries_then_uses_fallback_model(self):
        unavailable = HTTPError("https://example.test", 503, "busy", {}, None)
        response = {
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": json.dumps(details())}]},
            }]
        }
        with patch(
            "buy_or_wait.purchase_ai.urlopen",
            side_effect=[unavailable, unavailable, io.BytesIO(json.dumps(response).encode())],
        ) as mock, patch("buy_or_wait.purchase_ai.time.sleep") as sleep:
            result = extract_purchase("A GBP 900 laptop", "test-only", TODAY, "GBP")
        self.assertEqual(result["item"], "Laptop")
        self.assertEqual(mock.call_count, 3)
        self.assertEqual(sleep.call_count, 1)
        self.assertIn("gemini-2.5-flash-lite", mock.call_args.args[0].full_url)

    def test_missing_configured_model_uses_supported_fallback(self):
        missing = HTTPError("https://example.test", 404, "not found", {}, None)
        response = {
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": json.dumps(details())}]},
            }]
        }
        with patch(
            "buy_or_wait.purchase_ai.urlopen",
            side_effect=[missing, io.BytesIO(json.dumps(response).encode())],
        ) as mock:
            result = extract_purchase(
                "A GBP 900 laptop",
                "test-only",
                TODAY,
                "GBP",
                model="unavailable-model",
            )
        self.assertEqual(result["amount"], 900)
        self.assertEqual(mock.call_count, 2)
        self.assertIn("gemini-2.5-flash", mock.call_args.args[0].full_url)
