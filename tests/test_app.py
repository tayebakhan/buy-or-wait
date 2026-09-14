import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_render_and_calculate(self):
        app = AppTest.from_file("app.py", default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 3)

    def test_no_long_dashes_in_ui_copy(self):
        text = Path("app.py").read_text()
        self.assertFalse(any(chr(code) in text for code in (0x2013, 0x2014)))
