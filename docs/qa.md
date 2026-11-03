# QA workspace

Install `requirements.txt` in a Python 3.12–3.14 virtual environment. From the repository root, run:

```bash
python -m unittest discover -s tests -v
python -m scripts.qa_workspace
```

Open the localhost URL printed by Streamlit. Sign in with the randomly generated `qa_student` credentials printed in your terminal. Use `qa_isolation` in a separate browser profile to check isolation. The launcher uses temporary SQLite storage and removes it on normal exit. It ignores hosted database settings and listens on loopback. Use only synthetic notes, particularly when Gemini is configured.

| Area | Checks and expected results |
| --- | --- |
| Accounts | Register a third user. Reject duplicate names (including case variations), mismatched passwords and invalid credentials. Verify sign-out and password change, including revocation in a second session. Verify the isolation user cannot see the primary user's subjects, notes, or exports. |
| Today and subjects | Load sample subjects. Create, edit and remove a disposable subject, exam and topic. Validate scores, estimates and prerequisite rules. Record completed, partial and skipped outcomes on separate sessions and confirm that recorded history survives replanning. |
| Study coach | Enter goals, syllabus and availability. Save a self-rated recall check, preview without persisting sessions, invalidate the preview by changing inputs, then accept a fresh preview. |
| Weekly plan | Use multiple windows, breaks, a day off, prerequisites and a near exam deadline. Force excess workload. Check no overlap, unscheduled minutes, session explanations and preservation of finished work. Compare CSV and calendar downloads with the displayed plan. |
| Practice | Record weak and strong assessments, log and review a mistake, create a flashcard and rate its review. Check the next review date and whether the latest score influences future sessions. |
| Notes | Import selectable PDF and text, search for a known passage and try an unrelated query. Exercise invalid and oversized files and a scanned PDF. |
| Gemini | With a test API key, review and confirm drafted topics, generate and take a source-based quiz, and ask a question against the notes. Check citation grounding and failure behavior with an invalid key. Repeat with the key unset to verify offline workflows. |
| Progress | Start and stop the focus timer, check progress after recording study, and inspect the JSON export for records and absence of auth data. |
| Hosting | Separately run the documented hosted check with `--coach` against an approved environment. Verify WebSocket reconnect behavior and repeat provider-dependent cases there. The local launcher only exercises SQLite. |
| Console | Run `python python.py` and check the minutes allocated from sample subject marks. |

Record each case as passed, failed, or blocked. Include the commit, environment, exact steps, and observed result for failures.
