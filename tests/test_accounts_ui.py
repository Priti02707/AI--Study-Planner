"""User registration, sign-in, sign-out, and switching accounts in the dashboard."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from planner.accounts import Accounts
from planner.storage import Store


class AccountDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"STUDY_PLANNER_DB": str(Path(self.temp.name) / "accounts.sqlite3"),
                                                   "DATABASE_URL": "", "VERCEL": "", "STUDY_PLANNER_PASSWORD": "", "GEMINI_API_KEY": ""})
        self.environment.start()
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def field(self, label, value):
        next(w for w in self.app.text_input if w.label == label).set_value(value)

    def button(self, label):
        next(b for b in self.app.button if b.label == label).click().run()
        self.assertEqual(list(self.app.exception), [])

    def register(self, name="Alice", handle="alice.student"):
        self.app.radio[0].set_value("Create account").run()
        self.field("Your name", name)
        self.field("Choose a username", handle)
        self.field("Password", "student-password-12345")
        self.field("Confirm password", "student-password-12345")
        self.button("Create my account")

    def sign_in(self, handle="alice.student", password="student-password-12345"):
        self.field("Username", handle)
        self.field("Password", password)
        self.button("Sign in")

    def test_register_sign_out_and_sign_in_again_preserves_data(self):
        self.assertEqual(len(self.app.sidebar.radio), 0)
        self.register()
        self.assertEqual(self.app.sidebar.radio[0].value, "Today")
        self.button("Load sample subjects")
        accounts = Accounts()
        token = self.app.session_state["account_token"]
        account_id = accounts.identity(token)["id"]
        self.assertEqual(len(Store(workspace_id=account_id).subjects()), 3)
        self.app.session_state["quiz"] = {"private": "previous account material"}
        self.button("Sign out")
        self.assertIsNone(accounts.identity(token))
        self.assertNotIn("quiz", self.app.session_state)
        self.assertEqual(len(self.app.sidebar.radio), 0)
        self.sign_in()
        self.assertEqual(self.app.sidebar.radio[0].value, "Today")
        self.assertFalse(any(b.label == "Load sample subjects" for b in self.app.button))

    def test_account_switch_shows_an_empty_private_planner(self):
        self.register()
        self.button("Load sample subjects")
        self.button("Sign out")
        self.register("Bob", "bob.student")
        identity = Accounts().identity(self.app.session_state["account_token"])
        self.assertEqual(identity["username"], "bob.student")
        self.assertEqual(Store(workspace_id=identity["id"]).subjects(), [])
        self.assertTrue(any(b.label == "Load sample subjects" for b in self.app.button))
        self.assertNotIn("quiz", self.app.session_state)

    def test_mismatching_passwords_do_not_register(self):
        self.app.radio[0].set_value("Create account").run()
        self.field("Your name", "Alice")
        self.field("Choose a username", "alice.student")
        self.field("Password", "student-password-12345")
        self.field("Confirm password", "another-password-12345")
        self.button("Create my account")
        self.assertIn("do not match", self.app.error[0].value)
        with self.assertRaisesRegex(ValueError, "did not match"):
            Accounts().sign_in("alice.student", "student-password-12345")

    def test_wrong_password_and_expired_session_do_not_show_study_data(self):
        self.register()
        token = self.app.session_state["account_token"]
        self.button("Sign out")
        self.sign_in(password="wrong")
        self.assertIn("did not match", self.app.error[0].value)
        self.assertEqual(len(self.app.sidebar.radio), 0)
        self.app.session_state["account_token"] = token
        self.app.session_state["quiz"] = "private stale data"
        self.app.run()
        self.assertEqual(len(self.app.sidebar.radio), 0)
        self.assertNotIn("quiz", self.app.session_state)

    def test_change_password_signs_out_and_accepts_new_password(self):
        self.register()
        self.field("Current password", "student-password-12345")
        self.field("New password", "updated-password-12345")
        self.field("Confirm new password", "updated-password-12345")
        self.button("Update password")
        self.assertEqual(len(self.app.sidebar.radio), 0)
        self.assertTrue(any("Password changed" in s.value for s in self.app.success))
        self.sign_in(password="updated-password-12345")
        self.assertEqual(self.app.sidebar.radio[0].value, "Today")


if __name__ == "__main__":
    unittest.main()
