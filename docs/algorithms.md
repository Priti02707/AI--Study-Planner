# Algorithms and planning rules

[Project home](../README.md) · [User guide](guide.md)

## Scheduling

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

## Practice recommendations

The coach uses up to three recent topic assessments, weighted 3:2:1 from newest to oldest. Below 50% suggests Foundation, 50–79% Standard, and 80% or above Challenge. Subject marks are the fallback when no topic assessments exist. Self-rated recall checks count as assessments; these are not automatically graded tests.

This practice recommendation is separate from the scheduler's latest-score priority input. Optional Gemini quizzes receive the recommended level, recent mistake text, and source excerpts. The thresholds are heuristics, not calibrated estimates of mastery or exam results.

## Console example

For marks **8, 7, 9 out of 10** and **six hours**:

```text
Deep Learning: 2h 00m (2.00 hours)
Data Mining: 3h 00m (3.00 hours)
Python: 1h 00m (1.00 hours)

Focus more on: Data Mining
```

The console validates input, handles tied weak subjects and full marks, and distributes exact integer-minute totals. A small maintenance weight keeps full-mark subjects in revision when others are weaker.
