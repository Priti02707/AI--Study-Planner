"""Browser persistence for hosted sign-in and the disposable test workspace."""
import streamlit as st

SESSION_COOKIE = "study_planner_session"

session_cookie = st.components.v2.component(
    "planner_session_cookie",
    html="<span aria-live='polite'></span>",
    js="""
export default async function({data, parentElement}) {
    try {
        const response = await fetch("/api/session", {
            method: "POST",
            headers: {"Content-Type": "text/plain"},
            body: data,
            credentials: "same-origin"
        });
        if (!response.ok) throw new Error();
    } catch {
        parentElement.querySelector("span").textContent =
            "Could not save sign-in across browser reloads.";
    }
}
""",
)

load_workspace = st.components.v2.component(
    "planner_load_test_workspace",
    html="<span aria-live='polite'></span>",
    js="""
export default function({setStateValue, parentElement}) {
    try {
        setStateValue("snapshot", localStorage.getItem("study-planner-test-v1") ?? "");
    } catch {
        parentElement.querySelector("span").textContent =
            "Enable site storage to open the test workspace.";
    }
}
""",
)

save_workspace = st.components.v2.component(
    "planner_save_test_workspace",
    html="<span aria-live='polite'></span>",
    js="""
export default function({data, parentElement}) {
    const status = parentElement.querySelector("span");
    try {
        localStorage.setItem("study-planner-test-v1", data);
        status.textContent = "Test data saved in this browser profile.";
    } catch {
        status.textContent = "Browser storage is unavailable or full. Export your test data before leaving.";
    }
}
""",
)
