"""Run the storage contract against a disposable local PostgreSQL cluster.

Requires initdb and pg_ctl on PATH. Never connects to an existing database.
"""

import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import psycopg
    from planner.storage import Store
    from planner.database import clear_schema_cache, close_pools
    from tests.test_planner import StoreTests
    from tests.test_accounts import AccountTests
    from tests.test_coach import CoachTests
    from planner.accounts import Accounts

    with tempfile.TemporaryDirectory(prefix="study-planner-pg-") as directory:
        root = Path(directory)
        cluster = root/"cluster"
        subprocess.run(["initdb", "-D", str(cluster), "--no-locale", "-E", "UTF8", "-A", "trust"],
                       check=True, capture_output=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        subprocess.run(["pg_ctl", "-D", str(cluster), "-l", str(root/"postgres.log"),
                        "-o", f"-h 127.0.0.1 -p {port} -k {directory}", "-w", "start"],
                       check=True, capture_output=True)
        url = f"postgresql://127.0.0.1:{port}/postgres?sslmode=disable"
        try:
            class PostgresTests(StoreTests):
                def setUp(self):
                    clear_schema_cache()
                    with psycopg.connect(url, autocommit=True) as connection:
                        connection.execute("DROP SCHEMA public CASCADE")
                        connection.execute("CREATE SCHEMA public")
                    super().setUp()

                def test_recreate_store_skips_schema_ddl(self):
                    with patch("planner.database.PostgresConnection.executescript", side_effect=AssertionError("Repeated schema setup")):
                        self.assertEqual(Store().topics()[0]["name"], "Algebra")

            class PostgresAccountTests(AccountTests):
                def setUp(self):
                    clear_schema_cache()
                    with psycopg.connect(url, autocommit=True) as connection:
                        # All schemas belong to this disposable test cluster.
                        names = connection.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'workspace_%'").fetchall()
                        for (name,) in names:
                            connection.execute(psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(psycopg.sql.Identifier(name)))
                        connection.execute("DROP SCHEMA public CASCADE")
                        connection.execute("CREATE SCHEMA public")
                    super().setUp()

                def test_workspace_search_path_does_not_fall_back_to_public(self):
                    account_id = self.register()
                    store = self.workspace(account_id)
                    with store.connect(write=False) as db:
                        row = db.execute("SELECT current_schema()").fetchone()
                        self.assertEqual(row[0], f"workspace_{account_id}")
                    # The registry exists in public, but is unreachable through
                    # an account's ordinary unqualified database queries.
                    with self.assertRaises(psycopg.errors.UndefinedTable):
                        store.rows("SELECT * FROM app_accounts")
                    token = self.accounts.sign_in("student.one", "correct-password-12345")
                    self.assertEqual(self.accounts.identity(token)["id"], account_id)

            with patch.dict(os.environ, {"DATABASE_URL": url}), patch("tests.test_planner.Store", side_effect=lambda *args, **kwargs: Store()):
                result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PostgresTests))
            with patch.dict(os.environ, {"DATABASE_URL": url}), patch("tests.test_accounts.Accounts", side_effect=lambda *args, **kwargs: Accounts()), patch("tests.test_accounts.Store", side_effect=lambda *args, **kwargs: Store(workspace_id=kwargs.get("workspace_id"))):
                accounts_result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PostgresAccountTests))
            class PostgresCoachTests(CoachTests):
                def setUp(self):
                    clear_schema_cache()
                    with psycopg.connect(url, autocommit=True) as connection:
                        connection.execute("DROP SCHEMA public CASCADE")
                        connection.execute("CREATE SCHEMA public")
                    super().setUp()

            with patch.dict(os.environ, {"DATABASE_URL": url}), patch("tests.test_coach.Store", side_effect=lambda *args, **kwargs: Store()):
                coach_result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PostgresCoachTests))
            return 0 if result.wasSuccessful() and accounts_result.wasSuccessful() and coach_result.wasSuccessful() else 1
        finally:
            close_pools()
            subprocess.run(["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
                           check=True, capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
