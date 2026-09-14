import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_render_and_calculate(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        next(b for b in app.button if b.label == "Can I afford it?").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 3)

    def test_no_long_dashes_in_ui_copy(self):
        text = Path("app.py").read_text()
        self.assertFalse(any(chr(code) in text for code in (0x2013, 0x2014)))

    def test_ai_review_before_calculation(self):
        from unittest.mock import patch
        from datetime import date, timedelta
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}):
            app.run()
            app.text_area[0].set_value("A laptop for £900").run()
            details = {"item": "Laptop", "amount": 900.0, "currency": "GBP", "deadline": None}
            with patch("buy_or_wait.purchase_ai.extract_purchase", return_value=details):
                next(b for b in app.button if b.label == "Read my request").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(next(b for b in app.button if b.label == "Can I afford it?").disabled)
            app.date_input(key="purchase_deadline").set_value(date.today() + timedelta(days=30)).run()
            app.checkbox(key="ai_confirmed").check().run()
            next(b for b in app.button if b.label == "Can I afford it?").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.metric), 3)

    def test_currency_mismatch_blocks_ai_calculation(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
        app.session_state["ai_review"] = True
        app.session_state["ai_currency"] = "USD"
        app.run()
        app.checkbox(key="ai_confirmed").check().run()
        self.assertTrue(next(b for b in app.button if b.label == "Can I afford it?").disabled)
