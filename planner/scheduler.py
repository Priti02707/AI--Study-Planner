"""Deterministic capacity-aware greedy scheduler with explainable priorities."""

from datetime import datetime, timedelta

from planner.models import Plan, PlannedSession, Slot, Task
from planner.validation import integer


def merge_slots(slots):
    merged = []
    for slot in sorted(slots, key=lambda s: s.start):
        if slot.end <= slot.start:
            raise ValueError("Each free slot must end after it starts.")
        if merged and slot.start <= merged[-1].end:
            merged[-1] = Slot(merged[-1].start, max(slot.end, merged[-1].end))
        else:
            merged.append(slot)
    return merged


def subtract_busy(slots, busy):
    """Preserved completed/partial/skipped session intervals cannot be reused."""
    result = merge_slots(slots)
    for block in merge_slots(busy):
        pieces = []
        for slot in result:
            if block.end <= slot.start or block.start >= slot.end:
                pieces.append(slot)
            else:
                if slot.start < block.start:
                    pieces.append(Slot(slot.start, block.start))
                if block.end < slot.end:
                    pieces.append(Slot(block.end, slot.end))
        result = pieces
    return result


def priority(task, at, remaining, capacity):
    days = max((task.deadline - at).total_seconds() / 86400, 1)
    weakness = 1 - task.mastery
    pressure = min(remaining / max(capacity, 1), 1)
    # Difficulty is bounded 1–5. These are transparent heuristics, not predictions.
    value = 0.4 * weakness + 0.3 / days + 0.2 * pressure + 0.05 * task.difficulty / 5
    value += 0.05 if task.kind == "review" else 0
    reason = (
        f"Quiz/marks {task.mastery:.0%}; exam in {days:.1f} days; "
        f"{remaining} min left; difficulty {task.difficulty}/5"
    )
    if task.kind == "review":
        reason += "; recall review due"
    return value, reason


def schedule(tasks, slots, session_minutes=25, break_minutes=5):
    session_minutes = integer(session_minutes, "Session length", 5, 180)
    break_minutes = integer(break_minutes, "Break length", 0, 60)
    tasks = list(tasks)
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("Task IDs must be unique.")
    for task in tasks:
        integer(task.minutes, "Task minutes", 1)
        if not 0 <= task.mastery <= 1 or not 1 <= task.difficulty <= 5:
            raise ValueError("Task mastery or difficulty is outside its range.")
    slots = merge_slots(slots)
    remaining = {t.id: t.minutes for t in tasks}
    known = set(remaining)
    for task in tasks:
        if task.prerequisite and task.prerequisite not in known:
            raise ValueError("A prerequisite is missing from the plan.")
    completed_at = {}
    plan = Plan()
    previous_subject = None
    ready_at = slots[0].start if slots else datetime.min
    for slot in slots:
        cursor = max(slot.start, ready_at)
        while cursor < slot.end:
            eligible = [
                t for t in tasks
                if remaining[t.id] > 0 and t.available_from <= cursor < t.deadline
                and (not t.prerequisite or (
                    remaining[t.prerequisite] == 0
                    and completed_at[t.prerequisite] <= cursor
                ))
                and min((slot.end - cursor).total_seconds(),
                        (t.deadline - cursor).total_seconds()) >= 60
            ]
            if not eligible:
                future = [t.available_from for t in tasks
                          if remaining[t.id] > 0 and cursor < t.available_from < slot.end]
                if future:
                    cursor = min(future)
                    continue
                break
            def rank(task):
                capacity = sum(max(0, (min(s.end, task.deadline) - max(s.start, cursor)).total_seconds() / 60)
                               for s in slots if s.end > cursor and s.start < task.deadline)
                value, _ = priority(task, cursor, remaining[task.id], capacity)
                # Mild interleaving preference without overriding large urgency differences.
                return value - (0.03 if task.subject == previous_subject else 0)
            task = max(eligible, key=lambda t: (rank(t), -t.deadline.toordinal(), t.id))
            duration = min(session_minutes, remaining[task.id],
                           int((min(slot.end, task.deadline) - cursor).total_seconds() // 60))
            end = cursor + timedelta(minutes=duration)
            value, reason = priority(task, cursor, remaining[task.id],
                                     sum(max(0, (min(s.end, task.deadline) - max(s.start, cursor)).total_seconds() / 60)
                                         for s in slots))
            plan.sessions.append(PlannedSession(task, cursor, end, value, reason))
            remaining[task.id] -= duration
            if remaining[task.id] == 0:
                completed_at[task.id] = end
            previous_subject = task.subject
            cursor = end + timedelta(minutes=break_minutes)
            ready_at = cursor
    plan.unscheduled = {key: value for key, value in remaining.items() if value}
    return plan
