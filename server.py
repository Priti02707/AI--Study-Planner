"""ASGI entrypoint for Vercel and uvicorn, preserving the Streamlit dashboard."""

from pathlib import Path
from asyncio import to_thread
import os

# Serverless filesystems have no writable home directory. Disable Streamlit's
# optional telemetry before it initializes its installation identifier.
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ["STUDY_PLANNER_ASGI"] = "1"

import streamlit as st
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from planner.access import deployment_errors
from planner.accounts import Accounts, OWNER_ID, SESSION_SECONDS
from planner.browser_state import SESSION_COOKIE


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


async def test_workspace(request):
    return RedirectResponse("/?workspace=test")


async def persist_session(request):
    if request.headers.get("sec-fetch-site") != "same-origin":
        return Response(status_code=403)
    token_bytes = bytearray()
    async for chunk in request.stream():
        if len(token_bytes) + len(chunk) > 100:
            return Response(status_code=400)
        token_bytes.extend(chunk)
    token = token_bytes.decode("ascii", errors="replace")
    if not 20 <= len(token) <= 100:
        return Response(status_code=400)
    identity = await to_thread(lambda: Accounts().identity(token))
    if not identity or identity["id"] == OWNER_ID:
        return Response(status_code=401)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https" or os.environ.get("VERCEL") == "1",
                        samesite="strict")
    return response


app = st.App(Path(__file__).with_name("app.py"), routes=[
    Route("/api/health", health), Route("/api/session", persist_session, methods=["POST"]),
    Route("/test", test_workspace),
])
