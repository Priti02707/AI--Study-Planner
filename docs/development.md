# Development

[Project home](../README.md) · [Deployment](../DEPLOYMENT.md)

## Checks

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

## Source layout

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
  coach.py                Setup, recall checks, and practice recommendations
  coach_ui.py             Study coach page and plan preview
  availability.py         Recurring study-window validation
  reviews.py              Adaptive SM-2 based review intervals
  materials.py            PDF extraction and local source retrieval
  ai.py                   Optional Gemini generation and citation checks
  exports.py              CSV and RFC 5545 calendar exports
tests/                    Core and dashboard interaction tests
.github/workflows/        Continuous integration
docs/                     User guide, algorithms, and development notes
PROJECT_ANALYSIS.md       Initial research and eight-project comparison
```

## Working on the project

Follow the local setup in the README. Keep planning logic in `planner/`, interface changes in the dashboard modules, and verification helpers in `scripts/`. Use temporary databases for tests; do not use production records or spend provider quota for routine checks.

Keep Streamlit pinned while using its experimental ASGI interface. After a dependency change, run the HTTP and WebSocket smoke checks and regenerate browser assets before deployment. Live verification and QA account creation are documented separately in the deployment guide.

Feature history is in [CHANGELOG.md](../CHANGELOG.md). Original research and comparisons are in [PROJECT_ANALYSIS.md](../PROJECT_ANALYSIS.md); that report describes the earlier console prototype, not the current feature set.
