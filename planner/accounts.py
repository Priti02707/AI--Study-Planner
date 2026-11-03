"""Username accounts, salted password hashes, expiring sessions, and throttling.

Study records live in separate schemas/files; the registry holds identity only.
Session token hashes persist in the database. Hosted browsers resume via an HttpOnly cookie.
"""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time

from planner.access import verify_password
from planner.storage import Store
from planner.validation import text

ITERATIONS = 600_000
SESSION_SECONDS = 24 * 60 * 60
OWNER_ID = "original-workspace"
AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_accounts (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 password_hash TEXT NOT NULL, created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_auth_sessions (
 token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES app_accounts(id) ON DELETE CASCADE,
 expires_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_login_attempts (
 username TEXT PRIMARY KEY, failures INTEGER NOT NULL, blocked_until BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_recovery (
 account_id TEXT PRIMARY KEY REFERENCES app_accounts(id) ON DELETE CASCADE,
 question TEXT NOT NULL, answer_hash TEXT NOT NULL, code_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS app_auth_expiry ON app_auth_sessions(expires_at);
"""


def username(value):
    result = str(value).strip().casefold()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", result):
        raise ValueError("Use 3–40 letters, numbers, dots, underscores, or hyphens for your username. Start with a letter or number.")
    return result


def validate_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("Use a password with 12–128 characters.")
    return password


def hash_password(password):
    validate_password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def check_password(password, encoded):
    if not isinstance(password, str) or len(password) > 128:
        return False
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(rounds) != ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, path=None):
        self.store = Store(path, schema=AUTH_SCHEMA)

    def register(self, name, handle, password, question=None, answer=None, code=None):
        name, handle = text(name, "Your name", 80), username(handle)
        encoded = hash_password(password)
        recovery = self._recovery_fields(question, answer, code) if question is not None else None
        account_id = secrets.token_hex(16)
        try:
            with self.store.connect() as db:
                db.execute("INSERT INTO app_accounts(id,username,display_name,password_hash,created_at) VALUES (?,?,?,?,?)",
                           (account_id, handle, name, encoded, int(time.time())))
                if recovery:
                    self._save_recovery(db, account_id, recovery)
        except sqlite3.IntegrityError:
            raise ValueError("That username is unavailable. Choose another one.") from None
        return account_id

    @staticmethod
    def _recovery_fields(question, answer, code):
        question = text(question, "Security question", 160)
        answer = text(answer, "Security answer", 128).casefold()
        return question, hash_password(answer), token_hash(code)

    @staticmethod
    def _save_recovery(db, account_id, recovery):
        db.execute(
            "INSERT INTO app_recovery VALUES (?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET "
            "question=excluded.question,answer_hash=excluded.answer_hash,code_hash=excluded.code_hash",
            (account_id, *recovery),
        )

    def set_recovery(self, token, password, question, answer, code):
        identity = self.identity(token)
        if not identity or identity["id"] == OWNER_ID:
            raise ValueError("Sign in to a student account first.")
        with self.store.connect() as db:
            row = db.execute("SELECT password_hash FROM app_accounts WHERE id=?", (identity["id"],)).fetchone()
            if not check_password(password, row["password_hash"]):
                raise ValueError("Current password did not match.")
            self._save_recovery(db, identity["id"], self._recovery_fields(question, answer, code))
            db.execute("DELETE FROM app_login_attempts WHERE username=?", (f"#recovery:{identity['id']}",))

    def recovery_question(self, handle, code):
        with self.store.connect(write=False) as db:
            row = db.execute(
                "SELECT r.question FROM app_recovery r JOIN app_accounts a ON a.id=r.account_id "
                "WHERE a.username=? AND r.code_hash=?", (username(handle), token_hash(code.strip())),
            ).fetchone()
        if not row:
            raise ValueError("The username or recovery code did not match.")
        return row["question"]

    def reset_password(self, handle, code, answer, password):
        handle = username(handle)
        validate_password(password)
        error = None
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT r.account_id,r.answer_hash FROM app_recovery r JOIN app_accounts a ON a.id=r.account_id "
                "WHERE a.username=? AND r.code_hash=?", (handle, token_hash(code.strip())),
            ).fetchone()
            if not row:
                raise ValueError("The recovery details did not match.")
            attempt_key = f"#recovery:{row['account_id']}"
            now = int(time.time())
            attempt = db.execute("SELECT * FROM app_login_attempts WHERE username=?", (attempt_key,)).fetchone()
            if attempt and attempt["blocked_until"] > now:
                raise ValueError("Too many recovery attempts. Try again in 15 minutes.")
            if not check_password(answer.strip().casefold(), row["answer_hash"]):
                failures = (attempt["failures"] if attempt and not attempt["blocked_until"] else 0) + 1
                db.execute(
                    "INSERT INTO app_login_attempts VALUES (?,?,?) ON CONFLICT(username) DO UPDATE SET "
                    "failures=excluded.failures,blocked_until=excluded.blocked_until",
                    (attempt_key, failures, now + 900 if failures >= 5 else 0),
                )
                error = "The recovery details did not match."
            else:
                account_id = row["account_id"]
                db.execute("UPDATE app_accounts SET password_hash=? WHERE id=?", (hash_password(password), account_id))
                db.execute("DELETE FROM app_auth_sessions WHERE account_id=?", (account_id,))
                db.execute("DELETE FROM app_login_attempts WHERE username IN (?,?)", (handle, attempt_key))
                db.execute("DELETE FROM app_recovery WHERE account_id=?", (account_id,))
        if error:
            raise ValueError(error)

    def _session(self, db, account_id):
        current = int(time.time())
        db.execute("DELETE FROM app_auth_sessions WHERE expires_at<=?", (current,))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO app_auth_sessions(token_hash,account_id,expires_at) VALUES (?,?,?)",
                   (token_hash(token), account_id, current + SESSION_SECONDS))
        return token

    def sign_in(self, handle, password, owner=False):
        handle = "#original-owner" if owner else username(handle)
        error = None
        token = None
        with self.store.connect() as db:
            current = int(time.time())
            attempt = db.execute("SELECT * FROM app_login_attempts WHERE username=?", (handle,)).fetchone()
            if attempt and attempt["blocked_until"] > current:
                error = "Too many sign-in attempts. Try again in 15 minutes."
            else:
                account = db.execute("SELECT * FROM app_accounts WHERE username=?", (handle,)).fetchone()
                if owner:
                    valid = isinstance(password, str) and len(password) <= 128 and verify_password(password)
                else:
                    # Spend the same hash work for an unknown username.
                    dummy = f"pbkdf2_sha256${ITERATIONS}${'00' * 16}${'00' * 32}"
                    valid = check_password(password, account["password_hash"] if account else dummy) and account is not None
                if not valid:
                    failures = (attempt["failures"] if attempt and attempt["blocked_until"] == 0 else 0) + 1
                    blocked_until = current + 900 if failures >= 5 else 0
                    db.execute("INSERT INTO app_login_attempts(username,failures,blocked_until) VALUES (?,?,?) ON CONFLICT(username) DO UPDATE SET failures=excluded.failures,blocked_until=excluded.blocked_until",
                               (handle, failures, blocked_until))
                    error = "Username or password did not match."
                else:
                    if owner and account is None:
                        db.execute("INSERT INTO app_accounts(id,username,display_name,password_hash,created_at) VALUES (?,?,?,?,?)",
                                   (OWNER_ID, handle, "Original workspace", "", current))
                    db.execute("DELETE FROM app_login_attempts WHERE username=?", (handle,))
                    token = self._session(db, OWNER_ID if owner else account["id"])
        # Raise after committing failed attempts so throttling survives reruns.
        if error:
            raise ValueError(error)
        return token

    def identity(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 100:
            return None
        with self.store.connect(write=False) as db:
            row = db.execute("SELECT a.id,a.username,a.display_name FROM app_auth_sessions x JOIN app_accounts a ON a.id=x.account_id WHERE x.token_hash=? AND x.expires_at>?",
                             (token_hash(token), int(time.time()))).fetchone()
        return dict(row) if row else None

    def sign_out(self, token):
        if isinstance(token, str):
            with self.store.connect() as db:
                db.execute("DELETE FROM app_auth_sessions WHERE token_hash=?", (token_hash(token),))

    def change_password(self, token, current_password, new_password):
        encoded = hash_password(new_password)
        with self.store.connect() as db:
            row = db.execute("SELECT a.* FROM app_auth_sessions x JOIN app_accounts a ON a.id=x.account_id WHERE x.token_hash=? AND x.expires_at>?",
                             (token_hash(token), int(time.time()))).fetchone()
            if not row or row["id"] == OWNER_ID or not check_password(current_password, row["password_hash"]):
                raise ValueError("Current password did not match. Sign in again if your session expired.")
            db.execute("UPDATE app_accounts SET password_hash=? WHERE id=?", (encoded, row["id"]))
            db.execute("DELETE FROM app_auth_sessions WHERE account_id=?", (row["id"],))
