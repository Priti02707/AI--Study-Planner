# Production deployment

- Live URL: https://ai-study-planner-lac.vercel.app
- Vercel project: https://vercel.com/priti-09/ai-study-planner
- Workspace: `priti-09`
- Production deployment: `dpl_8kkKAcGmXabPckoPKiU8T98Qy8B5`
- Includes student registration, sign-in/sign-out, isolated workspaces, multiple study windows, and CDN browser assets.
- Function region: Singapore (`sin1`), matching the database.
- Database: Neon PostgreSQL, `ai-study-planner-db`, free plan, Singapore region.
- Published from local source using the authenticated Vercel CLI. GitHub automatic deployment is not connected.

## Opening the workspace

Open the live URL and choose **Create account**. Enter your name, a username, and a password of at least 12 characters. Returning students choose **Sign in**. Each account has its own empty planner, and **Sign out** and **Change password** appear in the sidebar.

The pre-account project data stays under **Existing workspace**. Its password is `STUDY_PLANNER_PASSWORD` in the ignored `.env.local` file. It is optional for new student accounts. To rotate the original workspace password, update the sensitive Vercel production variable and redeploy. Registered students change their own passwords inside the app; this revokes their existing sessions.

## Verified on 1 November 2026

- Production HTML: HTTP 200.
- `/api/health`: HTTP 200, healthy PostgreSQL connection.
- `/_stcore/health`: HTTP 200.
- Actual production Streamlit WebSocket connection and dashboard rendering.
- Student registration, sign-out, returning sign-in, and separate saved subjects for two accounts.
- Original workspace password gate and successful sign-in.
- Navigation to Today, Subjects, Weekly plan, Practice, Notes & AI, and Progress.
- Latest deployment runtime error query returned no errors during verification.
- Existing user study records were untouched. Two labelled QA accounts were created; their test subjects were removed and both accounts signed out. Their empty account records remain.

The accounts update passed 95 application tests and 35 disposable PostgreSQL checks. PostgreSQL checks include account schema isolation, prevention of fallback to public tables, session expiry/revocation, password changes, and preservation of original data. Live checks passed for registration, account switching, persistent private subjects, and original workspace navigation.

After the performance update, local checks passed: 70 application tests and 25 storage tests against a disposable PostgreSQL server. Live sign-in and all six page renders passed again. Measured page-render times were 0.17–0.65 seconds; see [PERFORMANCE.md](PERFORMANCE.md). Live AI provider calls were not tested; a Gemini API key has not been configured.

Recheck the production app using:

```bash
.venv/bin/python -u scripts/verify_deployment.py https://ai-study-planner-lac.vercel.app
```

For an explicit live registration/isolation check, run `scripts/verify_accounts.py` with the same URL. It creates two labelled QA accounts with unprinted random passwords, removes their test subjects, and signs them out; empty account records remain. It does not download production secrets or access pre-existing student accounts.

## Deployment implementation

The study windows update passed all 78 local application tests before publication. After deployment, production HTTP/database health, workspace sign-in, and all six dashboard pages passed verification without changing study records. Existing saved availability remains compatible.

The initial loading update passed all 80 local tests. Opening HTML loaded in 0.50 seconds in the post-deployment HTTP check, with a CDN cache hit; this is not a full browser-interactivity measurement. Production health, sign-in, and six-page navigation passed again. See [PERFORMANCE.md](PERFORMANCE.md) for measurements and network limits.

Before each CLI deployment, run `.venv/bin/python scripts/prepare_static.py` to create the matching pinned Streamlit frontend in ignored `public/`. Vercel uploads that generated directory using `.vercelignore` rules and serves it from the CDN; it is excluded from the Python bundle. Do not omit preparation or change the Streamlit pin without regenerating assets.

`api/index.py` exports the ASGI app from `server.py`. Vercel routes requests to that Python Function through `vercel.json`. Streamlit telemetry is disabled to avoid writes to Vercel's read-only home directory. Study data is durable in PostgreSQL; the server refuses an ephemeral SQLite fallback.

Registered accounts use separate PostgreSQL schemas; their transaction-local search path excludes the public/original workspace. The registry stores salted password hashes and hashed, expiring session tokens. Sign-out revokes the current token; password changes revoke every token for that account. Existing records are preserved in their original tables and cannot be claimed by a registrant.

Function duration is 300 seconds; reconnection can reset sign-in/timer state, while saved records remain in PostgreSQL. Hosted uploads are limited to 3 MB. The ASGI interface is experimental in the pinned Streamlit version, so verify interaction after upgrades. Email verification and automated password recovery are not implemented; save your credentials.

Local Vercel credentials, `.vercel/` project linkage, `.env.local`, and database credentials are excluded from Git and deployment uploads.
