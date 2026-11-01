"""Hosted configuration and access to the preserved original workspace."""

import hmac
import os


def hosted():
    return os.environ.get("VERCEL") == "1"


def verify_password(entered):
    expected = os.environ.get("STUDY_PLANNER_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(str(entered).encode(), expected.encode())


def deployment_errors():
    if not hosted():
        return []
    errors = []
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        errors.append("Connect a PostgreSQL database and set DATABASE_URL.")
    return errors
