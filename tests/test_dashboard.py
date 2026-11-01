"""Dashboard interaction tests, isolated from the user's data and AI accounts."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from planner.storage import Store
from planner.clock import now
from planner.availability import WEEKDAYS


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"ui.sqlite3"
        self.environment = patch.dict(os.environ, {"STUDY_PLANNER_DB":str(self.path), "GEMINI_API_KEY":""})
        self.environment.start()
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"), default_timeout=20).run()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def page(self, name):
        self.app.sidebar.radio[0].set_value(name).run()
        self.assertEqual(list(self.app.exception), [])

    def button(self, label):
        return next(b for b in self.app.button if b.label == label)

    def load_demo(self):
        self.button("Load sample subjects").click().run()
        self.assertEqual(list(self.app.exception), [])

    def test_empty_pages_are_usable(self):
        for page in ["Today", "Subjects", "Weekly plan", "Practice", "Notes & AI", "Progress"]:
            self.page(page)

    def test_demo_plan_and_all_pages(self):
        self.load_demo()
        self.assertEqual(len(Store(self.path).subjects()), 3)
        self.page("Weekly plan")
        self.button("Generate / replan").click().run()
        self.assertEqual(list(self.app.exception), [])
        count = len(Store(self.path).sessions())
        self.assertGreater(count, 0)
        self.button("Generate / replan").click().run()
        self.assertEqual(len(Store(self.path).sessions()), count)
        for page in ["Subjects", "Practice", "Notes & AI", "Progress", "Today"]:
            self.page(page)

    def test_create_subject_and_topic(self):
        self.page("Subjects")
        next(t for t in self.app.text_input if t.label == "Subject name").set_value("Databases")
        self.button("Save subject").click().run()
        self.assertEqual(list(self.app.exception), [])
        next(t for t in self.app.text_input if t.label == "Topic name").set_value("SQL joins")
        self.button("Save topic").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertEqual(Store(self.path).topics()[0]["name"], "SQL joins")

    def test_split_windows_preview_and_save(self):
        store = Store(self.path)
        tomorrow = now().date() + timedelta(days=1)
        subject = store.save_subject("Math", 5, 10, datetime.combine(tomorrow + timedelta(days=1), datetime.min.time()))
        store.save_topic(subject, "Algebra", 240)
        windows = [{"day": WEEKDAYS[tomorrow.weekday()], "start": "08:00", "minutes": 60},
                   {"day": WEEKDAYS[tomorrow.weekday()], "start": "18:00", "minutes": 60}]
        store.save_setting("availability", windows)
        self.page("Weekly plan")
        self.button("Preview only").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertEqual(store.sessions(), [])
        self.button("Generate / replan").click().run()
        self.assertEqual(list(self.app.exception), [])
        sessions = Store(self.path).sessions()
        self.assertEqual({datetime.fromisoformat(s["start"]).hour for s in sessions}, {8, 18})
        self.assertTrue(all(datetime.fromisoformat(s["end"]).hour in {8, 9, 18, 19} for s in sessions))
        self.assertEqual(Store(self.path).setting("availability", []), windows)

    def test_overlapping_windows_do_not_replace_a_saved_plan(self):
        self.load_demo()
        self.page("Weekly plan")
        self.button("Generate / replan").click().run()
        store = Store(self.path)
        before = store.sessions()
        windows = [{"day": "Monday", "start": "08:00", "minutes": 60},
                   {"day": "Monday", "start": "08:30", "minutes": 60}]
        store.save_setting("availability", windows)
        self.page("Today")
        self.page("Weekly plan")
        self.button("Generate / replan").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertIn("overlap on Monday", self.app.error[0].value)
        self.assertEqual(Store(self.path).sessions(), before)

    def test_invalid_marks_show_friendly_error(self):
        self.page("Subjects")
        next(t for t in self.app.text_input if t.label == "Subject name").set_value("Math")
        next(n for n in self.app.number_input if n.label == "Current marks").set_value(99.0)
        self.button("Save subject").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertIn("Marks", self.app.error[0].value)
        self.assertEqual(Store(self.path).subjects(), [])

    def test_manual_quiz_and_review_are_persisted(self):
        self.load_demo()
        self.page("Practice")
        next(n for n in self.app.number_input if n.label == "Quiz marks earned").set_value(2.0)
        self.button("Save quiz result").click().run()
        self.assertEqual(len(Store(self.path).rows("SELECT * FROM assessments")), 1)
        self.button("Save recall rating").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertEqual(len(Store(self.path).rows("SELECT * FROM review_logs")), 1)

    def test_focus_timer_starts_and_stops(self):
        self.load_demo()
        self.page("Progress")
        self.button("Start focus").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertIn("focus_timer", self.app.session_state)
        self.button("End focus block").click().run()
        self.assertEqual(list(self.app.exception), [])
        self.assertNotIn("focus_timer", self.app.session_state)

    def test_progress_does_not_generate_a_backup_until_requested(self):
        self.load_demo()
        with patch("planner.storage.Store.backup", side_effect=AssertionError("Backup generated during page render")):
            self.page("Progress")

    def test_notes_search_without_ai(self):
        self.load_demo()
        store = Store(self.path)
        store.save_document(store.subjects()[0]["id"], "lesson.txt", ["Classification predicts a class label for an observation."])
        self.page("Notes & AI")
        next(t for t in self.app.text_input if t.label == "Search your notes").set_value("Classification").run()
        self.assertEqual(list(self.app.exception), [])
        self.assertTrue(any("Classification" in t.value for t in self.app.text))
        self.assertTrue(self.button("Suggest topics from notes").disabled)


if __name__ == "__main__":
    unittest.main()
