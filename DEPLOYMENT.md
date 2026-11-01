# Production deployment

- Live URL: https://ai-study-planner-lac.vercel.app
- Vercel project: https://vercel.com/priti-09/ai-study-planner
- Workspace: `priti-09`
- Production deployment: `dpl_4VZCqFHFa1V3RPS7g4UF1gxQfNLA`
- Database: Neon PostgreSQL, `ai-study-planner-db`, free plan, Singapore region.
- Published from local source using the authenticated Vercel CLI. GitHub automatic deployment is not connected.

## Opening the workspace

Open the live URL. Use the value of `STUDY_PLANNER_PASSWORD` in the local `.env.local` file. This file is ignored by Git and contains private settings; do not upload it or paste its contents publicly.

To change the password, update the sensitive `STUDY_PLANNER_PASSWORD` environment variable in Vercel's production project settings and redeploy. Update your local copy if you want to rerun the verification script.

## Verified on 1 November 2026

- Production HTML: HTTP 200.
- `/api/health`: HTTP 200, healthy PostgreSQL connection.
- `/_stcore/health`: HTTP 200.
- Actual production Streamlit WebSocket connection and dashboard rendering.
- Private workspace password gate and successful sign-in.
- Navigation to Today, Subjects, Weekly plan, Practice, Notes & AI, and Progress.
- Latest deployment runtime error query returned no errors during verification.
- No study records were added or changed during live verification.

Local checks also passed: 63 application tests, 18 storage tests against a disposable PostgreSQL server, and ASGI HTTP/WebSocket smoke tests. Live AI provider calls were not tested; a Gemini API key has not been configured.

Recheck the production app using:

```bash
.venv/bin/python -u scripts/verify_deployment.py https://ai-study-planner-lac.vercel.app
```

## Deployment implementation

`api/index.py` exports the ASGI app from `server.py`. Vercel routes requests to that Python Function through `vercel.json`. Streamlit telemetry is disabled to avoid writes to Vercel's read-only home directory. Study data is durable in PostgreSQL; the server refuses an ephemeral SQLite fallback.

The workspace uses one shared owner password, not separate student accounts. Function duration is 300 seconds; reconnection can reset sign-in/timer state, while saved records remain in PostgreSQL. Hosted uploads are limited to 3 MB. The ASGI interface is experimental in the pinned Streamlit version, so verify interaction after upgrades.

Local Vercel credentials, `.vercel/` project linkage, `.env.local`, and database credentials are excluded from Git and deployment uploads.
