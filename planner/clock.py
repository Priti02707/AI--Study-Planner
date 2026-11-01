"""All stored datetimes are local wall times in one configured timezone."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo


def timezone_name():
    return os.environ.get("STUDY_PLANNER_TIMEZONE", "Asia/Kolkata")


def now():
    return datetime.now(ZoneInfo(timezone_name())).replace(tzinfo=None, microsecond=0)
