import unittest
from datetime import date, datetime

from planner.availability import WEEKDAYS, validate_windows, weekly_slots


class AvailabilityTests(unittest.TestCase):
    def test_existing_seven_day_settings_keep_their_schedule(self):
        rows = [{"day": day, "start": "18:00", "minutes": 120} for day in WEEKDAYS]
        slots = weekly_slots(date(2026, 11, 2), 14, rows, [])
        self.assertEqual(len(slots), 14)
        self.assertTrue(all(s.start.hour == 18 and s.end.hour == 20 for s in slots))

    def test_split_windows_repeat_in_order_and_respect_days_off(self):
        rows = [{"day": "Monday", "start": "18:00", "minutes": 60},
                {"day": "Monday", "start": "08:00", "minutes": 30},
                {"day": "Tuesday", "start": "12:00", "minutes": 0}]
        slots = weekly_slots(date(2026, 11, 2), 21, rows, [date(2026, 11, 9)])
        self.assertEqual([s.start for s in slots], [datetime(2026, 11, 2, 8), datetime(2026, 11, 2, 18),
                                                   datetime(2026, 11, 16, 8), datetime(2026, 11, 16, 18)])
        self.assertEqual([int((s.end - s.start).total_seconds() / 60) for s in slots], [30, 60, 30, 60])

    def test_overlaps_are_rejected_even_outside_the_planning_horizon(self):
        for start in ["08:00", "08:30", "07:30"]:
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "overlap on Monday"):
                weekly_slots(date(2026, 11, 3), 1, [
                    {"day": "Monday", "start": "08:00", "minutes": 60},
                    {"day": "Monday", "start": start, "minutes": 60}], [])

    def test_adjacent_windows_and_different_weekdays_are_allowed(self):
        rows = [{"day": "Monday", "start": "08:00", "minutes": 60},
                {"day": "Monday", "start": "09:00", "minutes": 60},
                {"day": "Tuesday", "start": "08:00", "minutes": 60}]
        self.assertEqual(validate_windows(rows), rows)

    def test_invalid_rows_have_actionable_errors(self):
        for change, message in [({"day": None}, "Choose a weekday"),
                                ({"day": "Mon"}, "Choose a weekday"),
                                ({"start": None}, "valid start time"),
                                ({"start": "25:00"}, "valid start time"),
                                ({"start": "08:00:30"}, "valid start time"),
                                ({"minutes": None}, "Free minutes"),
                                ({"minutes": float("nan")}, "Free minutes"),
                                ({"minutes": -1}, "Free minutes"),
                                ({"minutes": 30.5}, "whole number"),
                                ({"minutes": 721}, "at most 720"),
                                ({"start": "23:30", "minutes": 30}, "before midnight")]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                validate_windows([{"day": "Monday", "start": "08:00", "minutes": 60} | change])

    def test_all_windows_can_be_deleted(self):
        self.assertEqual(weekly_slots(date(2026, 11, 2), 7, [], []), [])


if __name__ == "__main__":
    unittest.main()
