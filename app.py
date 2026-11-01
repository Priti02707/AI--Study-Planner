"""Study Planner dashboard. Launch with: streamlit run app.py"""
import json
import os
import time as timer_time
from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from planner import ai
from planner.access import deployment_errors, hosted
from planner.accounts import Accounts, OWNER_ID
from planner.availability import WEEKDAYS, validate_windows, weekly_slots
from planner.clock import now, timezone_name
from planner.exports import calendar_export, csv_export
from planner.materials import extract_pdf, passages, retrieve
from planner.storage import Store

st.set_page_config(page_title="Study Planner · Your next step", page_icon="🌱", layout="wide")


def flash(message):
    st.session_state["notice"] = message
    st.rerun()


def topic_label(topic):
    return f"{topic['subject']} / {topic['name']}"


def choose_topic(topics, key):
    return st.selectbox("Topic", topics, format_func=topic_label, key=key)


def session_table(sessions):
    if not sessions:
        st.info("No sessions here yet. Generate a plan in Weekly plan.")
        return
    st.dataframe(pd.DataFrame([{
        "Date": s["start"][:10], "Start": s["start"][11:16], "End": s["end"][11:16],
        "Subject": s["subject"], "Topic": s["topic"], "Type": s["kind"],
        "Minutes": s["planned_minutes"], "Status": s["status"], "Why this session": s["reason"],
    } for s in sessions]), hide_index=True, width="stretch")


def today_page(store):
    st.title("A little progress, every day.")
    st.write("Your next study session, with a clear reason to start.")
    topics, sessions, subjects = store.topics(), store.sessions(), store.subjects()
    current = now()
    today = [s for s in sessions if s["start"][:10] == current.date().isoformat()]
    future = [s for s in subjects if s["exam"] > current.isoformat()]
    due = [c for c in store.cards() if c["due"] <= current.isoformat()]
    columns = st.columns(4)
    columns[0].metric("Today’s planned focus", f"{sum(s['planned_minutes'] for s in today if s['status'] == 'planned')} min")
    columns[1].metric("Sessions finished today", sum(s["status"] == "completed" for s in today))
    columns[2].metric("Cards ready to review", len(due))
    columns[3].metric("Next exam", future[0]["name"] if future else "No upcoming exam")
    if not subjects:
        st.info("Start by adding your subjects and exam dates, or explore a sample planner.")
        if st.button("Load sample subjects", type="primary"):
            store.seed_demo()
            flash("Sample subjects added. Open Weekly plan to build your timetable.")
        return
    overdue = [s for s in sessions if s["status"] == "planned" and s["end"] < current.isoformat()]
    if overdue:
        st.warning(f"{len(overdue)} unfinished sessions are overdue. Record any work you did, then regenerate your plan to move the rest.")
    st.subheader("Today’s sessions")
    session_table(today)
    pending = [s for s in sessions if s["status"] == "planned" and s["start"] <= current.isoformat()]
    if pending:
        st.subheader("Record your progress")
        with st.form("finish_session"):
            session = st.selectbox("Session", pending,
                                   format_func=lambda s: f"{s['start'][:16]} · {s['subject']} / {s['topic']} ({s['kind']})")
            status = st.selectbox("Outcome", ["completed", "partial", "skipped"])
            st.caption("For partial work, enter how many planned minutes of work you completed. Rate review cards in Practice.")
            done = st.number_input("Planned work completed (partial only)", min_value=0, max_value=180, value=10)
            actual = st.number_input("Actual active study minutes", min_value=1, max_value=1440, value=25)
            if st.form_submit_button("Save progress", type="primary"):
                store.finish_session(session["id"], status, done, actual)
                flash("Progress saved. Regenerate your weekly plan to apply the update.")
    st.subheader("Where to focus")
    if topics:
        ranked = sorted(topics, key=lambda t: t["latest_score"] if t["latest_score"] is not None else t["earned"] / t["maximum"])
        for topic in ranked[:3]:
            mastery = topic["latest_score"] if topic["latest_score"] is not None else topic["earned"] / topic["maximum"]
            st.write(f"**{topic_label(topic)}** · latest score {mastery:.0%} · {max(0, topic['estimated_minutes'] - topic['completed_minutes'])} min remaining")
    st.caption("Scores reflect recorded marks or the latest topic quiz. They are planning signals, not predictions of exam results.")


def subjects_page(store):
    st.title("Build your study map")
    st.write("Subjects give you direction. Topics make the work manageable.")
    subjects = store.subjects()
    left, right = st.columns(2)
    with left:
        st.subheader("Subject & exam")
        selected = st.selectbox("Edit subject", [None] + subjects,
                                format_func=lambda s: "Add a new subject" if s is None else s["name"])
        key = selected["id"] if selected else "new"
        exam = datetime.fromisoformat(selected["exam"]) if selected else now() + timedelta(days=14)
        with st.form(f"subject_{key}"):
            name = st.text_input("Subject name", value=selected["name"] if selected else "")
            earned = st.number_input("Current marks", min_value=0.0, value=float(selected["earned"]) if selected else 7.0)
            maximum = st.number_input("Maximum marks", min_value=0.01, value=float(selected["maximum"]) if selected else 10.0)
            target = st.slider("Target score (%)", 0, 100, int(selected["target"]) if selected else 80)
            day = st.date_input("Exam date", value=exam.date())
            at = st.time_input("Exam starts", value=exam.time().replace(second=0, microsecond=0))
            if st.form_submit_button("Save subject", type="primary"):
                store.save_subject(name, earned, maximum, datetime.combine(day, at), target, selected["id"] if selected else None)
                flash("Subject saved. Regenerate the plan if its marks or exam date changed.")
        if selected:
            with st.expander("Remove a subject without study history"):
                confirm = st.checkbox("Remove this subject, its topics, cards, and documents", key=f"delete_{key}")
                if st.button("Remove subject", disabled=not confirm):
                    store.delete_subject(selected["id"])
                    flash("Subject removed.")
    with right:
        st.subheader("Topics & prerequisites")
        if not subjects:
            st.info("Save a subject first.")
        else:
            subject = st.selectbox("Subject", subjects, format_func=lambda s: s["name"], key="topic_subject")
            existing = [t for t in store.topics() if t["subject_id"] == subject["id"]]
            topic = st.selectbox("Edit topic", [None] + existing, format_func=lambda t: "Add a new topic" if t is None else t["name"])
            topic_key = topic["id"] if topic else "new"
            prerequisites = [None] + [t for t in existing if not topic or t["id"] != topic["id"]]
            default_parent = next((i for i, t in enumerate(prerequisites) if t and topic and t["id"] == topic["prerequisite_id"]), 0)
            with st.form(f"topic_{subject['id']}_{topic_key}"):
                name = st.text_input("Topic name", value=topic["name"] if topic else "")
                minutes = st.number_input("Estimated total work (minutes)", 5, 100000, int(topic["estimated_minutes"]) if topic else 60, step=5)
                difficulty = st.slider("Difficulty", 1, 5, int(topic["difficulty"]) if topic else 3)
                parent = st.selectbox("Study this first", prerequisites, index=default_parent, format_func=lambda t: "No prerequisite" if t is None else t["name"])
                if st.form_submit_button("Save topic", type="primary"):
                    store.save_topic(subject["id"], name, minutes, difficulty, parent["id"] if parent else None, topic["id"] if topic else None)
                    flash("Topic saved.")
    topics = store.topics()
    if topics:
        st.subheader("Your topics")
        st.dataframe(pd.DataFrame([{"Subject": t["subject"], "Topic": t["name"], "Estimated min": t["estimated_minutes"],
                                    "Finished min": t["completed_minutes"], "Difficulty": t["difficulty"],
                                    "Exam": t["exam"][:16].replace("T", " ")} for t in topics]), hide_index=True, width="stretch")


def plan_page(store):
    st.title("Make room for what matters")
    st.write("A realistic timetable that works around your week.")
    if not store.topics():
        st.info("Add subjects and topics first.")
        return
    saved = store.setting("availability", [{"day": day, "start": "18:00", "minutes": 120} for day in WEEKDAYS])
    settings = store.setting("plan_options", {"days": 14, "session": 25, "break": 5})
    with st.form("availability"):
        st.caption("Add a row for each study window, including multiple windows on the same weekday. Delete rows or set free minutes to zero for days without study time.")
        availability = st.data_editor(pd.DataFrame(saved, columns=["day", "start", "minutes"]), hide_index=True, num_rows="dynamic",
                                      column_config={"day": st.column_config.SelectboxColumn("Weekday", options=list(WEEKDAYS), required=True),
                                                     "minutes": st.column_config.NumberColumn("Free minutes", min_value=0, max_value=720, step=5, required=True),
                                                     "start": st.column_config.TextColumn("Start time (HH:MM)", required=True)},
                                      width="stretch", key="availability_editor")
        a, b, c = st.columns(3)
        start = a.date_input("Plan starts", value=now().date(), min_value=now().date())
        days = a.number_input("Plan length (days)", 1, 90, int(settings["days"]))
        session = b.number_input("Focus session (minutes)", 5, 180, int(settings["session"]), step=5)
        rest = b.number_input("Break between sessions (minutes)", 0, 60, int(settings["break"]))
        choices = [start + timedelta(days=i) for i in range(days)]
        default_off = [d for d in choices if d.isoformat() in settings.get("days_off", [])]
        off = c.multiselect("Days off", choices, default=default_off, format_func=lambda d: d.strftime("%a %d %b"))
        st.caption("Breaks use part of your available window. Regenerating replaces unfinished reservations and preserves finished work. Record partial work first.")
        generate = st.form_submit_button("Generate / replan", type="primary")
        simulate = st.form_submit_button("Preview only")
    if generate or simulate:
        rows = validate_windows(availability.to_dict("records"))
        slots = weekly_slots(start, days, rows, off)
        plan = store.plan(slots, session, rest, save=generate)
        if generate:
            store.save_setting("availability", rows)
            store.save_setting("plan_options", {"days": days, "session": session, "break": rest,
                                                "days_off": [d.isoformat() for d in off]})
            flash(f"Plan saved: {len(plan.sessions)} sessions; {sum(plan.unscheduled.values())} minutes could not fit before the horizon or exam deadlines.")
        st.subheader("Preview · nothing saved")
        st.dataframe([{"Subject": p.task.subject, "Topic": p.task.topic, "Start": p.start, "End": p.end,
                       "Reason": p.reason} for p in plan.sessions], hide_index=True, width="stretch")
        st.warning(f"Unscheduled workload: {sum(plan.unscheduled.values())} min. Includes work beyond this planning window.")
    last = store.setting("last_plan", {})
    if last.get("unscheduled"):
        topics = {t["id"]: topic_label(t) for t in store.topics()}
        cards = {c["id"]: f"{c['subject']} / {c['topic']} · recall" for c in store.cards()}
        st.warning("Some work did not fit. Add availability, extend the planning window, or adjust scope. This includes unfinished topics beyond the chosen window.")
        st.dataframe([{"Task": (topics if key.startswith("learn:") else cards).get(int(key.split(":")[1]), key),
                       "Unscheduled minutes": minutes} for key, minutes in last["unscheduled"].items()], hide_index=True)
    session_table(store.sessions())
    sessions = store.sessions()
    if sessions:
        cols = st.columns(2)
        cols[0].download_button("Download CSV", csv_export(sessions), "study-plan.csv", "text/csv")
        cols[1].download_button("Add to calendar (.ics)", calendar_export(sessions), "study-plan.ics", "text/calendar")
        st.caption("Calendar export includes planned sessions. Remove an older imported calendar before importing a regenerated plan to avoid stale events.")


def practice_page(store):
    st.title("Make it stick")
    st.write("Recall first. Check your answer. Let the next plan learn from it.")
    topics = store.topics()
    if not topics:
        st.info("Add a topic first.")
        return
    tab_review, tab_score, tab_cards, tab_quiz = st.tabs(["Review queue", "Record a quiz", "Create a card", "AI practice"])
    with tab_review:
        due = [c for c in store.cards() if c["due"] <= now().isoformat()]
        if not due:
            st.success("Your review queue is clear.")
        for card in due[:20]:
            with st.container(border=True):
                st.caption(f"{card['subject']} / {card['topic']}")
                st.write(card["question"])
                with st.expander("Reveal answer"):
                    st.write(card["answer"])
                    st.caption(card["source"] or "Your own study card")
                with st.form(f"rate_{card['id']}"):
                    rating = st.select_slider("How well did you recall it?", options=list(range(6)), value=3,
                                              format_func=lambda x: ["0 · Forgot", "1 · Incorrect", "2 · Almost", "3 · Hard", "4 · Good", "5 · Easy"][x])
                    if st.form_submit_button("Save recall rating"):
                        due_at = store.review_card(card["id"], rating)
                        flash(f"Review saved. Next review: {due_at:%d %b %Y %H:%M}.")
        all_cards = store.cards()
        if all_cards:
            st.caption(f"{len(all_cards)} cards saved · intervals adapt using an SM-2 based algorithm.")
    with tab_score:
        with st.form("assessment"):
            topic = choose_topic(topics, "assessment_topic")
            earned = st.number_input("Quiz marks earned", 0.0, value=6.0)
            maximum = st.number_input("Quiz maximum marks", 0.01, value=10.0)
            question = st.text_area("What did you get wrong? (optional)")
            correction = st.text_area("Correction / lesson learned (optional)")
            if st.form_submit_button("Save quiz result", type="primary"):
                store.assessment(topic["id"], earned, maximum, question, correction)
                flash("Quiz saved. Regenerate your plan to apply the new topic priority.")
    with tab_cards:
        with st.form("new_card"):
            topic = choose_topic(topics, "card_topic")
            question = st.text_area("Recall question")
            answer = st.text_area("Answer / checking guide")
            source = st.text_input("Source (optional)", placeholder="Textbook, chapter 3, page 42")
            if st.form_submit_button("Add review card", type="primary"):
                store.add_card(topic["id"], question, answer, source)
                flash("Card added to your review queue.")
    with tab_quiz:
        st.caption("Optional: relevant note excerpts are sent to Gemini when you generate questions. Check generated answers against the source.")
        topic = choose_topic(topics, "ai_quiz_topic")
        if st.button("Generate source-based quiz", disabled=not ai.configured()):
            with st.spinner("Preparing your questions…"):
                sources = retrieve(topic["name"], store.documents(topic["subject_id"]))
                st.session_state["quiz"] = {"topic_id": topic["id"], "questions": ai.generate_quiz(topic["name"], sources), "graded": False}
        quiz = st.session_state.get("quiz")
        if quiz and quiz["topic_id"] == topic["id"]:
            if not quiz["graded"]:
                with st.form("take_quiz"):
                    choices = []
                    for i, question in enumerate(quiz["questions"]):
                        choices.append(st.radio(question["question"], range(4), index=None,
                                                format_func=lambda j, q=question: q["options"][j], key=f"q_{i}"))
                    if st.form_submit_button("Grade & save"):
                        if None in choices:
                            st.warning("Answer every question before submitting.")
                        else:
                            store.record_generated_quiz(topic["id"], quiz["questions"], choices)
                            quiz["graded"], quiz["choices"] = True, choices
                            st.rerun()
            else:
                correct = sum(q["correct"] == answer for q, answer in zip(quiz["questions"], quiz["choices"]))
                st.success(f"Saved: {correct}/{len(quiz['questions'])}. Missed questions are in your mistake notebook.")
                for question in quiz["questions"]:
                    st.write(f"**{question['question']}**")
                    st.write(question["options"][question["correct"]])
                    st.write(question["explanation"])
                    st.caption(question["source"])
                    st.caption("Source evidence: " + question["evidence"])
        if not ai.configured():
            st.info("AI is optional. See README for GEMINI_API_KEY setup. Manual quizzes and cards work now.")


def notes_page(store):
    st.title("Your notes, connected")
    st.write("Import material, find a source, and turn the syllabus into a plan.")
    subjects = store.subjects()
    if not subjects:
        st.info("Add a subject first.")
        return
    subject = st.selectbox("Subject", subjects, format_func=lambda s: s["name"], key="notes_subject")
    with st.form("upload_notes", clear_on_submit=True):
        upload_limit = 3 if hosted() else 10
        uploaded = st.file_uploader("PDF or text notes", type=["pdf", "txt"], max_upload_size=upload_limit)
        if st.form_submit_button("Import notes", type="primary"):
            if uploaded is None:
                raise ValueError("Choose a document first.")
            content = uploaded.getvalue()
            if len(content) > upload_limit * 1024 * 1024:
                raise ValueError(f"Document must be {upload_limit} MB or smaller.")
            pages = extract_pdf(content) if uploaded.name.lower().endswith(".pdf") else [content.decode("utf-8", errors="replace")[:100000]]
            store.save_document(subject["id"], uploaded.name, pages)
            flash("Notes imported locally.")
    docs = store.documents(subject["id"])
    for doc in docs:
        with st.expander(f"{doc['name']} · {len(doc['pages'])} pages"):
            page = st.number_input("Page", 1, len(doc["pages"]), 1, key=f"page_{doc['id']}")
            st.text(doc["pages"][page - 1])
    st.subheader("Find a passage")
    query = st.text_input("Search your notes", placeholder="e.g. gradient descent")
    if query:
        found = retrieve(query, docs)
        if not found:
            st.info("No matching passages found.")
        for item in found:
            with st.expander(item["label"]):
                st.text(item["text"])
    st.subheader("Syllabus → editable topics")
    st.caption("Generating sends up to 30 note excerpts to Gemini. Review and edit every suggestion before importing.")
    if st.button("Suggest topics from notes", disabled=not ai.configured() or not docs):
        with st.spinner("Reading your syllabus…"):
            st.session_state["draft_topics"] = {"subject_id": subject["id"], "rows": ai.extract_topics(passages(docs)[:30])}
    draft = st.session_state.get("draft_topics")
    if draft and draft["subject_id"] == subject["id"]:
        with st.form("confirm_topics"):
            edited = st.data_editor(pd.DataFrame(draft["rows"]), num_rows="dynamic", hide_index=True,
                                    column_config={"minutes": st.column_config.NumberColumn(min_value=5, max_value=600),
                                                   "difficulty": st.column_config.NumberColumn(min_value=1, max_value=5)},
                                    width="stretch")
            if st.form_submit_button("Confirm & import topics"):
                store.import_topics(subject["id"], edited.to_dict("records"))
                del st.session_state["draft_topics"]
                flash("Topics imported. Add prerequisites in Subjects, then generate a plan.")
    st.subheader("Ask your notes")
    with st.form("ask_notes"):
        question = st.text_input("Your question")
        if st.form_submit_button("Ask with sources", disabled=not ai.configured()):
            with st.spinner("Checking the relevant passages…"):
                result = ai.tutor(question, retrieve(question, docs))
            st.write(result["answer"])
            for item in result["citations"]:
                st.caption(item["source"])
                st.text(item["evidence"])


@st.fragment(run_every="1s")
def focus_timer(store, topics):
    running = st.session_state.get("focus_timer")
    if running:
        elapsed = max(0, timer_time.time() - running["started"])
        remaining = max(0, running["minutes"] * 60 - elapsed)
        st.metric(running["label"], f"{int(remaining) // 60:02d}:{int(remaining) % 60:02d}")
        st.progress(min(1.0, elapsed / (running["minutes"] * 60)))
        if remaining == 0:
            st.success("Focus block finished. Take a break, then record your session outcome on Today.")
        if st.button("End focus block"):
            del st.session_state["focus_timer"]
            st.rerun()
    else:
        with st.form("start_focus"):
            topic = choose_topic(topics, "focus_topic")
            minutes = st.slider("Focus minutes", 5, 90, 25, step=5)
            if st.form_submit_button("Start focus", type="primary"):
                st.session_state["focus_timer"] = {"started": timer_time.time(), "minutes": minutes, "label": topic_label(topic)}
                st.rerun()


def progress_page(store):
    st.title("See how far you’ve come")
    topics, sessions = store.topics(), store.sessions()
    if topics:
        for topic in topics:
            progress = min(topic["completed_minutes"] / topic["estimated_minutes"], 1.0)
            st.progress(progress, text=f"{topic_label(topic)} · {progress:.0%} of estimated work completed")
        st.subheader("Focus timer")
        st.caption("Timer state lasts for this browser session. Record study outcomes on Today; elapsed timer time does not automatically mark learning complete.")
        focus_timer(store, topics)
    finished = [s for s in sessions if s["actual_minutes"] > 0]
    if finished:
        st.subheader("Actual focus time by day")
        frame = pd.DataFrame(finished)
        frame["Day"] = frame["start"].str[:10]
        st.bar_chart(frame.groupby("Day")["actual_minutes"].sum(), y_label="Active minutes")
        st.subheader("Time by subject")
        st.bar_chart(frame.groupby("subject")["actual_minutes"].sum(), y_label="Active minutes")
    results = store.rows("SELECT a.*, t.name AS topic, s.name AS subject FROM assessments a JOIN topics t ON t.id=a.topic_id JOIN subjects s ON s.id=t.subject_id ORDER BY a.id")
    if results:
        st.subheader("Quiz history")
        frame = pd.DataFrame(results)
        frame["Score (%)"] = frame["earned"] / frame["maximum"] * 100
        st.dataframe(frame[["subject", "topic", "recorded_at", "Score (%)"]], hide_index=True, width="stretch")
        st.subheader("Mistake notebook")
        mistakes = [r for r in results if r["question"] or r["correction"]]
        for result in reversed(mistakes):
            with st.expander(f"{result['subject']} / {result['topic']} · {result['recorded_at'][:10]}"):
                st.write(result["question"])
                st.write(result["correction"])
    if not finished and not results:
        st.info("Your progress appears here after you record study work or a quiz.")
    st.download_button("Export all my data (JSON)", store.backup, "study-planner-backup.json", "application/json")
    st.caption("The JSON export includes your notes and study history. Keep it somewhere private. This version exports backups; restore is not yet supported in the interface.")


def enter_account(token):
    # Clear quiz drafts, uploaded material, focus timers, and widget selections
    # before moving between accounts in the same browser session.
    st.session_state.clear()
    st.session_state["account_token"] = token
    st.rerun()


def account_page(accounts):
    st.title("🌱 Your study space")
    st.write("Your subjects, your schedule, your progress. Sign in to pick up where you left off.")
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    choices = ["Sign in", "Create account"]
    if len(os.environ.get("STUDY_PLANNER_PASSWORD", "")) >= 12:
        choices.append("Existing workspace")
    mode = st.radio("Account", choices, horizontal=True)
    try:
        if mode == "Create account":
            with st.form("register_account"):
                name = st.text_input("Your name", max_chars=80)
                handle = st.text_input("Choose a username", max_chars=40)
                password = st.text_input("Password", type="password", max_chars=128)
                confirm = st.text_input("Confirm password", type="password", max_chars=128)
                st.caption("Choose a password with at least 12 characters. Save your username and password; email recovery is not available yet.")
                if st.form_submit_button("Create my account", type="primary"):
                    if password != confirm:
                        raise ValueError("The passwords do not match.")
                    accounts.register(name, handle, password)
                    enter_account(accounts.sign_in(handle, password))
        elif mode == "Existing workspace":
            st.info("For the original project workspace only. New students should create an account for their own private planner.")
            with st.form("workspace_login"):
                password = st.text_input("Workspace password", type="password", max_chars=128)
                if st.form_submit_button("Open my planner", type="primary"):
                    enter_account(accounts.sign_in("", password, owner=True))
        else:
            with st.form("sign_in_account"):
                handle = st.text_input("Username", max_chars=40)
                password = st.text_input("Password", type="password", max_chars=128)
                if st.form_submit_button("Sign in", type="primary"):
                    enter_account(accounts.sign_in(handle, password))
            st.caption("New here? Choose Create account. Every student gets a separate private planner.")
    except ValueError as exc:
        st.error(str(exc))


def main():
    errors = deployment_errors()
    if errors:
        st.title("Study Planner · finish setup")
        for error in errors:
            st.error(error)
        st.info("Your deployment is running. Complete the project environment settings to enable this private workspace.")
        return
    accounts = Accounts()
    token = st.session_state.get("account_token")
    identity = accounts.identity(token)
    if not identity:
        if token:
            st.session_state.clear()
            st.warning("Your session expired. Please sign in again.")
        account_page(accounts)
        return
    original = identity["id"] == OWNER_ID
    store = Store(workspace_id=None if original else identity["id"])
    with st.sidebar:
        st.title("🌱 Study Planner")
        st.caption("Small steps. Stronger recall.")
        page = st.radio("Workspace", ["Today", "Subjects", "Weekly plan", "Practice", "Notes & AI", "Progress"])
        st.divider()
        st.caption(f"{now():%A, %d %B %Y} · {timezone_name()}")
        st.text(identity["display_name"])
        st.caption("Original workspace" if original else f"Signed in as @{identity['username']}")
        st.caption("Saved in PostgreSQL · private account" if store.database_url else "Saved locally · private account")
        if st.button("Sign out"):
            accounts.sign_out(token)
            st.session_state.clear()
            st.rerun()
        if not original:
            with st.expander("Change password"):
                with st.form("change_password"):
                    current = st.text_input("Current password", type="password", max_chars=128)
                    new_password = st.text_input("New password", type="password", max_chars=128)
                    confirm = st.text_input("Confirm new password", type="password", max_chars=128)
                    if st.form_submit_button("Update password"):
                        try:
                            if new_password != confirm:
                                raise ValueError("The new passwords do not match.")
                            accounts.change_password(token, current, new_password)
                            st.session_state.clear()
                            flash("Password changed. Sign in with your new password.")
                        except ValueError as exc:
                            st.error(str(exc))
        st.caption("AI ready" if ai.configured() else "Core planner works without an API key")
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    pages = {"Today": today_page, "Subjects": subjects_page, "Weekly plan": plan_page,
             "Practice": practice_page, "Notes & AI": notes_page, "Progress": progress_page}
    try:
        pages[page](store)
    except ValueError as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
