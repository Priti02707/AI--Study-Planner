import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from planner import ai
from planner.clock import now
from planner.coach import practice_level, quick_start, recommendations, record_self_check
from planner.storage import Store


class CoachTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "coach.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def setup_map(self, names="Functions\nClasses", start="18:00"):
        return quick_start(self.store, "Python", now() + timedelta(days=10), 85, names, 60, start, 90, 70)

    def test_setup_creates_goal_topics_and_weekday_windows(self):
        self.setup_map()
        self.assertEqual(len(self.store.topics()), 2)
        self.assertEqual(self.store.subjects()[0]["target"], 85)
        self.assertEqual(self.store.subjects()[0]["earned"], 70)
        self.assertEqual(len(self.store.setting("availability", [])), 7)
        self.assertEqual(self.store.setting("availability", [])[0]["minutes"], 90)
        self.assertEqual(self.store.sessions(), [])

    def test_bad_setup_does_not_leave_partial_records(self):
        for names, start in [("Functions\nfunctions", "18:00"), ("", "18:00"), ("Functions", "23:30")]:
            with self.subTest(names=names, start=start), self.assertRaises(ValueError):
                self.setup_map(names, start)
            self.assertEqual(self.store.subjects(), [])
            self.assertIsNone(self.store.setting("coach_setup", None))

    def test_setup_rolls_back_if_topic_write_fails(self):
        with patch.object(self.store, "save_topic", side_effect=ValueError("test rollback")):
            with self.assertRaises(ValueError):
                self.setup_map()
        self.assertEqual(self.store.subjects(), [])
        self.assertEqual(self.store.topics(), [])

    def test_setup_preserves_existing_availability(self):
        windows = [{"day": "Monday", "start": "09:00", "minutes": 30}]
        self.store.save_setting("availability", windows)
        self.setup_map()
        self.assertEqual(self.store.setting("availability", []), windows)

    def test_self_check_updates_priority_and_creates_a_corrective_card(self):
        self.setup_map()
        topic = self.store.topics()[0]
        record_self_check(self.store, topic["id"], "I remember some definitions but cannot explain the steps.", 1,
                          "A function groups reusable statements and can receive arguments and return a value.")
        self.assertEqual(self.store.topics()[0]["latest_score"], 0.2)
        self.assertEqual(len(self.store.cards()), 1)
        items = recommendations(self.store)
        self.assertEqual(items[0]["topic"]["id"], topic["id"])
        self.assertEqual(items[0]["level"], "Foundation")
        self.assertEqual(items[0]["assessments"], 1)
        self.assertTrue(items[0]["mistakes"])

    def test_invalid_self_check_and_no_correction_do_not_create_fake_answers(self):
        self.setup_map()
        topic_id = self.store.topics()[0]["id"]
        with self.assertRaises(ValueError):
            record_self_check(self.store, topic_id, "Too short", 3)
        with self.assertRaises(ValueError):
            record_self_check(self.store, -1, "This explanation is long enough to validate.", 3)
        self.assertEqual(self.store.rows("SELECT * FROM assessments"), [])
        record_self_check(self.store, topic_id, "I cannot yet explain this topic with an example.", 0)
        self.assertEqual(self.store.cards(), [])

    def test_recommendations_omit_expired_exams_and_use_subject_fallback(self):
        self.setup_map()
        self.assertEqual(recommendations(self.store)[0]["level"], "Standard")
        with patch("planner.coach.now", return_value=now() + timedelta(days=20)):
            self.assertEqual(recommendations(self.store), [])


class PracticeLevelTests(unittest.TestCase):
    def test_weighting_boundaries_and_history_limit(self):
        self.assertEqual(practice_level([], 0.49)[1], "Foundation")
        self.assertEqual(practice_level([], 0.5)[1], "Standard")
        self.assertEqual(practice_level([], 0.8)[1], "Challenge")
        self.assertEqual(practice_level([1, 0, 0, 1], 0)[0], 0.5)
        self.assertEqual(practice_level([0, 1, 1], 1)[1], "Standard")
        self.assertEqual(practice_level([0, 0, 1], 1)[1], "Foundation")
        with self.assertRaises(ValueError):
            practice_level([float("nan")], 0.5)

    def test_adaptive_quiz_supplies_level_mistakes_and_validated_sources(self):
        sources = [{"id": "source-1", "label": "Page 1", "text": "A function groups reusable statements and returns a value."}]
        question = {"question": "What does a function group?", "options": ["Statements", "Exams", "Files only", "Scores"],
                    "correct": 0, "explanation": "Functions group reusable statements.", "source_id": "source-1", "evidence": "A function groups reusable statements"}
        with patch("planner.ai.generate", return_value={"questions": [question]}) as generate:
            quiz = ai.generate_quiz("Functions", sources, "Foundation", ["I confused functions and classes"])
        context = generate.call_args.args[1]
        self.assertEqual(context["level"], "Foundation")
        self.assertEqual(context["recent_mistakes"], ["I confused functions and classes"])
        self.assertEqual(quiz[0]["source"], "Page 1")
        with self.assertRaises(ai.AIError):
            ai.generate_quiz("Functions", sources, "Invalid")
