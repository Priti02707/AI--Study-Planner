# Performance fix — 1 November 2026

Production: https://ai-study-planner-lac.vercel.app

## Initial loading update

The public HTML and Streamlit browser assets now deploy as static files to Vercel's CDN. They no longer require the Singapore Python function to start. The HTML shows an opening message while JavaScript connects to the private workspace. Authentication and study records remain on the Python/WebSocket service.

Checks on 1 November 2026 after deployment `dpl_EbzSLcJXoA3QN89cYszhEMYe6RJq`:

| Request | First byte | Complete transfer |
| --- | ---: | ---: |
| Opening HTML | 0.49 s | 0.50 s |
| Repeat opening HTML | 1.34 s | 1.56 s |
| Main JavaScript, compressed | 0.59 s | 0.89 s |

The HTML returned `x-vercel-cache: HIT`. Both requests had a Mumbai edge-only Vercel request ID, without the previous `sin1` function hop. Versioned assets have a one-year immutable cache lifetime; HTML is revalidated. These timings measure HTTP transfers, not complete browser interactivity or visual paint.

Before this change, an opening request took 76.28 seconds, while a later warm request took 0.44 seconds. Separate connection probes also timed out before completing TCP connection. These variable samples include network effects and are not a controlled cold-start comparison; the CDN change cannot eliminate ISP/DNS or platform routing delays. Authenticated page renders were already fast and remained 0.17–0.66 seconds after the update. Free database wake-up and Python/WebSocket connection can still delay the interactive workspace.

All 80 local tests passed. Production HTTP/database health, private sign-in, and all six pages passed without changing study data. To reproduce deployment, run `python scripts/prepare_static.py` in the installed environment before the Vercel CLI command. It exports only the matching pinned framework assets into ignored `public/`; the deployment includes those files separately from the Python function.

Reference: [Vercel static-file delivery](https://vercel.com/kb/guide/ship-a-flask-app-on-vercel).

## Measured before and after

The same verification client connected to production, signed in, and navigated the six dashboard pages. Times measure the WebSocket request through Streamlit's successful script-finished message. They do not measure a browser's first asset download, visual paint, or arbitrary large datasets. No study records were changed during verification.

| Operation | Before | After |
| --- | ---: | ---: |
| Sign-in and Today render | 13.51 s | 0.70 s |
| Subjects | 11.16 s | 0.65 s |
| Weekly plan | 17.70 s | 0.21 s |
| Practice | 11.29 s | 0.26 s |
| Notes & AI | 8.97 s | 0.17 s |
| Progress | 14.91 s | 0.18 s |
| Today | 13.56 s | 0.47 s |

Mean page-navigation render time fell from 12.93 s to 0.32 s in this check, approximately a 97.5% reduction. These are observed measurements, not guaranteed response times. Initial cold starts, a sleeping free database, network latency, large documents, and AI calls can take longer.

## Causes and changes

- Store construction previously ran table/index creation on every Streamlit rerun. PostgreSQL setup now runs once per database/schema version per function process. Failed setup is not cached.
- Every query previously established a fresh PostgreSQL connection. A small checked connection pool now reuses connections, discards broken connections, and lets idle ones close.
- Identical reads within one page render previously repeated queries. A Store instance now caches those results, returns independent copies, and clears them before/after writes. New page renders create fresh Store instances, so this is not a long-lived shared-data cache.
- Nested operations now reuse their transaction connection. Replanning therefore does not wait for a second connection while holding a write lock; quiz changes are read afresh at the start of planning.
- Loading sample subjects now uses one atomic transaction instead of many separate connection/commit cycles. An interrupted import rolls back the whole batch.
- Progress previously generated the entire database backup while drawing the download button. Backup generation is now deferred until download is requested.
- The Vercel Function now runs in `sin1` (Singapore), matching the PostgreSQL database region.

## Validation

- 70 application tests passed.
- 25 PostgreSQL integration tests passed against a disposable cluster.
- Checks cover mutation-safe cached reads, cache invalidation after writes, new assessments from another Store, atomic sample-data import, schema reuse, persistence, and replanning.
- The dashboard test confirms opening Progress does not generate a backup.
- Production HTTP health, PostgreSQL connectivity, private sign-in, and all six page renders passed.
- Deployment: `dpl_3cDSrnNvtqowoQoxtXKLiMTBVBLs`.

To repeat the live measurement:

```bash
.venv/bin/python -u scripts/verify_deployment.py https://ai-study-planner-lac.vercel.app
```

Refresh an already-open browser tab after deployment to use the new function code.
