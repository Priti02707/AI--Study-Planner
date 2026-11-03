# User guide

[Project home](../README.md) · [Deployment](../DEPLOYMENT.md) · [Algorithms](algorithms.md)

## Study workflow

Choose **Create account**, enter your name, a username, and a password of at least 12 characters. You will enter your own empty planner. Returning students use **Sign in**. Use **Sign out** or **Change password** in the sidebar. Usernames ignore case. At signup, write a security question, choose a private answer of at least 12 characters, and save the generated recovery code. Existing users can enroll under **Set up password recovery**. Choose **Reset password** at sign-in and supply the code and answer. Reset revokes all sessions and consumes the code. Set up a new code after signing back in.

### Guided setup

Open **Study coach**. Enter your first subject, current marks, exam goal, syllabus topics, estimated work, and daily availability. Try a **Knowledge check**, then **Preview my starting plan → Accept and save plan**. Existing students can open the coach directly for recommendations and replanning.

Knowledge checks ask you to explain a topic from memory, compare it with your notes or a saved card, and rate recall from 0–5. They are self-rated diagnostics, not automatically graded quizzes. A low rating with a correction of at least 20 characters creates a review card. The rating is saved as an assessment and influences future planning. Empty or very short explanations are rejected.

Practice recommendations suggest Foundation, Standard, or Challenge sets from recent results. See [practice recommendation rules](algorithms.md#practice-recommendations) for weighting and thresholds. Optional AI question sets use this suggested level and recent mistake text while retaining source evidence checks.

The coach previews seven days using saved windows, breaks, and days off. Previewing does not change sessions; accepting recalculates from current records and preserves finished history. Previews expire after five minutes or changes to planning inputs. No topic import or AI call is required for manual setup, self-checks, or recommendations.

### Manual setup and replanning

1. Open **Today** and choose **Load sample subjects**, or add your own in **Subjects**.
2. Enter current marks, maximum marks, target score, and exam date/time.
3. Break each subject into topics with estimated work, difficulty, and optional prerequisites.
4. In **Weekly plan**, enter your weekday availability, session length, breaks, and days off. Add a row for each free window (for example, Monday at 08:00 for 60 minutes and Monday at 18:00 for 90 minutes). Generate a timetable.
5. Record completed, partial, or skipped sessions in **Today**. Record quiz results in **Practice**, then regenerate your plan.

Replanning preserves completed work and redistributes unfinished work into future available time. Record any partial work before regenerating.

Weekdays can have multiple study windows. Windows must not overlap and must finish before midnight. Delete rows or set minutes to zero for weekdays without study time; days off override every window on that date.

Download CSV and `.ics` calendar exports from **Weekly plan**. Calendar exports include planned sessions; remove an older imported calendar before importing a regenerated plan to avoid stale events.

## Optional AI setup

Export environment variables **before** starting Streamlit:

```bash
export GROQ_API_KEY="your-key"
export GROQ_MODEL="llama-3.3-70b-versatile"
python -m streamlit run app.py
```

In PowerShell, use `$env:GROQ_API_KEY="your-key"` and `$env:GROQ_MODEL="llama-3.3-70b-versatile"`.

The model name is configurable because provider availability can change. [`.env.example`](../.env.example) documents the settings; `.env` files are **not** loaded automatically. Keys are read on the server and are never written to the database or repository.

- AI calls happen only when you press a generation/answer button.
- Selected note excerpts and your request are sent to Groq’s API. Adaptive quizzes also include up to three recent mistake prompts, which can include self-check explanations. This may use your provider quota.
- Topic generation uses up to the first 30 document excerpts; large documents may need splitting.
- Quiz generation and tutoring use local lexical retrieval to select relevant page excerpts. This is a lightweight retrieval-augmented workflow, without embeddings or a vector database.
- Responses use structured JSON. Source IDs and evidence excerpts are checked against the material supplied to the model. These checks do not prove that an answer is correct; inspect source pages and review AI topic suggestions before importing.
- If AI is unavailable, manual topic entry, quiz logging, cards, planning, and local search continue to work.

References: [Groq JSON Object Mode](https://console.groq.com/docs/structured-outputs), [Streamlit](https://docs.streamlit.io/get-started/fundamentals/main-concepts), [pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

## Saved data and timezone

SQLite stores the account registry in `data/study_planner.sqlite3` and each account's subjects, topics, exams, sessions, assessments, cards, review history, imported text, and availability in `data/workspaces/<account-id>.sqlite3`. The original local workspace remains in `data/study_planner.sqlite3`. Saved records survive process restarts.

Optional environment variables:

```bash
export STUDY_PLANNER_DB="data/study_planner.sqlite3"
export STUDY_PLANNER_TIMEZONE="Asia/Kolkata"
```

Dates are stored as wall times in the configured timezone. Calendar export converts them to UTC. Keep the same timezone for an existing database. If using a timezone with daylight-saving changes, check sessions around clock transitions manually; the scheduler does not resolve ambiguous or nonexistent local times.

Local mode binds to `127.0.0.1`. Hosted mode requires PostgreSQL. Accounts use separate PostgreSQL schemas with transaction-local search paths that exclude the original workspace. Locally, accounts use separate SQLite files. Registration creates a new empty workspace and cannot claim existing project data. The same subject names and topic IDs can exist independently in different accounts.

Passwords use individually salted PBKDF2-HMAC-SHA256 hashes with 600,000 iterations. Server-side sessions expire after 24 hours, are revoked by sign-out, and all of an account's sessions are revoked when its password changes. Five failed sign-ins for a username trigger a 15-minute lockout. Hosted student sign-in survives reloads while the browser retains its HttpOnly session cookie. Email verification, social sign-in, and administrator account management are unavailable.

To open pre-account project data, set `STUDY_PLANNER_PASSWORD` to a password of at least 12 characters before launching, then choose **Existing workspace**. On the deployed project, the existing password continues to work. This compatibility workspace is separate from registered accounts.

Use **Progress → Export all my data** for a readable JSON snapshot of your current account's study records; authentication records are excluded. For a full restorable local backup, stop the app and copy the entire `data/` directory (or the registry file and adjacent `workspaces/` directory at a custom database path). Restore while stopped. To import a JSON snapshot, open **Progress → Restore a backup** in an empty workspace. The hosted upload limit is 3 MB. Local data, virtual environments, generated browser assets, and secrets are excluded from Git.

Password hashing reference: [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

## Browser password manager

Sign-in and registration fields provide standard browser autofill hints. Chrome controls whether a Save password prompt appears; the app cannot force it. In Chrome, open **Google Password Manager → Settings** and enable **Offer to save passwords and passkeys**. You can also use **Google Password Manager → Passwords → Add** to save the app URL, your username, and your password manually.

## Current limitations

- The scheduler is greedy; it can leave work unscheduled even when a more sophisticated arrangement exists. CP-SAT optimization is a future improvement.
- A planning pass reserves the next review for each card. After rating a card, regenerate to include its next due review.
- The focus timer resumes from the saved start time. Its elapsed time does not automatically mark work complete.
- PDF import supports selectable text, up to 10 MB locally or 3 MB when hosted, and 100 pages, with per-page complexity/text limits. Scans need external OCR.
- The application has no push notifications or trained grade prediction. Account recovery uses a security answer and recovery code.
- AI requests are tested with mocks. Run `python -m scripts.verify_groq` with a test key to check live topic extraction, quiz generation, and cited tutoring against synthetic notes.

