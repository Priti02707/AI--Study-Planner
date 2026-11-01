"""Transactional persistence using local SQLite or hosted PostgreSQL."""

import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from planner.clock import now
from planner.database import PostgresConnection
from planner.models import Slot, Task
from planner.reviews import next_review
from planner.scheduler import schedule, subtract_busy
from planner.validation import integer, number, score, text

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL UNIQUE,
 earned REAL NOT NULL, maximum REAL NOT NULL, exam TEXT NOT NULL, target REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
 id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
 name TEXT NOT NULL, normalized_name TEXT NOT NULL, estimated_minutes INTEGER NOT NULL,
 difficulty INTEGER NOT NULL, prerequisite_id INTEGER REFERENCES topics(id),
 pace REAL NOT NULL DEFAULT 1, UNIQUE(subject_id, normalized_name)
);
CREATE TABLE IF NOT EXISTS cards (
 id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
 question TEXT NOT NULL, answer TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
 due TEXT NOT NULL, repetitions INTEGER NOT NULL DEFAULT 0,
 interval INTEGER NOT NULL DEFAULT 0, ease REAL NOT NULL DEFAULT 2.5
);
CREATE TABLE IF NOT EXISTS sessions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
 card_id INTEGER REFERENCES cards(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'planned', planned_minutes INTEGER NOT NULL,
 done_minutes INTEGER NOT NULL DEFAULT 0, actual_minutes INTEGER NOT NULL DEFAULT 0,
 priority REAL NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assessments (
 id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
 earned REAL NOT NULL, maximum REAL NOT NULL, recorded_at TEXT NOT NULL,
 question TEXT NOT NULL DEFAULT '', correction TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS review_logs (
 id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
 rating INTEGER NOT NULL, reviewed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
 name TEXT NOT NULL, pages TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sessions_start ON sessions(start);
CREATE INDEX IF NOT EXISTS assessments_topic ON assessments(topic_id, id);
"""


class Store:
    def __init__(self, path=None):
        self.database_url = os.environ.get("DATABASE_URL", "") if path is None else ""
        self.path = Path(path or os.environ.get("STUDY_PLANNER_DB", "data/study_planner.sqlite3"))
        if not self.database_url:
            if os.environ.get("VERCEL") == "1":
                raise ValueError("Connect PostgreSQL with DATABASE_URL before using this hosted planner.")
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self, write=True):
        if self.database_url:
            import psycopg
            with psycopg.connect(self.database_url, connect_timeout=10) as connection:
                if write:
                    # Shared by all app writes, including concurrent serverless instances.
                    connection.execute("SELECT pg_advisory_xact_lock(681204718)")
                else:
                    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                yield PostgresConnection(connection)
            return
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, query, params=()):
        with self.connect(write=False) as db:
            return [dict(row) for row in db.execute(query, params)]

    def setting(self, key, default):
        rows = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def save_setting(self, key, value):
        with self.connect() as db:
            db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (key, json.dumps(value)))

    def subjects(self):
        return self.rows("SELECT * FROM subjects ORDER BY exam, name")

    def save_subject(self, name, earned, maximum, exam, target=80, subject_id=None):
        name = text(name, "Subject")
        maximum = number(maximum, "Maximum marks", 0.000001)
        earned = number(earned, "Marks", 0, maximum)
        target = number(target, "Target percentage", 0, 100)
        if not isinstance(exam, datetime) or exam.tzinfo is not None:
            raise ValueError("Exam must be a local date and time.")
        values = (name, name.casefold(), earned, maximum, exam.isoformat(), target)
        try:
            with self.connect() as db:
                if subject_id is None:
                    return db.execute("INSERT INTO subjects(name,normalized_name,earned,maximum,exam,target) VALUES (?,?,?,?,?,?)", values).lastrowid
                cursor = db.execute("UPDATE subjects SET name=?, normalized_name=?, earned=?, maximum=?, exam=?, target=? WHERE id=?",
                                    values + (subject_id,))
                if not cursor.rowcount:
                    raise ValueError("Subject no longer exists.")
                return subject_id
        except sqlite3.IntegrityError:
            raise ValueError("A subject with that name already exists.") from None

    def topics(self):
        return self.rows("""SELECT t.*, s.name AS subject, s.earned, s.maximum, s.exam, s.target,
            COALESCE((SELECT SUM(done_minutes) FROM sessions WHERE topic_id=t.id
                      AND kind='learn' AND status IN ('completed','partial')),0) AS completed_minutes,
            (SELECT earned/maximum FROM assessments WHERE topic_id=t.id ORDER BY id DESC LIMIT 1) AS latest_score
            FROM topics t JOIN subjects s ON s.id=t.subject_id ORDER BY s.exam,s.name,t.id""")

    def save_topic(self, subject_id, name, estimated_minutes, difficulty=3, prerequisite_id=None, topic_id=None):
        name = text(name, "Topic")
        estimated_minutes = integer(estimated_minutes, "Estimated minutes", 5, 100000)
        difficulty = integer(difficulty, "Difficulty", 1, 5)
        try:
            with self.connect() as db:
                if not db.execute("SELECT 1 FROM subjects WHERE id=?", (subject_id,)).fetchone():
                    raise ValueError("Select an existing subject.")
                if topic_id is not None:
                    existing = db.execute("SELECT subject_id FROM topics WHERE id=?", (topic_id,)).fetchone()
                    if not existing or existing["subject_id"] != subject_id:
                        raise ValueError("Topic no longer exists in this subject.")
                seen = {topic_id} if topic_id else set()
                parent = prerequisite_id
                while parent is not None:
                    if parent in seen:
                        raise ValueError("Topic prerequisites must not contain a cycle.")
                    seen.add(parent)
                    row = db.execute("SELECT subject_id,prerequisite_id FROM topics WHERE id=?", (parent,)).fetchone()
                    if not row or row["subject_id"] != subject_id:
                        raise ValueError("Prerequisite must be a topic in the same subject.")
                    parent = row["prerequisite_id"]
                values = (subject_id, name, name.casefold(), estimated_minutes, difficulty, prerequisite_id)
                if topic_id is None:
                    return db.execute("INSERT INTO topics(subject_id,name,normalized_name,estimated_minutes,difficulty,prerequisite_id) VALUES (?,?,?,?,?,?)", values).lastrowid
                db.execute("UPDATE topics SET subject_id=?,name=?,normalized_name=?,estimated_minutes=?,difficulty=?,prerequisite_id=? WHERE id=?", values + (topic_id,))
                return topic_id
        except sqlite3.IntegrityError:
            raise ValueError("That topic name already exists in this subject.") from None

    def delete_subject(self, subject_id):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM sessions JOIN topics ON topics.id=sessions.topic_id WHERE subject_id=? AND status!='planned'", (subject_id,)).fetchone():
                raise ValueError("This subject has study history. Keep it for your progress records.")
            # Remove self-referencing prerequisite links before cascading topics.
            db.execute("UPDATE topics SET prerequisite_id=NULL WHERE subject_id=?", (subject_id,))
            db.execute("DELETE FROM subjects WHERE id=?", (subject_id,))

    def assessment(self, topic_id, earned, maximum, question="", correction=""):
        score(earned, maximum)
        with self.connect() as db:
            db.execute("INSERT INTO assessments(topic_id,earned,maximum,recorded_at,question,correction) VALUES (?,?,?,?,?,?)",
                       (topic_id, earned, maximum, now().isoformat(), question[:5000], correction[:10000]))

    def add_card(self, topic_id, question, answer, source=""):
        question, answer = text(question, "Question", 5000), text(answer, "Answer", 10000)
        with self.connect() as db:
            return db.execute("INSERT INTO cards(topic_id,question,answer,source,due) VALUES (?,?,?,?,?)",
                              (topic_id, question, answer, str(source)[:500], now().isoformat())).lastrowid

    def import_topics(self, subject_id, rows):
        if not rows or len(rows) > 100:
            raise ValueError("Import between 1 and 100 topics at a time.")
        validated = [(text(row.get("name"), "Topic"), integer(row.get("minutes"), "Minutes", 5, 100000),
                      integer(row.get("difficulty"), "Difficulty", 1, 5)) for row in rows]
        try:
            with self.connect() as db:
                for name, minutes, difficulty in validated:
                    db.execute("INSERT INTO topics(subject_id,name,normalized_name,estimated_minutes,difficulty) VALUES (?,?,?,?,?)",
                               (subject_id, name, name.casefold(), minutes, difficulty))
        except sqlite3.IntegrityError:
            raise ValueError("Import cancelled: duplicate topic names or the subject no longer exists. No topics were imported.") from None

    def record_generated_quiz(self, topic_id, questions, choices):
        if not questions or len(questions) != len(choices):
            raise ValueError("Answer every question first.")
        choices = [integer(choice, "Answer", 0, 3) for choice in choices]
        earned = sum(q["correct"] == choice for q, choice in zip(questions, choices))
        mistakes = [(q["question"], f"{q['options'][q['correct']]} — {q['explanation']} ({q['source']})")
                    for q, choice in zip(questions, choices) if q["correct"] != choice]
        with self.connect() as db:
            db.execute("INSERT INTO assessments(topic_id,earned,maximum,recorded_at,question,correction) VALUES (?,?,?,?,?,?)",
                       (topic_id, earned, len(questions), now().isoformat(),
                        "\n\n".join(q for q, _ in mistakes), "\n\n".join(a for _, a in mistakes)))
            for question, answer in mistakes:
                db.execute("INSERT INTO cards(topic_id,question,answer,source,due) VALUES (?,?,?,?,?)",
                           (topic_id, question, answer, "AI practice · verify with your notes", now().isoformat()))

    def cards(self):
        return self.rows("SELECT c.*, t.name AS topic, s.name AS subject FROM cards c JOIN topics t ON t.id=c.topic_id JOIN subjects s ON s.id=t.subject_id ORDER BY due,c.id")

    def review_card(self, card_id, rating, reviewed_at=None):
        reviewed_at = reviewed_at or now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            if not row:
                raise ValueError("Card no longer exists.")
            if datetime.fromisoformat(row["due"]) > reviewed_at:
                raise ValueError("This card is not due yet. Its latest review is already saved.")
            reps, interval, ease, due = next_review(rating, row["repetitions"], row["interval"], row["ease"], reviewed_at)
            db.execute("UPDATE cards SET repetitions=?,interval=?,ease=?,due=? WHERE id=?", (reps, interval, ease, due.isoformat(), card_id))
            db.execute("INSERT INTO review_logs(card_id,rating,reviewed_at) VALUES (?,?,?)", (card_id, rating, reviewed_at.isoformat()))
            # Cancel the stale reservation; rating is the only way to finish recall work.
            db.execute("UPDATE sessions SET status='completed',done_minutes=planned_minutes,actual_minutes=planned_minutes WHERE card_id=? AND status='planned' AND start<=?",
                       (card_id, reviewed_at.isoformat()))
            db.execute("DELETE FROM sessions WHERE card_id=? AND status='planned'", (card_id,))
            return due

    def sessions(self):
        return self.rows("SELECT x.*,t.name AS topic,s.name AS subject FROM sessions x JOIN topics t ON t.id=x.topic_id JOIN subjects s ON s.id=t.subject_id ORDER BY start,x.id")

    def finish_session(self, session_id, status, done_minutes=0, actual_minutes=0):
        if status not in {"completed", "partial", "skipped"}:
            raise ValueError("Choose completed, partial, or skipped.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row or row["status"] != "planned":
                raise ValueError("This session has already been updated.")
            if row["kind"] == "review" and status != "skipped":
                raise ValueError("Rate recall in Practice to complete a review session.")
            if datetime.fromisoformat(row["start"]) > now():
                raise ValueError("This session has not started yet.")
            planned = row["planned_minutes"]
            done = planned if status == "completed" else 0 if status == "skipped" else integer(done_minutes, "Completed work", 1, planned - 1)
            actual = 0 if status == "skipped" else integer(actual_minutes, "Active minutes", 1, 1440)
            db.execute("UPDATE sessions SET status=?,done_minutes=?,actual_minutes=? WHERE id=?", (status, done, actual, session_id))
            if done:
                topic = db.execute("SELECT pace,estimated_minutes FROM topics WHERE id=?", (row["topic_id"],)).fetchone()
                pace = topic["pace"]
                ratio = min(3, max(0.25, actual / done))
                new_pace = 0.7 * pace + 0.3 * ratio
                completed = db.execute("SELECT COALESCE(SUM(done_minutes),0) FROM sessions WHERE topic_id=? AND kind='learn' AND status IN ('completed','partial')", (row["topic_id"],)).fetchone()[0]
                remaining = max(0, topic["estimated_minutes"] - completed)
                updated_total = completed + math.ceil(remaining * new_pace / pace)
                db.execute("UPDATE topics SET pace=?,estimated_minutes=? WHERE id=?", (new_pace, updated_total, row["topic_id"]))

    def build_tasks(self, start, horizon):
        topics = self.topics()
        unfinished = {t["id"] for t in topics if t["estimated_minutes"] > t["completed_minutes"]}
        tasks = []
        for topic in topics:
            outstanding = max(0, topic["estimated_minutes"] - topic["completed_minutes"])
            if not outstanding:
                continue
            mastery = topic["latest_score"] if topic["latest_score"] is not None else topic["earned"] / topic["maximum"]
            parent = topic["prerequisite_id"]
            tasks.append(Task(f"learn:{topic['id']}", topic["id"], topic["subject"], topic["name"], outstanding,
                              mastery, topic["difficulty"], datetime.fromisoformat(topic["exam"]), start,
                              prerequisite=f"learn:{parent}" if parent in unfinished else None))
        lookup = {t["id"]: t for t in topics}
        for card in self.cards():
            if datetime.fromisoformat(card["due"]) >= horizon:
                continue
            topic = lookup[card["topic_id"]]
            parent = f"learn:{topic['id']}" if topic["id"] in unfinished else None
            tasks.append(Task(f"review:{card['id']}", topic["id"], topic["subject"], topic["name"] + " · recall", 5,
                              topic["latest_score"] if topic["latest_score"] is not None else topic["earned"] / topic["maximum"],
                              topic["difficulty"], datetime.fromisoformat(topic["exam"]),
                              max(start, datetime.fromisoformat(card["due"])), "review", parent, card["id"]))
        return tasks

    def plan(self, slots, session_minutes=25, break_minutes=5, save=False, start=None):
        start = start or now()
        slots = [Slot(max(s.start, start), s.end) for s in slots if s.end > start]
        if not slots:
            raise ValueError("Add at least one future free time slot.")
        horizon = max(s.end for s in slots)
        with self.connect() as db:
            # Reserve the write lock before taking a coherent snapshot on other connections.
            db.execute("BEGIN IMMEDIATE")
            tasks = self.build_tasks(start, horizon)
            busy = [Slot(datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"]) +
                         timedelta(minutes=break_minutes if r["status"] != "skipped" else 0))
                    for r in db.execute("SELECT start,end,status FROM sessions WHERE status!='planned' OR start<?", (start.isoformat(),))]
            # In-progress/unreported sessions are replaced as remaining work; past time
            # is never reused. Finished intervals always stay blocked.
            plan = schedule(tasks, subtract_busy(slots, busy), session_minutes, break_minutes)
            if save:
                db.execute("DELETE FROM sessions WHERE status='planned'")
                for item in plan.sessions:
                    duration = int((item.end - item.start).total_seconds() // 60)
                    db.execute("INSERT INTO sessions(topic_id,card_id,kind,start,end,planned_minutes,priority,reason) VALUES (?,?,?,?,?,?,?,?)",
                               (item.task.topic_id, item.task.card_id, item.task.kind, item.start.isoformat(), item.end.isoformat(), duration, item.priority, item.reason))
                self_values = {"generated_at": start.isoformat(), "unscheduled": plan.unscheduled}
                db.execute("INSERT INTO settings VALUES ('last_plan',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(self_values),))
        return plan

    def save_document(self, subject_id, name, pages):
        if not pages or not any(p.strip() for p in pages):
            raise ValueError("No readable text found. Scanned PDFs need OCR first.")
        with self.connect() as db:
            return db.execute("INSERT INTO documents(subject_id,name,pages) VALUES (?,?,?)",
                              (subject_id, text(name, "Document name", 300), json.dumps(pages))).lastrowid

    def documents(self, subject_id):
        docs = self.rows("SELECT * FROM documents WHERE subject_id=? ORDER BY id DESC", (subject_id,))
        for doc in docs:
            doc["pages"] = json.loads(doc["pages"])
        return docs

    def backup(self):
        tables = ("subjects", "topics", "cards", "sessions", "assessments", "review_logs", "documents", "settings")
        with self.connect(write=False) as db:
            db.execute("BEGIN")
            return json.dumps({"format_version": 1, "exported_at": now().isoformat(),
                               "tables": {table: [dict(r) for r in db.execute(f"SELECT * FROM {table}")] for table in tables}}, indent=2)

    def seed_demo(self):
        if self.subjects():
            raise ValueError("Demo data can only be loaded into an empty planner.")
        today = now()
        for name, marks, days, topics in [
            ("Python", 8, 10, ["Functions and scope", "Classes and objects"]),
            ("Data Mining", 5, 6, ["Classification", "Clustering"]),
            ("Deep Learning", 7, 14, ["Neural networks", "Backpropagation"]),
        ]:
            subject_id = self.save_subject(name, marks, 10, (today + timedelta(days=days)).replace(hour=9, minute=0), 85)
            previous = None
            for topic in topics:
                topic_id = self.save_topic(subject_id, topic, 75, 3, previous)
                self.add_card(topic_id, f"Explain {topic.lower()} from memory.",
                              "Describe the key idea, give one example, and check your notes for missing details.", "Demo self-check prompt")
                previous = topic_id
