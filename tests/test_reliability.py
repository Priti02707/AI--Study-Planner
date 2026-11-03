import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from planner.accounts import Accounts
from planner.materials import retrieve
from planner.storage import Store


class ReliabilityTests(unittest.TestCase):
    def test_reset_requires_both_factors_and_revokes_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            accounts = Accounts(Path(directory) / "accounts.sqlite3")
            code = secrets.token_urlsafe(24)
            accounts.register("Tester", "tester", "old-password-123", "What is my phrase?", "long secret phrase", code)
            token = accounts.sign_in("tester", "old-password-123")
            with self.assertRaises(ValueError):
                accounts.recovery_question("tester", "wrong code")
            self.assertEqual(accounts.recovery_question("tester", code), "What is my phrase?")
            with self.assertRaises(ValueError):
                accounts.reset_password("tester", code, "wrong answer", "new-password-123")
            accounts.reset_password("tester", code, "Long Secret Phrase", "new-password-123")
            self.assertIsNone(accounts.identity(token))
            self.assertTrue(accounts.sign_in("tester", "new-password-123"))
            with self.assertRaises(ValueError):
                accounts.recovery_question("tester", code)

    def test_browser_store_and_backup_round_trip_bypass_hosted_database(self):
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": "postgresql://unused"}):
            original = Store(browser_workspace=True)
            original.seed_demo()
            backup = original.backup()
            restored = Store(browser_workspace=True)
            self.assertEqual(restored.subjects(), [])
            restored.restore(backup)
            self.assertEqual(json.loads(backup)["tables"], json.loads(restored.backup())["tables"])
            with self.assertRaisesRegex(ValueError, "empty workspace"):
                restored.restore(backup)
            broken = json.loads(backup)
            broken["tables"]["cards"][0]["topic_id"] = -1
            empty = Store(browser_workspace=True)
            with self.assertRaises(ValueError):
                empty.restore(json.dumps(broken))
            self.assertEqual(empty.subjects(), [])

    def test_retrieval_ranks_typo_match_and_rejects_unrelated_query(self):
        documents = [{"id": 1, "name": "Math", "pages": ["Gradient descent minimizes a loss function.", "Circles have a radius."]}]
        self.assertEqual(retrieve("gradent descent", documents)[0]["label"], "Math · page 1")
        self.assertEqual(retrieve("volcano", documents), [])
