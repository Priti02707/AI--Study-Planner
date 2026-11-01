"""SM-2 based intervals. Same-day relearning is handled as a one-day retry.

This intentionally uses the next-day queue rather than claiming to implement
SuperMemo's entire same-day repetition procedure.
"""

import math
from datetime import timedelta

from planner.validation import integer


def next_review(rating, repetitions, interval, ease, reviewed_at):
    rating = integer(rating, "Recall rating", 0, 5)
    if rating < 3:
        repetitions, interval = 0, 1
    else:
        interval = 1 if repetitions == 0 else 6 if repetitions == 1 else math.ceil(interval * ease)
        repetitions += 1
    ease = max(1.3, ease + 0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02))
    return repetitions, interval, ease, reviewed_at + timedelta(days=interval)
