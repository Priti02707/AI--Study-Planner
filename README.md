# 🌱 AI Study Planner

**Live app:** https://ai-study-planner-lac.vercel.app · hosted in `priti-09/ai-study-planner`.

Create an account on the live app, then sign in with your own username and password. Every account has a separate private planner. The original project data remains under **Existing workspace**, protected by `STUDY_PLANNER_PASSWORD` in the ignored `.env.local` file. See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment and verification details.

The performance update reduces measured page rendering from 9–18 seconds to 0.17–0.65 seconds in the live navigation check. See [PERFORMANCE.md](PERFORMANCE.md) for the method and limits, and [FEATURES_ADDED.md](FEATURES_ADDED.md) for a plain-language feature summary. Refresh an existing browser tab after deployment.

An explainable study planner that turns subjects, exam dates, available time, and quiz results into a realistic revision schedule.

Built with Python and Streamlit by **Priti Kumari**. Use SQLite locally or PostgreSQL when hosted. The core planner works offline without an API key. Optional Gemini features help extract syllabus topics, generate practice questions, and answer questions from your notes.

## Run locally

Requires **Python 3.12 or newer**.

```bash
git clone https://github.com/Priti02707/AI--Study-Planner.git
cd AI--Study-Planner
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell. Open **http://localhost:8501** after starting the app.

For the console edition, run:

```bash
python python.py
```

## First five minutes

Choose **Create account**, enter your name, a username, and a password of at least 12 characters. You will enter your own empty planner. Returning students use **Sign in**. Use **Sign out** or **Change password** in the sidebar. Usernames ignore case; save your credentials because email recovery is not included.

For guided setup, open **Study coach**. Enter your first subject, current marks, exam goal, syllabus topics, estimated work, and daily availability. Try a **Knowledge check**, then **Preview my starting plan → Accept and save plan**. Existing students can open the coach directly for recommendations and replanning.

Knowledge checks ask you to explain a topic from memory, compare it with your notes or a saved card, and rate recall from 0–5. They are self-rated diagnostics, not automatically graded quizzes. A low rating with a correction of at least 20 characters creates a review card. The rating is saved as an assessment and influences future planning. Empty or very short explanations are rejected.

Next-practice recommendations use up to three recent topic assessments, weighted 3:2:1 from newest to oldest. Below 50% suggests **Foundation**, 50–79% **Standard**, and 80% or above **Challenge**. Subject marks are the fallback. This is a transparent heuristic, not an estimate of exam performance. The planner continues using its existing latest-score priority formula. Optional AI question sets use the suggested level and recent mistake text while retaining source evidence checks.

The coach previews seven days using saved windows, breaks, and days off. Previewing does not change sessions; accepting recalculates from current records and preserves finished history. Previews expire after five minutes or changes to planning inputs. No topic import or AI call is required for manual setup, self-checks, or recommendations.

1. Open **Today** and choose **Load sample subjects**, or add your own in **Subjects**.
2. Enter current marks, maximum marks, target score, and exam date/time.
3. Break each subject into topics with estimated work, difficulty, and optional prerequisites.
4. In **Weekly plan**, enter your weekday availability, session length, breaks, and days off. Add a row for each free window (for example, Monday at 08:00 for 60 minutes and Monday at 18:00 for 90 minutes). Generate a timetable.
5. Record completed, partial, or skipped sessions in **Today**. Record quiz results in **Practice**, then regenerate your plan.

Replanning preserves completed work and redistributes unfinished work into future available time. Record any partial work before regenerating.

## What is included

| Workspace | Features |
| --- | --- |
| Today | Today's sessions, overdue alerts, weak-topic suggestions, completed/partial/skipped work |
| Study coach | Guided setup, self-rated recall checks, practice levels, corrective cards, and a starting plan to preview and accept |
| Subjects | Add/edit subjects, normalized marks, target scores, exam dates/times, topics, difficulty, cycle-checked prerequisites |
| Weekly plan | Weekday free-time windows, days off, configurable focus/break lengths, preview, replanning, shortfall details |
| Practice | Manual quiz scores, flashcards, adaptive review queue, optional AI multiple-choice quizzes |
| Notes & AI | Local PDF/text import, page viewer, local passage search, editable AI topic suggestions, source-based answers |
| Progress | Completed-work indicators, active-time charts, quiz history, mistake notebook, focus timer, JSON export |

Exports include CSV and an `.ics` calendar file. Optional AI quiz mistakes become review cards automatically.

## How scheduling works

The planner uses a **deterministic greedy algorithm**, not a trained model. It fills free time windows with eligible topic/review sessions, using:

```text
priority = 0.40 × weakness
         + 0.30 × exam urgency
         + 0.20 × workload pressure
         + 0.05 × normalized difficulty
         + 0.05 × due-review indicator
```

- Weakness is `1 - latest topic quiz score`; subject marks are the fallback.
- Exam urgency is `1 / max(days until exam, 1)`.
- Workload pressure is remaining task minutes divided by remaining free minutes before its exam, capped at 1. Breaks are applied when placing sessions.
- A small repeated-subject penalty encourages interleaving when priorities are otherwise close.
- Prerequisites finish before dependent study tasks. Review cards are scheduled after the topic's remaining learning work.
- Sessions do not overlap, exceed a free-time window, or run past their exam.
- Unscheduled minutes are reported, including work that falls beyond the selected planning window. They are not necessarily a permanent deadline shortfall.

Every session includes a readable reason. The weights are adjustable engineering heuristics, not validated predictions of academic performance. The target percentage is stored as a student goal; it is not used to predict the mark needed or to calculate priority.

### Study duration adaptation

When a learning session is recorded, the planner updates a smoothed pace ratio:

```text
new_pace = 0.7 × previous_pace + 0.3 × (actual_active_minutes / completed_planned_minutes)
```

The observed ratio is bounded to reduce the effect of timer accidents. Remaining workload is rescaled by the change in pace. Regenerate the plan to apply revised estimates. This is an explainable heuristic, not an ML model.

### Spaced revision

Cards use **SM-2 based intervals**, starting at one day, then six days after successful recalls, then increasing with an easiness factor. Ratings range from 0 (forgot) to 5 (easy). Failed recall resets the card to a one-day retry. This version does not implement SuperMemo's full same-day relearning loop or FSRS optimization.

Reference: [original SuperMemo SM-2 description](https://www.super-memory.com/english/ol/sm2.htm).

## Optional AI setup

Export environment variables **before** starting Streamlit:

```bash
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-2.5-flash"
python -m streamlit run app.py
```

In PowerShell, use `$env:GEMINI_API_KEY="your-key"` and `$env:GEMINI_MODEL="gemini-2.5-flash"`.

The model name is configurable because provider availability can change. `.env.example` documents the settings; `.env` files are **not** loaded automatically. Keys are read on the server and are never written to the database or repository.

- AI calls happen only when you press a generation/answer button.
- Selected note excerpts and your request are sent to Google's Gemini API. Adaptive quizzes also include up to three recent mistake prompts, which can include self-check explanations. This may use your provider quota.
- Topic generation uses up to the first 30 document excerpts; large documents may need splitting.
- Quiz generation and tutoring use local lexical retrieval to select relevant page excerpts. This is a lightweight retrieval-augmented workflow, without embeddings or a vector database.
- Responses use structured JSON. Source IDs and evidence excerpts are checked against the material supplied to the model. These checks do not prove that an answer is correct; inspect source pages and review AI topic suggestions before importing.
- If AI is unavailable, manual topic entry, quiz logging, cards, planning, and local search continue to work.

References: [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Streamlit](https://docs.streamlit.io/get-started/fundamentals/main-concepts), [pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

## Saved data and timezone

SQLite stores the account registry in `data/study_planner.sqlite3` and each account's subjects, topics, exams, sessions, assessments, cards, review history, imported text, and availability in `data/workspaces/<account-id>.sqlite3`. The original local workspace remains in `data/study_planner.sqlite3`. Saved records survive process restarts.

Optional environment variables:

```bash
export STUDY_PLANNER_DB="data/study_planner.sqlite3"
export STUDY_PLANNER_TIMEZONE="Asia/Kolkata"
```

Dates are stored as wall times in the configured timezone. Calendar export converts them to UTC. Keep the same timezone for an existing database. If using a timezone with daylight-saving changes, check sessions around clock transitions manually; the scheduler does not resolve ambiguous or nonexistent local times.

Local mode binds to `127.0.0.1`. Hosted mode requires PostgreSQL. Accounts use separate PostgreSQL schemas with transaction-local search paths that exclude the original workspace. Locally, accounts use separate SQLite files. Registration creates a new empty workspace and cannot claim existing project data. The same subject names and topic IDs can exist independently in different accounts.

Passwords use individually salted PBKDF2-HMAC-SHA256 hashes with 600,000 iterations. Server-side sessions expire after 24 hours, are revoked by sign-out, and all of an account's sessions are revoked when its password changes. Five failed sign-ins for a username trigger a 15-minute lockout. Browser session recycling may require an earlier sign-in. This version does not provide email verification, password recovery, social sign-in, or administrator account management.

To open pre-account project data, set `STUDY_PLANNER_PASSWORD` to a password of at least 12 characters before launching, then choose **Existing workspace**. On the deployed project, the existing password continues to work. This compatibility workspace is separate from registered accounts.

Use **Progress → Export all my data** for a readable JSON snapshot of your current account's study records; authentication records are excluded. For a full restorable local backup, stop the app and copy the entire `data/` directory (or the registry file and adjacent `workspaces/` directory at a custom database path). Restore while stopped. JSON import is not included yet. Local data, virtual environments, generated browser assets, and secrets are excluded from Git.

Password hashing reference: [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

## Vercel deployment

The pinned Streamlit version includes experimental `st.App` ASGI support. `server.py` wraps the existing dashboard as an ASGI application; `api/index.py` exposes it as a file-based Vercel Python Function, and `vercel.json` routes requests to that function. A frontend rewrite is not required for this path. Keep the pinned version until changes have been tested against both HTTP and WebSocket behavior.

Required project environment variables:

```text
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
```

Optional: `GEMINI_API_KEY`, `GEMINI_MODEL`, `STUDY_PLANNER_TIMEZONE`, and `STUDY_PLANNER_PASSWORD` (only for access to the original shared workspace).

1. Sign into Vercel with `vercel login` and verify with `vercel whoami`.
2. Link/create the project in the intended scope: `vercel link --yes --scope priti-09 --project ai-study-planner` (the CLI may prompt to create a new project).
3. Connect a PostgreSQL database through Vercel Marketplace, such as Neon. Select the free plan when available; do not enable a paid plan without reviewing it.
4. Confirm the integration sets `DATABASE_URL` for the intended deployment environment. Keep `STUDY_PLANNER_PASSWORD` as a sensitive environment variable if retaining access to the original workspace; new student accounts do not need it. The database role must be able to create account schemas.
5. Run `python scripts/prepare_static.py` with the installed project dependencies, then `vercel deploy --prod --scope priti-09`. The preparation step copies the pinned Streamlit browser assets into ignored `public/` for CDN delivery. Repeat it after changing Streamlit. CLI deployment can publish local committed source without first pushing GitHub.
6. Verify `/api/health`, open the dashboard, sign in, and test saving/reloading a subject and plan. The health route checks required configuration and database connectivity.

The app creates its tables on first use. PostgreSQL writes take a shared transaction-level advisory lock to keep replanning consistent across function instances. Reads use consistent snapshots. Production refuses an ephemeral SQLite fallback.

Tables are initialized once per function process/schema version. Database connections are pooled and checked before reuse. Duplicate reads are reused only within one render and cleared on writes. The deployed function and database both use Singapore to reduce database round trips.

The initial HTML and framework JavaScript, styles, and fonts are served directly from Vercel's CDN. Versioned assets receive a one-year immutable cache lifetime; the HTML is revalidated so deployments can update its asset references. The private workspace still requires a Python/WebSocket connection, and sign-in remains required before reading study records.

Vercel configuration limits functions to 300 seconds. WebSocket reconnections/function recycling can interrupt a browser session and reset the focus timer or sign-in state; durable study records stay in PostgreSQL. Test actual hosted interaction before relying on long study timers. Hosted document uploads are capped at 3 MB to leave room for request overhead. Local uploads remain limited to 10 MB.

The workspace link alone grants no deployment access. Browser authorization must finish before the CLI can provision services or publish. A successful local ASGI check does not prove a Vercel deployment is live.

References: [Streamlit ASGI release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2026), [Vercel Python entrypoints](https://vercel.com/docs/functions/runtimes/python), [Vercel WebSockets](https://vercel.com/changelog/websocket-support-is-now-in-public-beta).

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q planner app.py python.py
python -m pip check
python scripts/smoke_server.py
python scripts/smoke_asgi.py
```

If PostgreSQL server tools (`initdb` and `pg_ctl`) are installed, `python scripts/check_postgres.py` runs the storage tests against a disposable local PostgreSQL cluster. It never uses an existing hosted database.

Tests use temporary databases and mocked AI responses; they do not read your saved study data or spend API quota. Coverage includes input errors, mark normalization, integer allocation, prerequisite ordering, exam boundaries, randomized capacity checks, partial/skipped replanning, persistence, pace updates, review intervals, PDF extraction, source validation, exports, and Streamlit interactions.

GitHub Actions runs the checks on Python 3.12 and 3.14. A successful local run does not establish that a GitHub Actions run or live Gemini request succeeded.

## Console example

For marks **8, 7, 9 out of 10** and **six hours**:

```text
Deep Learning: 2h 00m (2.00 hours)
Data Mining: 3h 00m (3.00 hours)
Python: 1h 00m (1.00 hours)

Focus more on: Data Mining
```

The console validates input, handles tied weak subjects and full marks, and distributes exact integer-minute totals. A small maintenance weight keeps full-mark subjects in revision when others are weaker.

## Project structure

```text
app.py                    Streamlit dashboard
server.py                 ASGI entrypoint and deployment health check
python.py                 Validated console edition
planner/
  validation.py           Input validation and proportional allocation
  clock.py                Configured local timezone
  models.py               Task, slot, session, and plan records
  scheduler.py            Priorities, constraints, and greedy scheduling
  storage.py              Transactional SQLite persistence and replanning
  database.py             PostgreSQL adapter for durable hosted storage
  access.py               Hosted configuration and workspace access
  accounts.py             Registration, password hashing, sessions, and throttling
  reviews.py              Adaptive SM-2 based review intervals
  materials.py            PDF extraction and local source retrieval
  ai.py                   Optional Gemini generation and citation checks
  exports.py              CSV and RFC 5545 calendar exports
tests/                    Core and dashboard interaction tests
.github/workflows/        Continuous integration
PROJECT_ANALYSIS.md       Initial research and eight-project comparison
```

## Current limits and next steps

- The scheduler is greedy; it can leave work unscheduled even when a more sophisticated arrangement exists. CP-SAT optimization is a future improvement.
- Multiple recurring free-time windows per weekday are supported. Windows must not overlap and must finish before midnight. Delete rows or set minutes to zero for weekdays without study time; days off override all windows on that date.
- A planning pass reserves the next review for each card. After rating a card, regenerate to include its next due review.
- The focus timer lasts only for the browser session. Its elapsed time does not automatically mark work complete.
- PDF import supports selectable text, up to 10 MB locally or 3 MB when hosted, and 100 pages, with per-page complexity/text limits. Scans need external OCR.
- The application has no push notifications or trained grade prediction. Accounts have no email verification or automated password recovery yet.
- AI requests are implemented and tested with mocks; live responses require a configured provider key.

See [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) for the original comparison and [CHANGELOG.md](CHANGELOG.md) for the implemented upgrade.
