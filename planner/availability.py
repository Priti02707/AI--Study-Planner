"""Validate recurring study windows and expand them into dated free slots."""

import re
from datetime import datetime, time, timedelta

from planner.models import Slot
from planner.validation import integer

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def validate_windows(rows):
    """Keep the saved row format compatible with the original seven-row editor."""
    result = []
    intervals = {day: [] for day in WEEKDAYS}
    for row in rows:
        day = row.get("day")
        if day not in WEEKDAYS:
            raise ValueError("Choose a weekday for every study window.")
        start = row.get("start")
        if not isinstance(start, str) or not re.fullmatch(r"\d{2}:\d{2}", start):
            raise ValueError("Use a valid start time such as 18:00.")
        try:
            begin = time.fromisoformat(start)
        except ValueError:
            raise ValueError("Use a valid start time such as 18:00.") from None
        minutes = integer(row.get("minutes"), "Free minutes", 0, 720)
        first = begin.hour * 60 + begin.minute
        end = first + minutes
        if minutes:
            if end >= 1440:
                raise ValueError("Free study windows must finish before midnight. Shorten the window or start earlier.")
            if any(first < right and end > left for left, right in intervals[day]):
                raise ValueError(f"Study windows overlap on {day}. Adjust their start times or lengths.")
            intervals[day].append((first, end))
        result.append({"day": day, "start": start, "minutes": minutes})
    return result


def weekly_slots(start, days, availability, days_off):
    rows = validate_windows(availability)
    result = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day in days_off:
            continue
        for row in rows:
            if row["day"] == WEEKDAYS[day.weekday()] and row["minutes"]:
                begin = datetime.combine(day, time.fromisoformat(row["start"]))
                result.append(Slot(begin, begin + timedelta(minutes=row["minutes"])))
    return sorted(result, key=lambda slot: slot.start)
