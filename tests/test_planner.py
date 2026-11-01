import csv
import io
import json
import os
import random
import subprocess
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from planner import ai
from planner.exports import calendar_export, csv_export
from planner.materials import extract_pdf, passages, retrieve
from planner.models import Slot, Task
from planner.reviews import next_review
from planner.scheduler import merge_slots, schedule, subtract_busy
from planner.storage import Store
from planner.validation import allocate_minutes, integer, number, score

BASE = datetime(2026, 11, 2, 9)


def task(key="a", minutes=60, **changes):
    return replace(Task(key, 1, "Math", key, minutes, 0.5, 3,
                        BASE + timedelta(days=2), BASE), **changes)


class ValidationTests(unittest.TestCase):
    def test_readme_allocation(self):
        self.assertEqual(allocate_minutes([("DL", 8, 10), ("DM", 7, 10), ("Python", 9, 10)], 360),
                         {"DL": 120, "DM": 180, "Python": 60})

    def test_full_marks_and_exact_totals(self):
        result = allocate_minutes([("A", 10, 10), ("B", 10, 10), ("C", 10, 10)], 100)
        self.assertEqual(sum(result.values()), 100)
        self.assertLessEqual(max(result.values()) - min(result.values()), 1)

    def test_normalized_scales(self):
        self.assertEqual(score(8, 10), score(80, 100))
        self.assertEqual(allocate_minutes([("A", 80, 100), ("B", 60, 100)], 120), {"A": 40, "B": 80})

    def test_zero_hours_is_day_off(self):
        self.assertEqual(allocate_minutes([("A", 5, 10)], 0), {"A": 0})

    def test_invalid_numbers(self):
        for value in ["bad", "NaN", "inf", -1, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value, "Input")
        with self.assertRaises(ValueError):
            integer(2.5, "Count")
        with self.assertRaises(ValueError):
            score(11, 10)
        with self.assertRaises(ValueError):
            score(0, 0)

    def test_duplicate_and_empty_subjects(self):
        for subjects in [[], [(" A ", 4, 10), ("a", 5, 10)]]:
            with self.assertRaises(ValueError):
                allocate_minutes(subjects, 60)

    def test_maintenance_time(self):
        self.assertGreater(allocate_minutes([("A", 10, 10), ("B", 5, 10)], 120)["A"], 0)

    def test_console_retries_and_does_not_execute_on_import(self):
        result = subprocess.run([os.sys.executable, "python.py"], input="0\n1\n10\nMath\n10\n2\n", text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Please try again", result.stdout)
        self.assertIn("2h 00m", result.stdout)
        imported = subprocess.run([os.sys.executable, "-c", "import python"], text=True, capture_output=True)
        self.assertEqual(imported.stdout, "")


class SchedulerTests(unittest.TestCase):
    def test_breaks_and_shortfall(self):
        plan = schedule([task(minutes=90)], [Slot(BASE, BASE + timedelta(hours=1))])
        self.assertEqual([int((s.end-s.start).total_seconds()/60) for s in plan.sessions], [25, 25])
        self.assertEqual(plan.unscheduled, {"a": 40})

    def test_break_continues_between_separate_slots(self):
        plan = schedule([task(minutes=60)], [Slot(BASE, BASE+timedelta(minutes=25)),
                                            Slot(BASE+timedelta(minutes=27), BASE+timedelta(hours=1))])
        self.assertEqual(plan.sessions[1].start, BASE+timedelta(minutes=30))

    def test_exam_boundary(self):
        plan = schedule([task(minutes=60, deadline=BASE + timedelta(minutes=33))], [Slot(BASE, BASE + timedelta(hours=2))])
        self.assertEqual(sum(int((s.end-s.start).total_seconds()/60) for s in plan.sessions), 28)
        self.assertTrue(all(s.end <= BASE + timedelta(minutes=33) for s in plan.sessions))

    def test_past_exam(self):
        plan = schedule([task(deadline=BASE - timedelta(days=1))], [Slot(BASE, BASE + timedelta(hours=2))])
        self.assertEqual(plan.sessions, [])
        self.assertEqual(plan.unscheduled, {"a": 60})

    def test_prerequisites(self):
        tasks = [task("a", 25), task("b", 25, mastery=0, prerequisite="a")]
        result = schedule(tasks, [Slot(BASE, BASE + timedelta(hours=2))])
        self.assertEqual([s.task.id for s in result.sessions], ["a", "b"])

    def test_missing_prerequisite(self):
        with self.assertRaises(ValueError):
            schedule([task(prerequisite="missing")], [Slot(BASE, BASE + timedelta(hours=1))])

    def test_overlapping_slots_merge(self):
        slots = [Slot(BASE, BASE + timedelta(hours=1)), Slot(BASE + timedelta(minutes=30), BASE + timedelta(hours=2))]
        self.assertEqual(merge_slots(slots), [Slot(BASE, BASE + timedelta(hours=2))])
        plan = schedule([task(minutes=200)], slots, 25, 0)
        self.assertEqual(sum((s.end-s.start).total_seconds()/60 for s in plan.sessions), 120)

    def test_preserved_time_is_blocked(self):
        slots = subtract_busy([Slot(BASE, BASE + timedelta(hours=2))], [Slot(BASE + timedelta(minutes=30), BASE + timedelta(minutes=60))])
        self.assertEqual(slots, [Slot(BASE, BASE + timedelta(minutes=30)), Slot(BASE + timedelta(hours=1), BASE + timedelta(hours=2))])

    def test_future_review_is_not_scheduled_early(self):
        due = BASE + timedelta(hours=1)
        plan = schedule([task(kind="review", minutes=5, available_from=due)], [Slot(BASE, BASE+timedelta(hours=2))])
        self.assertEqual(plan.sessions[0].start, due)

    def test_interleaving_and_weakness(self):
        result = schedule([task("weak", mastery=0.2, subject="A"), task("strong", mastery=0.9, subject="B")], [Slot(BASE, BASE + timedelta(hours=3))])
        self.assertEqual(result.sessions[0].task.id, "weak")
        self.assertIn("Quiz/marks", result.sessions[0].reason)

    def test_randomized_capacity_invariants(self):
        rng = random.Random(73)
        for _ in range(50):
            tasks = [task(str(i), rng.randint(5, 200), subject=str(i), mastery=rng.random(),
                          deadline=BASE+timedelta(minutes=rng.randint(10, 500))) for i in range(8)]
            result = schedule(tasks, [Slot(BASE, BASE+timedelta(hours=4))])
            allocated = {t.id: 0 for t in tasks}
            previous_end = BASE
            for session in result.sessions:
                self.assertGreaterEqual(session.start, previous_end)
                self.assertLessEqual(session.end, min(session.task.deadline, BASE+timedelta(hours=4)))
                self.assertGreater(session.end, session.start)
                allocated[session.task.id] += int((session.end-session.start).total_seconds()/60)
                previous_end = session.end+timedelta(minutes=5)
            for t in tasks:
                self.assertEqual(allocated[t.id]+result.unscheduled.get(t.id, 0), t.minutes)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"study.sqlite3"
        self.store = Store(self.path)
        self.subject = self.store.save_subject("Math", 7, 10, BASE+timedelta(days=7))
        self.topic = self.store.save_topic(self.subject, "Algebra", 120)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, start=BASE, save=True):
        return self.store.plan([Slot(start, start+timedelta(hours=3))], save=save, start=start)

    def test_persists_across_restart(self):
        self.assertEqual(Store(self.path).topics()[0]["name"], "Algebra")

    def test_cached_reads_do_not_share_mutable_rows(self):
        self.store.subjects()[0]["name"] = "Changed in browser"
        self.assertEqual(self.store.subjects()[0]["name"], "Math")

    def test_writes_invalidate_current_render_reads(self):
        self.assertEqual(self.store.subjects()[0]["name"], "Math")
        self.store.save_subject("Updated Math", 8, 10, BASE+timedelta(days=7), subject_id=self.subject)
        self.assertEqual(self.store.subjects()[0]["name"], "Updated Math")

    def test_repeated_document_reads_remain_decodable(self):
        self.store.save_document(self.subject, "Notes", ["Algebra notes."])
        for _ in range(2):
            docs = self.store.documents(self.subject)
            self.assertEqual(docs[0]["pages"], ["Algebra notes."])

    def test_replan_reads_new_assessments_from_another_store(self):
        self.store.topics()
        Store(self.path).assessment(self.topic, 2, 10)
        plan = self.plan()
        self.assertAlmostEqual(plan.sessions[0].task.mastery, 0.2)

    def test_demo_batch_is_atomic(self):
        self.store.delete_subject(self.subject)
        with patch.object(self.store, "add_card", side_effect=RuntimeError("Simulated interrupted import")):
            with self.assertRaises(RuntimeError):
                self.store.seed_demo()
        self.assertEqual(self.store.subjects(), [])
        self.assertEqual(self.store.topics(), [])

    def test_demo_batch_saves_all_records(self):
        self.store.delete_subject(self.subject)
        self.store.seed_demo()
        self.assertEqual(len(self.store.subjects()), 3)
        self.assertEqual(len(self.store.topics()), 6)
        self.assertEqual(len(self.store.cards()), 6)

    def test_duplicate_subjects_normalized(self):
        with self.assertRaises(ValueError):
            self.store.save_subject(" MATH ", 6, 10, BASE)

    def test_invalid_marks_and_missing_topic_subject(self):
        with self.assertRaises(ValueError):
            self.store.save_subject("Science", 11, 10, BASE)
        with self.assertRaises(ValueError):
            self.store.save_topic(999, "A", 20)

    def test_cycle_prevention(self):
        child = self.store.save_topic(self.subject, "Geometry", 60, prerequisite_id=self.topic)
        with self.assertRaises(ValueError):
            self.store.save_topic(self.subject, "Algebra", 120, prerequisite_id=child, topic_id=self.topic)

    def test_import_atomic_on_duplicates(self):
        with self.assertRaises(ValueError):
            self.store.import_topics(self.subject, [{"name":"New", "minutes":20, "difficulty":2}, {"name":"Algebra", "minutes":20, "difficulty":2}])
        self.assertEqual(len(self.store.topics()), 1)

    def test_preview_does_not_save(self):
        self.assertGreater(len(self.plan(save=False).sessions), 0)
        self.assertEqual(self.store.sessions(), [])

    def test_replan_is_idempotent_and_preserves_completion(self):
        self.plan()
        session = self.store.sessions()[0]
        with patch("planner.storage.now", return_value=BASE+timedelta(minutes=25)):
            self.store.finish_session(session["id"], "completed", actual_minutes=25)
        completed = self.store.sessions()[0]
        for _ in range(2):
            self.plan(BASE+timedelta(minutes=30))
            history = [s for s in self.store.sessions() if s["status"] == "completed"]
            self.assertEqual(history, [completed])
            self.assertEqual(sum(s["planned_minutes"] for s in self.store.sessions() if s["status"] == "planned"), 95)

    def test_partial_replans_only_remaining_work(self):
        self.plan()
        session = self.store.sessions()[0]
        with patch("planner.storage.now", return_value=BASE+timedelta(minutes=25)):
            self.store.finish_session(session["id"], "partial", 10, 10)
        plan = self.plan(BASE+timedelta(minutes=30))
        self.assertEqual(sum(int((s.end-s.start).total_seconds()/60) for s in plan.sessions), 110)

    def test_slow_work_adjusts_estimate(self):
        self.plan()
        session = self.store.sessions()[0]
        with patch("planner.storage.now", return_value=BASE+timedelta(minutes=50)):
            self.store.finish_session(session["id"], "completed", actual_minutes=50)
        topic = self.store.topics()[0]
        self.assertAlmostEqual(topic["pace"], 1.3)
        self.assertGreater(topic["estimated_minutes"], 120)

    def test_skipped_work_is_not_lost(self):
        self.plan()
        session = self.store.sessions()[0]
        with patch("planner.storage.now", return_value=BASE+timedelta(minutes=25)):
            self.store.finish_session(session["id"], "skipped")
        self.plan(BASE+timedelta(minutes=30))
        self.assertEqual(sum(s["planned_minutes"] for s in self.store.sessions() if s["status"] == "planned"), 120)

    def test_future_sessions_cannot_be_completed(self):
        self.plan()
        with patch("planner.storage.now", return_value=BASE-timedelta(hours=1)), self.assertRaises(ValueError):
            self.store.finish_session(self.store.sessions()[0]["id"], "completed", actual_minutes=25)

    def test_duplicate_completion_rejected(self):
        self.plan()
        session = self.store.sessions()[0]
        with patch("planner.storage.now", return_value=BASE+timedelta(minutes=25)):
            self.store.finish_session(session["id"], "completed", actual_minutes=25)
            with self.assertRaises(ValueError):
                self.store.finish_session(session["id"], "completed", actual_minutes=25)

    def test_assessment_changes_priority_signal(self):
        self.store.assessment(self.topic, 2, 10)
        self.assertAlmostEqual(self.store.build_tasks(BASE, BASE+timedelta(days=7))[0].mastery, 0.2)

    def test_card_rating_and_repeated_submit(self):
        with patch("planner.storage.now", return_value=BASE):
            card = self.store.add_card(self.topic, "What is a variable?", "A named reference to a value.")
        due = self.store.review_card(card, 4, BASE)
        self.assertEqual(due, BASE+timedelta(days=1))
        with self.assertRaises(ValueError):
            self.store.review_card(card, 4, BASE)

    def test_generated_quiz_records_feedback_and_mistake_card(self):
        q = {"question":"2+2?", "options":["1","2","3","4"], "correct":3, "explanation":"Addition.", "source":"Notes p1"}
        self.store.record_generated_quiz(self.topic, [q], [0])
        self.assertEqual(self.store.topics()[0]["latest_score"], 0)
        self.assertEqual(len(self.store.cards()), 1)
        self.assertIn("2+2?", self.store.rows("SELECT question FROM assessments")[0]["question"])

    def test_delete_subject_without_history(self):
        self.store.save_topic(self.subject, "Next", 30, prerequisite_id=self.topic)
        self.store.delete_subject(self.subject)
        self.assertEqual(self.store.subjects(), [])

    def test_deletion_preserves_history(self):
        self.plan()
        with patch("planner.storage.now", return_value=BASE+timedelta(minutes=25)):
            self.store.finish_session(self.store.sessions()[0]["id"], "skipped")
        with self.assertRaises(ValueError):
            self.store.delete_subject(self.subject)

    def test_backup(self):
        backup = json.loads(self.store.backup())
        self.assertEqual(backup["format_version"], 1)
        self.assertEqual(len(backup["tables"]["topics"]), 1)


class ReviewAndExportTests(unittest.TestCase):
    def test_review_intervals(self):
        reps, days, ease, due = next_review(4, 0, 0, 2.5, BASE)
        self.assertEqual((reps, days, ease, due), (1, 1, 2.5, BASE+timedelta(days=1)))
        reps, days, ease, _ = next_review(4, reps, days, ease, due)
        self.assertEqual((reps, days), (2, 6))
        self.assertEqual(next_review(4, reps, days, ease, due)[1], 15)
        self.assertEqual(next_review(0, reps, days, 1.3, due)[:3], (0, 1, 1.3))

    def test_calendar_utc_escaping_and_utf8_folding(self):
        row = {"id":1,"status":"planned","start":"2026-11-02T18:00:00","end":"2026-11-02T18:25:00",
               "subject":"Math,Science", "topic":"अध्ययन"*30,"reason":"Line1\nLine2"}
        with patch.dict(os.environ, {"STUDY_PLANNER_TIMEZONE":"Asia/Kolkata"}):
            result = calendar_export([row])
        self.assertIn("DTSTART:20261102T123000Z", result)
        self.assertIn("Math\\,Science", result)
        self.assertTrue(all(len(line.encode()) <= 75 for line in result.split("\r\n")))
        self.assertIn("Line1\\nLine2", result)

    def test_csv_quoting_and_formula_protection(self):
        result = csv_export([{"subject":"=1+1","topic":"A,B\nC"}])
        rows = list(csv.DictReader(io.StringIO(result)))
        self.assertEqual(rows[0]["subject"], "'=1+1")
        self.assertEqual(rows[0]["topic"], "A,B\nC")


class MaterialsAndAITests(unittest.TestCase):
    def setUp(self):
        self.docs = [{"id":1,"name":"notes.txt","pages":["Gradient descent updates model weights to minimize a loss function.", "Clustering groups similar observations."]}]

    def test_page_retrieval(self):
        result = retrieve("gradient weights", self.docs)
        self.assertEqual(result[0]["label"], "notes.txt · page 1")
        self.assertEqual(retrieve("unrelated query", self.docs), [])

    def test_bad_pdf(self):
        with self.assertRaises(ValueError):
            extract_pdf(b"not a PDF")

    def test_valid_text_pdf(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        writer = PdfWriter()
        page = writer.add_blank_page(300, 300)
        font = DictionaryObject({NameObject("/Type"):NameObject("/Font"), NameObject("/Subtype"):NameObject("/Type1"), NameObject("/BaseFont"):NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 250 Td (Gradient descent) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        output = io.BytesIO()
        writer.write(output)
        self.assertIn("Gradient descent", extract_pdf(output.getvalue())[0])

    def test_scanned_pdf_reports_ocr(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(100, 100)
        output = io.BytesIO()
        writer.write(output)
        with self.assertRaisesRegex(ValueError, "OCR"):
            extract_pdf(output.getvalue())

    def test_missing_key_does_not_make_network_request(self):
        with patch.dict(os.environ, {}, clear=True), patch("urllib.request.urlopen") as request:
            with self.assertRaises(ai.AIError):
                ai.generate("Test", {}, {})
            request.assert_not_called()

    def test_evidence_must_exist_in_named_source(self):
        sources = passages(self.docs)
        self.assertEqual(ai.validate_evidence({"source_id":sources[0]["id"],"evidence":"Gradient descent updates model weights"}, sources), sources[0]["label"])
        for item in [{"source_id":"invented","evidence":"Gradient descent updates model weights"},
                     {"source_id":sources[0]["id"],"evidence":"Invented evidence not in the notes"}]:
            with self.assertRaises(ai.AIError):
                ai.validate_evidence(item, sources)

    def test_valid_topic_suggestions(self):
        source = passages(self.docs)[0]
        payload = {"topics":[{"name":"Gradient descent","minutes":60,"difficulty":3,"source_id":source["id"],"evidence":"Gradient descent updates model weights"}]}
        with patch("planner.ai.generate", return_value=payload):
            result = ai.extract_topics([source])
        self.assertEqual(result[0]["minutes"], 60)
        self.assertEqual(result[0]["source"], source["label"])

    def test_uncited_tutor_answer_is_replaced(self):
        with patch("planner.ai.generate", return_value={"answer":"An unsupported statement.","citations":[]}):
            self.assertIn("do not provide", ai.tutor("What?", passages(self.docs))["answer"])

    def test_invalid_ai_json(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":"invalid json"}]}}]}'
        with patch.dict(os.environ, {"GEMINI_API_KEY":"test-key"}), patch("urllib.request.urlopen", return_value=response):
            with self.assertRaises(ai.AIError):
                ai.generate("test", {}, {})


if __name__ == "__main__":
    unittest.main()
