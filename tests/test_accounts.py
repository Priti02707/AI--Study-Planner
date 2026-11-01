"""Account lifecycle and private workspace contracts for SQLite and PostgreSQL."""
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from planner.accounts import Accounts, OWNER_ID, SESSION_SECONDS, check_password, hash_password
from planner.clock import now
from planner.database import workspace_schema
from planner.models import Slot
from planner.storage import Store


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "registry.sqlite3"
        self.accounts = Accounts(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def register(self, handle="student.one"):
        return self.accounts.register("Student", handle, "correct-password-12345")

    def workspace(self, account_id):
        return Store(self.path, workspace_id=account_id)

    def test_registration_normalizes_username_and_rejects_duplicates(self):
        account_id = self.register(" Student.One ")
        token = self.accounts.sign_in("STUDENT.ONE", "correct-password-12345")
        self.assertEqual(self.accounts.identity(token)["id"], account_id)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.register("student.one")
        for handle in ["../escape", "xy", "a" * 41, "__owner__", "#original-owner", "user name"]:
            with self.subTest(handle=handle), self.assertRaises(ValueError):
                self.register(handle)

    def test_passwords_are_salted_and_never_stored_as_plaintext(self):
        first = self.register()
        second = self.register("student.two")
        with self.accounts.store.connect(write=False) as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM app_accounts")]
        hashes = [row["password_hash"] for row in rows]
        self.assertNotEqual(hashes[0], hashes[1])
        self.assertNotIn("correct-password-12345", json.dumps(rows))
        self.assertTrue(all(check_password("correct-password-12345", encoded) for encoded in hashes))
        self.assertFalse(check_password("wrong", hashes[0]))
        self.assertFalse(check_password("wrong", "invalid hash"))
        for password in ["short", "a" * 129, None]:
            with self.subTest(password=password), self.assertRaises(ValueError):
                hash_password(password)
        self.assertNotEqual(first, second)

    def test_expiring_revocable_sessions_store_only_token_hashes(self):
        self.register()
        with patch("planner.accounts.time.time", return_value=1000):
            token = self.accounts.sign_in("student.one", "correct-password-12345")
            self.assertIsNotNone(self.accounts.identity(token))
            with self.accounts.store.connect(write=False) as db:
                rows = [dict(row) for row in db.execute("SELECT * FROM app_auth_sessions")]
            self.assertNotIn(token, json.dumps(rows))
            self.assertIsNone(self.accounts.identity(rows[0]["token_hash"]))
            self.assertIsNone(self.accounts.identity("invalid"))
        with patch("planner.accounts.time.time", return_value=1000 + SESSION_SECONDS):
            self.assertIsNone(self.accounts.identity(token))
        fresh = self.accounts.sign_in("student.one", "correct-password-12345")
        self.accounts.sign_out(fresh)
        self.assertIsNone(self.accounts.identity(fresh))

    def test_failed_sign_ins_are_throttled_across_registry_instances(self):
        self.register()
        with patch("planner.accounts.time.time", return_value=1000):
            for _ in range(5):
                with self.assertRaisesRegex(ValueError, "did not match"):
                    self.accounts.sign_in("student.one", "wrong")
            with self.assertRaisesRegex(ValueError, "15 minutes"):
                Accounts(self.path).sign_in("student.one", "correct-password-12345")
            with self.assertRaisesRegex(ValueError, "did not match"):
                self.accounts.sign_in("unknown.user", "wrong")
        with patch("planner.accounts.time.time", return_value=1901):
            token = self.accounts.sign_in("student.one", "correct-password-12345")
            self.assertIsNotNone(self.accounts.identity(token))

    def test_password_change_revokes_all_sessions_only_for_that_account(self):
        self.register()
        self.register("student.two")
        token = self.accounts.sign_in("student.one", "correct-password-12345")
        other_session = self.accounts.sign_in("student.one", "correct-password-12345")
        other_account = self.accounts.sign_in("student.two", "correct-password-12345")
        with self.assertRaisesRegex(ValueError, "Current password"):
            self.accounts.change_password(token, "wrong", "updated-password-12345")
        self.assertIsNotNone(self.accounts.identity(token))
        self.accounts.change_password(token, "correct-password-12345", "updated-password-12345")
        self.assertIsNone(self.accounts.identity(token))
        self.assertIsNone(self.accounts.identity(other_session))
        self.assertIsNotNone(self.accounts.identity(other_account))
        with self.assertRaisesRegex(ValueError, "did not match"):
            self.accounts.sign_in("student.one", "correct-password-12345")
        self.assertIsNotNone(self.accounts.identity(self.accounts.sign_in("student.one", "updated-password-12345")))

    def test_owner_access_preserves_original_data_and_uses_separate_credentials(self):
        legacy = Store(self.path)
        legacy.save_setting("private", "original owner secret")
        with patch.dict("os.environ", {"STUDY_PLANNER_PASSWORD": "original-private-password"}):
            with self.assertRaisesRegex(ValueError, "did not match"):
                self.accounts.sign_in("", "wrong", owner=True)
            token = self.accounts.sign_in("", "original-private-password", owner=True)
        self.assertEqual(self.accounts.identity(token)["id"], OWNER_ID)
        account_id = self.register()
        self.assertIsNone(self.workspace(account_id).setting("private", None))
        self.assertEqual(Store(self.path).setting("private", None), "original owner secret")
        with self.assertRaises(ValueError):
            self.accounts.sign_in("#original-owner", "original-private-password")

    def test_separate_accounts_have_independent_data_and_exports(self):
        alice, bob = self.workspace(self.register()), self.workspace(self.register("student.two"))
        start = now().replace(second=0, microsecond=0)
        for store, secret in [(alice, "Alice private notes"), (bob, "Bob private notes")]:
            subject = store.save_subject("Math", 5, 10, start + timedelta(days=5))
            topic = store.save_topic(subject, "Algebra", 120)
            card = store.add_card(topic, secret, "answer")
            store.assessment(topic, 2, 10, secret, "correction")
            store.save_document(subject, "private.txt", [secret])
            store.save_setting("availability", secret)
            store.plan([Slot(start, start + timedelta(hours=2))], save=True, start=start)
            store.review_card(card, 3, reviewed_at=start + timedelta(minutes=1))
        for _ in range(3):
            for account, secret, excluded in [(alice, "Alice private notes", "Bob private notes"), (bob, "Bob private notes", "Alice private notes")]:
                fresh = self.workspace(account.workspace_id)
                self.assertEqual(len(fresh.subjects()), 1)
                self.assertEqual(fresh.setting("availability", None), secret)
                self.assertEqual(fresh.cards()[0]["question"], secret)
                backup = fresh.backup()
                self.assertIn(secret, backup)
                self.assertNotIn(excluded, backup)
                self.assertNotIn("password_hash", backup)
                self.assertEqual(len(json.loads(backup)["tables"]["review_logs"]), 1)
        bob_sessions = self.workspace(bob.workspace_id).sessions()
        alice.plan([Slot(start, start + timedelta(hours=1))], save=True, start=start)
        self.assertEqual(self.workspace(bob.workspace_id).sessions(), bob_sessions)
        alice.delete_subject(alice.subjects()[0]["id"])
        self.assertEqual(len(self.workspace(bob.workspace_id).topics()), 1)

    def test_other_accounts_cannot_access_foreign_ids_in_an_empty_workspace(self):
        alice, bob = self.workspace(self.register()), self.workspace(self.register("student.two"))
        subject = alice.save_subject("Private subject", 5, 10, now() + timedelta(days=2))
        topic = alice.save_topic(subject, "Private topic", 60)
        card = alice.add_card(topic, "private card", "answer")
        with self.assertRaises(ValueError):
            bob.save_topic(subject, "intrusion", 60)
        with self.assertRaises(ValueError):
            bob.review_card(card, 3)
        with self.assertRaises(ValueError):
            bob.finish_session(1, "skipped")
        self.assertEqual(bob.documents(subject), [])
        bob.delete_subject(subject)
        self.assertEqual(len(self.workspace(alice.workspace_id).subjects()), 1)
        self.assertEqual(len(self.workspace(alice.workspace_id).topics()), 1)

    def test_workspace_identifiers_cannot_inject_paths_or_schemas(self):
        for value in ["../secret", 'public"; DROP TABLE subjects;--', "public", "", "a" * 31]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.workspace(value)
        self.assertEqual(workspace_schema(None), "public")


if __name__ == "__main__":
    unittest.main()
