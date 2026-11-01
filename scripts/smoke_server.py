"""Start an isolated local server, check HTTP readiness, and shut it down."""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, STUDY_PLANNER_DB=str(Path(directory)/"smoke.sqlite3"))
        with (Path(directory)/"server.log").open("w+") as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", str(root/"app.py"),
                 "--server.address=127.0.0.1", "--server.headless=true", "--server.port=8517",
                 "--browser.gatherUsageStats=false"],
                cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        output.seek(0)
                        raise RuntimeError(output.read())
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:8517/_stcore/health", timeout=1) as response:
                            assert response.status == 200 and response.read() == b"ok"
                        with urllib.request.urlopen("http://127.0.0.1:8517/", timeout=1) as response:
                            assert response.status == 200
                        print("Server health: 200 ok; dashboard HTTP: 200")
                        return
                    except OSError:
                        time.sleep(0.2)
                raise RuntimeError("Server did not become ready.")
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
