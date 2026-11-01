import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from planner.access import deployment_errors, verify_password
from planner.database import Row, postgres_schema
from planner.storage import SCHEMA, Store


class HostingTests(unittest.TestCase):
    def test_hosted_setup_requires_durable_storage(self):
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": "", "STUDY_PLANNER_PASSWORD": ""}):
            self.assertEqual(len(deployment_errors()), 1)

    def test_hosted_setup_accepts_postgres_and_strong_password(self):
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": "postgresql://localhost/test", "STUDY_PLANNER_PASSWORD": "test-password-12345"}):
            self.assertEqual(deployment_errors(), [])

    def test_registration_does_not_require_an_owner_password(self):
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": "postgresql://localhost/test", "STUDY_PLANNER_PASSWORD": ""}):
            self.assertEqual(deployment_errors(), [])

    def test_hosted_store_does_not_fall_back_to_ephemeral_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": "", "STUDY_PLANNER_DB": str(Path(directory)/"blocked.sqlite3")}):
                with self.assertRaisesRegex(ValueError, "PostgreSQL"):
                    Store()
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_password_verification(self):
        with patch.dict(os.environ, {"STUDY_PLANNER_PASSWORD": "private-password-12345"}):
            self.assertTrue(verify_password("private-password-12345"))
            self.assertFalse(verify_password("wrong"))
        with patch.dict(os.environ, {"STUDY_PLANNER_PASSWORD": ""}):
            self.assertFalse(verify_password(""))

    def test_postgres_schema_uses_serial_and_quotes_reserved_column(self):
        translated = postgres_schema(SCHEMA)
        self.assertNotIn("AUTOINCREMENT", translated)
        self.assertIn('"end" TEXT NOT NULL', translated)
        self.assertIn("DOUBLE PRECISION", translated)

    def test_row_works_with_both_mapping_and_scalar_access(self):
        row = Row({"id": 42, "name": "Math"})
        self.assertEqual(row[0], row["id"])
        self.assertEqual(dict(row)["name"], "Math")

    def test_login_gate_and_sign_out(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"VERCEL": "", "DATABASE_URL": "", "STUDY_PLANNER_DB": str(Path(directory)/"local.sqlite3"), "STUDY_PLANNER_PASSWORD": "test-private-password"}):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"), default_timeout=20).run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual(len(app.sidebar.radio), 0)
                app.radio[0].set_value("Existing workspace").run()
                app.text_input[0].set_value("wrong")
                next(b for b in app.button if b.label == "Open my planner").click().run()
                self.assertTrue(app.error)
                app.text_input[0].set_value("test-private-password")
                next(b for b in app.button if b.label == "Open my planner").click().run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual(app.sidebar.radio[0].value, "Today")
                next(b for b in app.button if b.label == "Sign out").click().run()
                self.assertEqual(len(app.sidebar.radio), 0)


if __name__ == "__main__":
    unittest.main()
