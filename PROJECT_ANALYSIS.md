# AI Study Planner: analysis and development recommendations

Reviewed: 1 November 2026.

Implementation note: this report describes the original console prototype and the research that guided its upgrade. Many recommendations are now implemented; see [README.md](README.md) and [CHANGELOG.md](CHANGELOG.md) for current behavior and remaining limits.

## Recommendation

Develop this into an **explainable, adaptive revision planner**: use exam deadlines and topic-level quiz results to generate realistic sessions, then revise future sessions when the student struggles or misses a day.

The existing script is a useful starting point for proportional time allocation. The next major improvement is a persistent planning and feedback loop. A chatbot can come later.

## Scope and evidence

I read the local `python.py` and `README.md` and ran seven input scenarios using Python 3.14.7. I compared eight public GitHub repositories using their published README documentation and repository pages. I did not install or execute those external projects, audit all their implementations, or verify their claimed learning outcomes. The comparison describes documented capabilities, not independently measured quality. This is a selected comparison, not an exhaustive GitHub survey.

## 1. What your project currently does

The program stores subject names and marks in a dictionary, asks for a daily study budget, and computes:

```text
subject_weight = 10 - marks
subject_hours = daily_hours × subject_weight / sum(subject_weights)
```

It then identifies the subject with the lowest mark.

Strengths:

- Small, understandable Python implementation with no third-party dependencies.
- Transparent allocation formula that is easy to explain in a project demonstration.
- Correctly directs more time to lower-scoring subjects when scores are within the assumed 0–10 scale and the denominator is positive.

Current boundaries:

- It allocates hours by subject; it does not create dated or timed timetable entries.
- It is a rule-based program. There is no trained model, LLM integration, or learning from historical performance.
- It has no saved state, topic breakdown, deadline handling, review schedule, or completion tracking.

Describe the current version as a rule-based study planner in the README. If keeping the AI title, explain exactly which parts are currently heuristic and which AI additions are planned.

## 2. Confirmed issues to fix first

| Case tested | Observed behavior | Recommended correction |
| --- | --- | --- |
| README example: scores 8, 7, 9; six hours | Actual output: 2.0, 3.0, 1.0 hours. README shows 2.0, 2.4, 1.6. | Update the example to match the implemented formula. |
| Every subject scores 10 | `ZeroDivisionError` at `python.py:17`. | Handle zero total weakness explicitly; use equal maintenance time or let the student select another objective. |
| Zero subjects | `ValueError` at `python.py:21`. | Require at least one subject before planning. |
| Scores 80 and 60; four hours | Higher-scoring subject receives 2.33 hours and weaker subject 1.67. | Ask for maximum marks and normalize; reject scores outside the selected scale. |
| Same subject entered twice | Later mark silently replaces the earlier entry at `python.py:8`. | Detect duplicate names after trimming and case normalization; explicitly update or reject. |
| Negative daily hours | Prints negative allocated study time. | Reject negative and non-finite hours; define zero hours as a day off or request positive hours. |
| Subject count entered as `two` | Unhandled `ValueError`. | Validate input and provide a retry prompt. |

Additional inspection findings: a subject with full marks gets zero maintenance revision when others are weaker; equally weak subjects are reduced to a single displayed recommendation; independent rounding can make displayed allocations differ from the requested total. Marks such as NaN/infinity also need explicit rejection.

Use integer minutes for allocations and session lengths. When proportional allocation needs exact totals, floor each minute quota and distribute leftover minutes to the largest fractional remainders.

## 3. Comparison with eight GitHub projects

The following features are documented by the linked repositories. Each row includes the idea most relevant to your current stage.

| Project | Documented capabilities | What to learn from it |
| --- | --- | --- |
| [SpacedRepetitionStudyPlanner](https://github.com/TheoUgwuja/SpacedRepetitionStudyPlanner) | Python/Tkinter calendar, fixed review days, JSON save/load. | A small Python project can add a calendar and persistence without a large backend. |
| [Study Revision Planner](https://github.com/Cletrix-Labs/study-revision-planner) | Flask app, topic difficulty, exam dates, revision sessions, completion records, CSV export. | Move from subject hour totals to dated topic sessions and track completion. |
| [SmartStudy](https://github.com/PseudoOzone/SmartStudy-AI-Planner) | Streamlit dashboard, exam/confidence inputs, workload heuristics, confidence history, what-if analysis. Explicitly identifies its logic as rule-based. | Make priority transparent and add a dashboard. Keep heuristic scores distinct from validated predictions. |
| [dguywhoknows/study-planner](https://github.com/dguywhoknows/study-planner) | Topic breakdown, capacity-aware scheduling, interleaving, spaced reviews, missed-session replanning, calendar export. | Respect available capacity and keep completed work when regenerating the plan. |
| [AdaptiStudy](https://github.com/prushti21/AdaptiStudy) | Mobile app, weighted historical duration estimates, focus timer, PDF quizzes, mistake review, progress rewards. | Learn realistic task duration from completed sessions and keep a mistake notebook. |
| [StudyIndex](https://github.com/ethanhunt1011/studyindex) | Document-to-topic extraction, SM-2 flashcards, document-grounded chat, practice exams. | Connect uploaded material, retrieval practice, and review scheduling. |
| [AI Study Plan Recommender](https://github.com/Lezo-Jong/ai-study-plan-recommender) | Gemini-generated plans, progress feedback loop, planner/reviewer/evaluation architecture. | Evaluate plan quality explicitly; separate generation from validation. |
| [EduAgent Pro](https://github.com/JMadhan1/eduagent) | PDF retrieval, adaptive quizzes, notes, tutor chat, exam simulation, analytics. | Integrate practice results with planning after the core scheduler is reliable. |

Your main gap is the absence of dates, saved progress, and feedback. Build those before attempting the entire feature set of the larger projects.

## 4. Recommended techniques

### A. Explainable priority scoring — first algorithm upgrade

Replace the fixed `10 - marks` score with normalized signals for each topic:

```text
weakness = 1 - earned_marks / maximum_marks
urgency = 1 / max(days_until_exam, 1)
workload = remaining_estimated_minutes / max(available_minutes_before_exam, 1)
workload_pressure = min(workload, 1)
review_due = 1 if a review is due, otherwise 0

priority = 0.40 × weakness
         + 0.30 × urgency
         + 0.20 × workload_pressure
         + 0.10 × review_due
```

These are proposed starting weights, not a validated learning model. Tune them with example schedules and user feedback. The reciprocal urgency term rises sharply near the deadline; inspect that behavior before adopting it. Keep the uncapped workload ratio for shortage detection even though the score caps its contribution. Validate dates separately: past exams must be archived or corrected, and an exam today permits only time slots before its start.

Show an explanation such as: “Higher priority because your latest quiz score was 40% and the exam is in three days.” Reserve maintenance reviews or minimum coverage so stronger topics are not permanently excluded. Use subject marks initially; move to recent topic-level quiz results when available.

### B. Capacity-aware scheduling — highest practical value

Start with a greedy scheduler:

1. Collect free time slots for each day, exam dates, topic workload, and prerequisite order.
2. Generate study and review tasks with estimated minutes.
3. Rank eligible tasks by priority, recomputing as the date and remaining workload change.
4. Fill available slots using configurable session durations, accounting for breaks and switching subjects when practical.
5. Prevent overlap, sessions after an exam, and learning a dependent topic before its prerequisite.
6. Report unscheduled work and an hour shortfall when capacity is insufficient.

For example, if the remaining work requires ten hours but only six are available, show a four-hour shortfall and let the student adjust scope or availability.

As constraints become more complex, consider a CP-SAT scheduling model with [Google OR-Tools](https://developers.google.com/optimization/scheduling). That is a later optimization step; a transparent greedy approach is easier to build and debug now.

### C. Spaced repetition with active recall

Add flashcards or short topic quizzes and record review outcomes. Begin with configurable fixed intervals, for example 1, 3, and 7 days, while respecting exam deadlines and available capacity. These example intervals are a product starting point, not a claim of optimal timing for every learner.

For adaptive card review, evaluate [Py-FSRS](https://github.com/open-spaced-repetition/py-fsrs). It supports card state, review logs, and Again/Hard/Good/Easy ratings to calculate subsequent due dates. Persist that state and feed due reviews into your daily scheduler. A review algorithm supplies due dates; your planner still has to resolve time conflicts and review backlogs. Start with its default model; personalized parameter optimization is a later step requiring review history.

### D. Feedback-driven replanning

Store session status as planned, completed, skipped, or partial. When regenerating a plan, preserve completed history, carry only remaining work forward, and recompute future priorities. A missed day must not create an impossible workload tomorrow.

For comparable tasks, update duration estimates with an exponential moving average:

```text
updated_estimate = 0.7 × previous_estimate + 0.3 × latest_completed_duration
```

This is a proposed smoothing heuristic, similar to the historical weighting documented by [AdaptiStudy](https://github.com/prushti21/AdaptiStudy). Use active work time and comparable task sizes; exclude breaks, abandoned tasks, and timer accidents. Provide an initial estimate before history exists.

### E. Document-grounded AI — later feature

Allow a syllabus PDF to produce an editable subject/chapter/topic hierarchy. Require structured output and student confirmation of extracted topics. Generate short practice questions tied to source pages and send quiz outcomes back to the planner.

For a tutor feature, retrieval-augmented generation can supply relevant uploaded passages and page references to the model. Ask the system to acknowledge when the source lacks the answer. Retrieval does not guarantee correctness; evaluate factual support and quiz answer quality. Keep API keys on the server and retain manual topic entry when AI is unavailable.

## 5. Feature order

| Order | Deliverable | Why it belongs here | Relative effort |
| --- | --- | --- | --- |
| 1 | Input validation, score normalization, zero-denominator handling, corrected README | Makes the existing behavior dependable. | Small |
| 2 | Functions/modules and saved subjects, topics, exams, and sessions | Enables future features without losing work on exit. | Small–medium |
| 3 | Dashboard showing today's tasks, available time, next exam, completion, and priority reasons | Gives students an actionable daily view. | Medium |
| 4 | Weekly planner with exam dates, free slots, breaks, and shortage alerts | Produces a usable timetable. | Medium |
| 5 | Topic quizzes, spaced review, and mistake notebook | Adds a feedback signal beyond old subject marks. | Medium |
| 6 | Missed-session replanning and duration adaptation | Lets the plan respond to actual behavior. | Medium |
| 7 | CSV and calendar-file export; optional focus timer | Makes the plan easier to use outside the app. | Small–medium |
| 8 | PDF topic extraction and grounded quiz generation | Adds AI around a working scheduling system. | Large |

Optional later additions: Hindi/English interface, printable weekly plans, offline operation, and a what-if tool that compares two daily study budgets. These are useful product directions, not claims of novelty across GitHub.

## 6. Suggested implementation structure

Keep Python for the next version. My suggested first interface is [Streamlit](https://docs.streamlit.io/get-started/fundamentals/main-concepts), which supports building a browser interface with Python widgets, tables, and charts. Use SQLite for persistent local data. A custom frontend and API can wait until you need more control over layout or multi-user deployment.

```text
app.py                 # proposed dashboard entry point
planner/
    models.py          # subject, topic, exam, session, assessment
    validation.py      # input rules and score normalization
    scheduler.py       # priority, allocation, dated sessions, replanning
    reviews.py         # fixed-interval or FSRS review integration
    storage.py         # SQLite reads and writes
tests/
    test_scheduler.py
    test_validation.py
data/                  # local database; exclude personal data from Git
requirements.txt
README.md
```

Suggested records:

- Subject: stable ID, name, maximum mark.
- Topic: subject ID, name, difficulty, estimated remaining minutes, prerequisites.
- Exam: subject ID, date/time, target score.
- Session: topic ID, scheduled start/end, status, planned and actual active minutes.
- Assessment: topic ID, earned marks, maximum marks, timestamp.
- Review: card/topic ID, rating, review timestamp, next due date, algorithm state.

Separate pure planning functions from console/browser input and database operations. Importing the scheduler should not prompt for input. Streamlit reruns scripts on interaction, so persist records deliberately and avoid duplicate session creation on reruns; session state alone is not durable storage.

## 7. How to evaluate the next version

Compare three planners using the same subjects, dates, and availability: equal time, the current marks-only formula, and the proposed adaptive scheduler.

Check engineering properties first:

- No crashes on empty/invalid input or full marks.
- No negative allocations, overlapping sessions, or capacity violations.
- Score normalization gives equivalent priorities for 8/10 and 80/100.
- Completed sessions survive regeneration and application restart.
- Daily minute totals fit availability, with breaks accounted for.
- Infeasible deadlines produce explicit unscheduled-work warnings.
- Topic prerequisites and exam boundaries hold.

Then measure practical outcomes: percentage of sessions completed, topics covered before the exam, overdue review load, and error between estimated and actual study time. Quiz trends can inform future improvements, but more time logged or a higher heuristic readiness score does not prove improved learning. Demonstrating academic benefit requires evaluation with learners and a suitable comparison.

## Suggested project demonstration

Show a student with three subjects and different exam dates. Generate a feasible weekly plan. Record a weak quiz result on one topic, mark another session missed, and regenerate. Demonstrate that the affected topic rises in priority, finished sessions remain intact, and available hours are still respected. Explain each changed recommendation.

This demonstrates a concrete improvement over the current script: the plan responds to evidence and real constraints.
