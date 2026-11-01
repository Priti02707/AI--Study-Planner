"""ASGI entrypoint for Vercel and uvicorn, preserving the Streamlit dashboard."""

from pathlib import Path
from asyncio import to_thread
import os

# Serverless filesystems have no writable home directory. Disable Streamlit's
# optional telemetry before it initializes its installation identifier.
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

import streamlit as st
from starlette.responses import JSONResponse
from starlette.routing import Route

from planner.access import deployment_errors


async def health(request):
    errors = deployment_errors()
    if not errors and os.environ.get("DATABASE_URL"):
        def check_database():
            import psycopg
            with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as db:
                db.execute("SELECT 1").fetchone()
        try:
            await to_thread(check_database)
        except Exception:
            errors = ["The database connection is unavailable."]
    return JSONResponse({"status": "configuration_required" if errors else "ok", "errors": errors},
                        status_code=503 if errors else 200)


app = st.App(Path(__file__).with_name("app.py"), routes=[Route("/api/health", health)])
