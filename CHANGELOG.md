# Changelog

## 2.1.0 — 2026-11-01

- Added an ASGI entrypoint using the pinned Streamlit version's experimental `st.App` interface, preserving the existing dashboard.
- Added Vercel entrypoint, duration limits, deployment exclusions, and an HTTP/database health route.
- Added PostgreSQL storage with transactional write coordination and consistent read snapshots; retained local SQLite.
- Added a hosted workspace password gate and configuration checks that prevent ephemeral database fallback.
- Added hosted upload limits, access tests, PostgreSQL integration checks, and a real ASGI WebSocket smoke test.
- Deployed to https://ai-study-planner-lac.vercel.app with Neon PostgreSQL on the free plan. Verified production health, private sign-in, WebSocket rendering, and all six dashboard pages.
- Used Vercel's file-based `api/index.py` entrypoint and disabled Streamlit telemetry for its read-only serverless filesystem.

## 2.0.0 — 2026-11-01

Expanded the original marks-only console script into a persistent study-planning application.

- Added a six-page Streamlit dashboard and SQLite storage.
- Added normalized marks, validated inputs, exact minute allocations, full-mark handling, duplicate detection, and tied weak-subject reporting.
- Added subjects, topics, exam dates/times, goals, difficulty, and cycle-checked prerequisites.
- Added explainable priority scoring and a capacity-aware weekly scheduler with breaks, days off, exam boundaries, preview, and workload shortfall reporting.
- Added completion/partial/skip tracking, history-preserving replanning, and smoothed duration adaptation.
- Added manual quiz feedback, adaptive review cards, progress charts, a focus timer, and a mistake notebook.
- Added PDF/text import, page-based local retrieval, optional Gemini topic extraction, source-based quizzes, and cited note answers.
- Added CSV, UTC calendar export, JSON data export, and private local-data exclusions.
- Added core, persistence, PDF/AI-validation, and dashboard interaction tests with GitHub Actions.
- Updated setup instructions, examples, algorithm explanations, and feature limitations.

The scheduling core remains deterministic and works without a provider key. No live AI credentials or user study records are included.
