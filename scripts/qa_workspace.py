"""Start an isolated QA planner: python -m scripts.qa_workspace."""
import os
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

from planner.accounts import Accounts


def main():
    with TemporaryDirectory(prefix="study-planner-qa-") as directory:
        database = Path(directory) / "qa.sqlite3"
        for key in ("DATABASE_URL", "VERCEL", "STUDY_PLANNER_PASSWORD"):
            os.environ.pop(key, None)
        os.environ["STUDY_PLANNER_DB"] = str(database)

        accounts = Accounts(database)
        for handle in ("qa_student", "qa_isolation"):
            password = secrets.token_urlsafe(24)
            account_id = accounts.register("QA Student", handle, password)
            token = accounts.sign_in(handle, password)
            if accounts.identity(token)["id"] != account_id:
                raise RuntimeError("QA account identity check failed")
            accounts.sign_out(token)
            print(f"QA login: {handle} / {password}", flush=True)

        from streamlit.web.cli import main as streamlit_main

        streamlit_main(["run", str(Path(__file__).resolve().parents[1] / "app.py"),
                        "--server.address", "127.0.0.1", "--server.headless", "true"])


if __name__ == "__main__":
    main()
