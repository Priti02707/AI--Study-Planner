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

            with patch.dict(os.environ, {"DATABASE_URL": url}), patch("tests.test_planner.Store", side_effect=lambda *args, **kwargs: Store()):
                result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PostgresTests))
            return 0 if result.wasSuccessful() else 1
        finally:
            close_pools()
            subprocess.run(["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
                           check=True, capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
