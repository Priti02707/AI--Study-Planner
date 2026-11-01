"""Guided setup, self-rated recall checks, and a reviewable starting timetable."""
from datetime import datetime, time, timedelta
import hashlib
import json

import streamlit as st

from planner.availability import WEEKDAYS, weekly_slots
from planner.clock import now
from planner.coach import quick_start, recommendations, record_self_check


def coach_page(store, notify):
    st.title("Your next step, made clear")
    st.write("Set a goal, check what you recall, and choose a plan that fits your week.")
    if not store.topics():
        st.subheader("Build your first study map")
        st.caption("Enter topics from your syllabus. You can import notes and review AI topic suggestions in Notes & AI later.")
        with st.form("coach_setup"):
            name = st.text_input("First subject")
            marks = st.number_input("Current marks out of 100", 0, 100, 50)
            target = st.slider("Your target (%)", 0, 100, 80)
            exam_date = st.date_input("Your exam date", value=now().date() + timedelta(days=14), min_value=now().date())
            exam_time = st.time_input("Your exam time", value=time(9))
            names = st.text_area("Syllabus topics · one per line", placeholder="Functions\nClasses\nFile handling")
            minutes = st.number_input("Estimated minutes per topic", 5, 600, 60, step=5)
            start = st.time_input("Usual study start", value=time(18))
            daily = st.number_input("Daily free minutes", 5, 720, 60, step=5)
            st.caption("This creates one daily window. You can edit weekdays, add split windows, or take days off in Weekly plan. Existing availability is preserved.")
            if st.form_submit_button("Create my study map", type="primary"):
                quick_start(store, name, datetime.combine(exam_date, exam_time), target, names, minutes, start.strftime("%H:%M"), daily, marks)
                notify("Study map saved. Try a knowledge check, then preview your starting plan.")
        return

    items = recommendations(store)
    if not items:
        st.info("Add or update a future exam in Subjects to get current practice recommendations.")
        return
    st.subheader("What to work on next")
    st.caption("Recommendations use up to three recent topic results, newest first. Without results, subject marks are the starting point. Self-rated checks are learning signals, not predicted exam marks.")
    st.dataframe([{"Subject": item["topic"]["subject"], "Topic": item["topic"]["name"],
                   "Next practice": item["level"], "Why": item["reason"]} for item in items[:5]], hide_index=True, width="stretch")
    checked = sum(item["assessments"] > 0 for item in items)
    st.progress(checked / len(items), text=f"{checked}/{len(items)} upcoming topics have an assessment baseline")
    check_tab, plan_tab = st.tabs(["Knowledge check", "Starting plan"])
    with check_tab:
        topic = st.selectbox("Check a topic", [item["topic"] for item in items], format_func=lambda t: f"{t['subject']} / {t['name']}")
        cards = [card for card in store.cards() if card["topic_id"] == topic["id"]]
        prompt = cards[0]["question"] if cards else f"Explain {topic['name']} from memory. Give an example and describe the steps you would follow."
        st.write(prompt)
        with st.expander("Check your explanation against your material"):
            if cards:
                st.write(cards[0]["answer"])
                st.caption(cards[0]["source"] or "Your saved checking guide")
            else:
                st.write("Open your notes and check the definition, key steps, and example. Identify anything missing or incorrect.")
            st.caption("You rate your own recall. This check does not automatically grade your explanation.")
        with st.form(f"coach_check_{topic['id']}", clear_on_submit=True):
            explanation = st.text_area("Explain from memory", max_chars=5000)
            rating = st.select_slider("My recall after checking", options=list(range(6)), value=2,
                                      format_func=lambda r: ["0 · Could not recall", "1 · Fragments", "2 · Major gaps", "3 · Some gaps", "4 · Mostly correct", "5 · Correct with an example"][r])
            correction = st.text_area("Correction from my notes (optional)", max_chars=5000)
            st.caption("A rating of 0–2 with a correction of at least 20 characters also creates a review card. Your score informs future planning when you accept a new plan.")
            if st.form_submit_button("Save knowledge check", type="primary"):
                record_self_check(store, topic["id"], explanation, rating, correction)
                st.session_state.pop("coach_preview", None)
                notify("Knowledge check saved. Your practice recommendations are updated; preview a new plan when ready.")

    with plan_tab:
        st.write("Preview the next week using your saved availability, session lengths, breaks, and days off.")
        options = store.setting("plan_options", {"session": 25, "break": 5})
        windows = store.setting("availability", [{"day": day, "start": "18:00", "minutes": 60} for day in WEEKDAYS])
        days_off = [datetime.fromisoformat(day).date() for day in options.get("days_off", [])]
        focus, rest = options.get("session", 25), options.get("break", 5)
        fingerprint = hashlib.sha256(json.dumps([store.topics(), store.cards(), store.sessions(), windows, options], sort_keys=True).encode()).hexdigest()
        preview = st.session_state.get("coach_preview")
        if preview and (preview["fingerprint"] != fingerprint or datetime.fromisoformat(preview["created_at"]) + timedelta(minutes=5) < now()):
            st.session_state.pop("coach_preview", None)
            st.info("Your records changed or the preview expired. Preview the plan again before accepting.")
        st.caption(f"7 days · {focus}-minute focus blocks · {rest}-minute breaks. Adjust availability in Weekly plan. Saving replaces unfinished reservations and preserves finished work.")
        if st.button("Preview my starting plan"):
            plan = store.plan(weekly_slots(now().date(), 7, windows, days_off), focus, rest, save=False)
            st.session_state["coach_preview"] = {"plan": plan, "fingerprint": fingerprint, "created_at": now().isoformat()}
        if st.session_state.get("coach_preview"):
            show_plan(st.session_state["coach_preview"]["plan"])
            if st.button("Accept and save plan", type="primary"):
                # Recompute from current data and current time; never save an old
                # browser snapshot after another session updates study results.
                plan = store.plan(weekly_slots(now().date(), 7, windows, days_off), focus, rest, save=True)
                st.session_state.pop("coach_preview", None)
                notify(f"Plan saved: {len(plan.sessions)} sessions; {sum(plan.unscheduled.values())} minutes did not fit. See Weekly plan for your timetable.")
            st.caption("Accepting recalculates from the latest study records and current time.")


def show_plan(plan):
    st.subheader("Preview · nothing saved")
    if plan.sessions:
        st.dataframe([{"Subject": s.task.subject, "Topic": s.task.topic, "Start": s.start, "End": s.end, "Why": s.reason}
                      for s in plan.sessions], hide_index=True, width="stretch")
    else:
        st.info("No sessions fit the current windows and exam deadlines.")
    if plan.unscheduled:
        st.warning(f"{sum(plan.unscheduled.values())} minutes did not fit this planning window. Extend availability or adjust scope in Weekly plan.")
