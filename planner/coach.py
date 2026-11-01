"""Explainable onboarding and practice recommendations; no provider is required."""
from datetime import datetime

from planner.availability import WEEKDAYS, validate_windows
from planner.clock import now
from planner.validation import integer, number, text

LEVELS = ("Foundation", "Standard", "Challenge")


def practice_level(scores, fallback):
    """Latest three assessments, newest first, with weights 3:2:1."""
    recent = [number(s, "Assessment score", 0, 1) for s in scores[:3]]
    if recent:
        weights = [3, 2, 1][:len(recent)]
        score = sum(value * weight for value, weight in zip(recent, weights)) / sum(weights)
    else:
        score = number(fallback, "Subject score", 0, 1)
    level = "Foundation" if score < 0.5 else "Standard" if score < 0.8 else "Challenge"
    return score, level


def recommendations(store):
    history = store.rows("SELECT topic_id,earned,maximum,question,correction FROM assessments ORDER BY id DESC")
    result = []
    for topic in store.topics():
        if datetime.fromisoformat(topic["exam"]) <= now():
            continue
        recent = [row for row in history if row["topic_id"] == topic["id"]][:3]
        score, level = practice_level([row["earned"] / row["maximum"] for row in recent], topic["earned"] / topic["maximum"])
        reason = f"Recent assessment signal {score:.0%} across {len(recent)} result(s)." if recent else f"Subject marks {score:.0%}; no topic assessment yet."
        result.append({"topic": topic, "score": score, "level": level, "reason": reason,
                       "assessments": len(recent), "mistakes": [row["question"][:1200] for row in recent if row["earned"] < row["maximum"] and row["question"]]})
    return sorted(result, key=lambda item: (item["score"], item["topic"]["exam"], item["topic"]["id"]))


def quick_start(store, name, exam, target, topic_names, minutes, start_time, daily_minutes, earned=50):
    names = [text(line, "Topic") for line in topic_names.splitlines() if line.strip()]
    if not 1 <= len(names) <= 20:
        raise ValueError("Enter 1–20 topics, one per line.")
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Topic names must be unique.")
    minutes = integer(minutes, "Minutes per topic", 5, 600)
    daily_minutes = integer(daily_minutes, "Daily free minutes", 5, 720)
    if not isinstance(exam, datetime) or exam.tzinfo is not None or exam <= now():
        raise ValueError("Choose an exam date and time in the future.")
    windows = validate_windows([{"day": day, "start": start_time, "minutes": daily_minutes} for day in WEEKDAYS])
    with store.connect():
        subject_id = store.save_subject(name, earned, 100, exam, target)
        for name in names:
            store.save_topic(subject_id, name, minutes)
        # Existing availability belongs to the student; setup never overwrites it.
        if store.setting("availability", None) is None:
            store.save_setting("availability", windows)
        store.save_setting("coach_setup", {"subject_id": subject_id, "created_at": now().isoformat()})
    return subject_id


def record_self_check(store, topic_id, explanation, rating, correction=""):
    explanation = text(explanation, "Your explanation", 5000)
    if len(explanation) < 20:
        raise ValueError("Write at least 20 characters explaining the topic from memory.")
    rating = integer(rating, "Self-check rating", 0, 5)
    correction = str(correction).strip()
    if len(correction) > 5000:
        raise ValueError("Keep your correction within 5000 characters.")
    with store.connect():
        topic = next((item for item in store.topics() if item["id"] == topic_id), None)
        if topic is None:
            raise ValueError("Select an existing topic.")
        store.assessment(topic_id, rating, 5, "Self-rated recall check: " + explanation,
                         "Self-rated diagnostic; not an automatically graded test. " + correction)
        if rating <= 2 and len(correction) >= 20:
            store.add_card(topic_id, f"Explain {topic['name']} and correct your earlier mistake.", correction, "Your self-check correction · verify with your notes")
