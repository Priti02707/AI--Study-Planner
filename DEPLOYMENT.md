# Production deployment

- Live URL: https://ai-study-planner-lac.vercel.app
- Vercel project: https://vercel.com/priti-09/ai-study-planner
- Workspace: `priti-09`
- Production deployment: `dpl_7EovhqrSsAw9itV774Dd3S6TAHyV`
- Application commit: `3f085e6` (browser password-manager autofill support).
- Includes guided setup, self-rated recall checks, practice recommendations, plan preview/acceptance, student accounts, multiple study windows, and CDN browser assets.
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

The password-manager update passed 13 account/hosting interaction checks, and Vercel confirmed the deployment as ready. Standard autocomplete hints identify usernames, existing passwords, and new passwords. Chrome controls whether it offers to save a login; appearance of that browser prompt has not been verified. Manual saving instructions are in the [user guide](docs/guide.md#browser-password-manager).

The Study coach update passed 108 application tests and 43 disposable PostgreSQL checks. GitHub Actions passed on Python 3.12 and 3.14. The knowledge check is self-rated, not AI-graded; adaptive AI question generation remains optional and requires a configured Gemini key. Core setup, recommendations, review cards, and plan preview/acceptance work offline.

Vercel confirmed this release as `READY`, and its authenticated production health check returned `{"status":"ok","errors":[]}` through the project alias. Full live coach/account verification on this release could not complete: public-domain TCP connections and subsequent authenticated-alias probes timed out from the verification network before the clients could exercise the workflow. Local interaction tests cover setup, self-check, preview, acceptance, and stale-preview invalidation; the remaining live verification is not claimed as passed. No existing student records were modified during these probes.

To explicitly test the live coach flow in new QA accounts, run `.venv/bin/python -u scripts/verify_accounts.py https://ai-study-planner-lac.vercel.app --coach`. It removes its test subjects, checks account isolation, and signs out. QA account metadata and setup settings remain; existing students' study records are untouched.

The study windows update passed all 78 local application tests before publication. After deployment, production HTTP/database health, workspace sign-in, and all six dashboard pages passed verification without changing study records. Existing saved availability remains compatible.

The initial loading update passed all 80 local tests. Opening HTML loaded in 0.50 seconds in the post-deployment HTTP check, with a CDN cache hit; this is not a full browser-interactivity measurement. Production health, sign-in, and six-page navigation passed again. See [PERFORMANCE.md](PERFORMANCE.md) for measurements and network limits.

See [Deploy from a checkout](#deploy-from-a-checkout) for the required asset preparation and publishing commands. Vercel uploads the generated `public/` directory using `.vercelignore` rules and serves it from the CDN; it is excluded from the Python bundle.

`api/index.py` exports the ASGI app from `server.py`. Vercel routes requests to that Python Function through `vercel.json`. Streamlit telemetry is disabled to avoid writes to Vercel's read-only home directory. Study data is durable in PostgreSQL; the server refuses an ephemeral SQLite fallback.

Registered accounts use separate PostgreSQL schemas; their transaction-local search path excludes the public/original workspace. The registry stores salted password hashes and hashed, expiring session tokens. Sign-out revokes the current token; password changes revoke every token for that account. Existing records are preserved in their original tables and cannot be claimed by a registrant.

Function duration is 300 seconds; reconnection can reset sign-in/timer state, while saved records remain in PostgreSQL. Hosted uploads are limited to 3 MB. The ASGI interface is experimental in the pinned Streamlit version, so verify interaction after upgrades. Email verification and automated password recovery are not implemented; save your credentials.

Local Vercel credentials, `.vercel/` project linkage, `.env.local`, and database credentials are excluded from Git and deployment uploads.

## Deploy from a checkout

Install the project dependencies using the README's local setup, then use an authenticated Vercel CLI. Keep the pinned Streamlit version: `server.py` uses its experimental `st.App` ASGI interface, exposed through `api/index.py`. Check both HTTP and WebSocket behavior after upgrades.

1. Run `vercel login` and `vercel whoami`, then link the intended project:

   ```bash
   vercel link --yes --scope priti-09 --project ai-study-planner
   ```

2. Connect PostgreSQL through Vercel Marketplace or configure an existing database. Review the provider plan before provisioning. The application role must be able to create account schemas. Set the production `DATABASE_URL` through Vercel settings, for example `postgresql://user:password@host/database?sslmode=require`; never commit credentials.
3. Optionally set `GEMINI_API_KEY`, `GEMINI_MODEL`, and `STUDY_PLANNER_TIMEZONE`. Keep `STUDY_PLANNER_PASSWORD` only if retaining access to the original workspace. New student accounts do not need that shared password.
4. Prepare the matching browser assets and deploy from the installed environment:

   ```bash
   python scripts/prepare_static.py
   vercel deploy --prod --scope priti-09
   ```

   Repeat asset preparation before each CLI deployment and whenever the Streamlit pin changes. CLI publication uses local source; it does not require a preceding GitHub push.

5. Check `/api/health`, open the dashboard, sign in, and verify saving/reloading a subject and plan. The health route checks configuration and database connectivity. A successful local ASGI smoke check alone does not verify a hosted deployment.

The function and database currently use Singapore to reduce database round trips. Schema setup is reused per process; checked database connections are pooled and duplicate reads are reused within a render, then invalidated on writes. See [PERFORMANCE.md](PERFORMANCE.md) for measurements and limits.

References: [Streamlit ASGI release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2026), [Vercel Python entrypoints](https://vercel.com/docs/functions/runtimes/python), and [Vercel WebSocket support](https://vercel.com/changelog/websocket-support-is-now-in-public-beta).
