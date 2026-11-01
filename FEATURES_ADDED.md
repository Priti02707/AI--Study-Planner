# What we added to AI Study Planner

The original project was a console script that distributed daily study hours using subject marks. It now includes the following capabilities.

| Area | Added capability | How it helps |
| --- | --- | --- |
| Dashboard | Today, Subjects, Weekly plan, Practice, Notes & AI, and Progress pages | Manage the full study workflow in a browser. |
| Subjects and topics | Exam dates/times, normalized marks, target goals, topic difficulty, estimated work, and prerequisites | Turn broad subjects into actionable work. |
| Scheduling | Multiple free windows per weekday, days off, configurable breaks/session lengths, priorities, and explanations | Build a timetable that fits real availability. |
| Adaptive planning | Completed/partial/skipped work, recent quiz feedback, duration adaptation, and replanning | Adjust future work while retaining completed history. |
| Revision | Recall cards and SM-2 based review intervals | Keep a queue of material to revisit. |
| Practice | Manual quiz logging and a mistake notebook | Track weaknesses at topic level. |
| Notes | PDF/text import, page viewing, and local passage search | Keep relevant material connected to study topics. |
| Optional AI | Syllabus-to-topic suggestions, source-based multiple-choice quizzes, and answers from notes | Assist preparation when a Gemini API key is configured. |
| Progress | Active-time charts, completed-work indicators, quiz history, and a focus timer | See activity and study progress over time. |
| Exports | CSV timetable, calendar `.ics`, and JSON data export | Take plans and records outside the app. |
| Storage | SQLite locally and Neon PostgreSQL in production | Keep study records between visits and server restarts. |
| Accounts and hosting | Registration, username/password sign-in, sign-out, password changes, isolated study data, and a working Vercel deployment | Each student can keep a private planner online. |
| Reliability | Input validation, duplicate detection, full-mark handling, exact minute allocation, tests, and CI configuration | Prevent the failures present in the original script. |
| Performance | Connection reuse, one-time schema setup, per-render read reuse, atomic sample import, deferred backups, and aligned hosting region | Make navigation and data loading faster. |

AI features are optional and are currently disabled in production until a Gemini API key is configured. The scheduling algorithm remains an explainable heuristic. Each registered account has its own data; the original workspace remains accessible with its existing owner password. Email verification, password recovery, notification reminders, and trained grade prediction are not included.

See [README.md](README.md) for usage and [PERFORMANCE.md](PERFORMANCE.md) for measured speed improvements.
