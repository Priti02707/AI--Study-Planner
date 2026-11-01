"""Validation shared by the console, dashboard, and persistence layer."""

import math


def number(value, label, minimum=0, maximum=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.") from None
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{label} must be finite and at least {minimum}.")
    if maximum is not None and result > maximum:
        raise ValueError(f"{label} must be at most {maximum}.")
    return result


def integer(value, label, minimum=0, maximum=None):
    result = number(value, label, minimum, maximum)
    if not result.is_integer():
        raise ValueError(f"{label} must be a whole number.")
    return int(result)


def text(value, label, limit=200):
    result = value.strip() if isinstance(value, str) else ""
    if not result or len(result) > limit:
        raise ValueError(f"{label} must contain 1–{limit} characters.")
    return result


def score(earned, maximum):
    maximum = number(maximum, "Maximum marks", 0.000001)
    return number(earned, "Marks", 0, maximum) / maximum


def allocate_minutes(subjects, daily_minutes):
    """Normalized proportional allocation, with exact integer-minute totals.

    Subjects are (name, earned, maximum). A small maintenance weight keeps
    perfect-scoring subjects in revision; all-perfect scores split equally.
    """
    daily_minutes = integer(daily_minutes, "Daily minutes", 0, 1440)
    if not subjects:
        raise ValueError("Add at least one subject.")
    names, weights = [], []
    for name, earned, maximum in subjects:
        name = text(name, "Subject name")
        if name.casefold() in {n.casefold() for n in names}:
            raise ValueError("Subject names must be unique.")
        names.append(name)
        weights.append(max(0.05, 1 - score(earned, maximum)))
    quotas = [daily_minutes * w / sum(weights) for w in weights]
    minutes = [math.floor(q) for q in quotas]
    order = sorted(range(len(quotas)), key=lambda i: quotas[i] - minutes[i], reverse=True)
    for i in order[: daily_minutes - sum(minutes)]:
        minutes[i] += 1
    return dict(zip(names, minutes))
