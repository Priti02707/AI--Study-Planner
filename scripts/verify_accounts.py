"""Exercise live account registration and isolation through the public UI.

Creates two clearly labelled QA accounts with random, unprinted credentials.
Removes their test subjects and signs them out. The empty QA accounts remain;
no production environment secrets or pre-existing accounts are accessed.
"""
import secrets
import sys
from urllib.parse import urlsplit

from websockets.sync.client import connect

from verify_deployment import Dashboard


def change(dashboard, kind, label, value, field="string_value"):
    widget = dashboard.widget(kind, label)
    dashboard.rerun([(widget.id, field, value)])


def submit(dashboard, label, fields=(), areas=()):
    widgets = [(dashboard.widget("text_input", name).id, "string_value", value) for name, value in fields]
    widgets.extend((dashboard.widget("text_area", name).id, "string_value", value) for name, value in areas)
    widgets.append((dashboard.widget("button", label).id, "trigger_value", True))
    dashboard.rerun(widgets)


def register(dashboard, handle, password):
    change(dashboard, "radio", "Account", "Create account")
    submit(dashboard, "Create my account", [("Your name", "Deployment QA"), ("Choose a username", handle),
                                           ("Password", password), ("Confirm password", password),
                                           ("Your security question", "What is my QA recovery phrase?"),
                                           ("Security answer (12–128 characters)", secrets.token_urlsafe(24))])
    dashboard.widget("radio", "Workspace")


def sign_out(dashboard):
    submit(dashboard, "Sign out")
    dashboard.widget("text_input", "Username")


def sign_in(dashboard, handle, password):
    submit(dashboard, "Sign in", [("Username", handle), ("Password", password)])
    dashboard.widget("radio", "Workspace")


def subjects(dashboard):
    change(dashboard, "radio", "Workspace", "Subjects")
    return list(dashboard.widget("selectbox", "Edit subject").options)


def remove_subject(dashboard, name):
    change(dashboard, "selectbox", "Edit subject", name)
    change(dashboard, "checkbox", "Remove this subject, its topics, cards, and documents", True, "bool_value")
    submit(dashboard, "Remove subject")
    assert list(dashboard.widget("selectbox", "Edit subject").options) == ["Add a new subject"]


def exercise_coach(dashboard, suffix):
    name = f"QA coach {suffix}"
    change(dashboard, "radio", "Workspace", "Study coach")
    submit(dashboard, "Create my study map", [("First subject", name)],
           [("Syllabus topics · one per line", "QA Foundations\nQA Applications")])
    dashboard.widget("selectbox", "Check a topic")
    submit(dashboard, "Save knowledge check", areas=[("Explain from memory", "I remember the basic definition but need to revisit the worked example.")])
    submit(dashboard, "Preview my starting plan")
    submit(dashboard, "Accept and save plan")
    assert subjects(dashboard) == ["Add a new subject", name]
    remove_subject(dashboard, name)
    print("Guided setup, self-rated knowledge check, preview, and accepted plan: passed; coach test subject removed")


def main():
    url = sys.argv[1].rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Use an HTTPS production URL.")
    suffix = secrets.token_hex(8)
    first, second = f"qa_{suffix}_a", f"qa_{suffix}_b"
    password = secrets.token_urlsafe(24)
    first_subject, second_subject = f"QA private A {suffix}", f"QA private B {suffix}"
    with connect(f"wss://{parsed.netloc}/_stcore/stream", subprotocols=["streamlit"], origin=url,
                 open_timeout=30, max_size=20 * 1024 * 1024) as socket:
        dashboard = Dashboard(socket)
        dashboard.rerun()
        register(dashboard, first, password)
        print("First student registration: passed")
        if "--coach" in sys.argv[2:]:
            exercise_coach(dashboard, suffix)
        assert subjects(dashboard) == ["Add a new subject"]
        submit(dashboard, "Save subject", [("Subject name", first_subject)])
        assert first_subject in list(dashboard.widget("selectbox", "Edit subject").options)
        sign_out(dashboard)
        print("Sign-out returns to account sign-in: passed")
        register(dashboard, second, password)
        assert subjects(dashboard) == ["Add a new subject"]
        submit(dashboard, "Save subject", [("Subject name", second_subject)])
        assert first_subject not in list(dashboard.widget("selectbox", "Edit subject").options)
        sign_out(dashboard)
        sign_in(dashboard, first, password)
        assert subjects(dashboard) == ["Add a new subject", first_subject]
        remove_subject(dashboard, first_subject)
        sign_out(dashboard)
        sign_in(dashboard, second, password)
        assert subjects(dashboard) == ["Add a new subject", second_subject]
        remove_subject(dashboard, second_subject)
        sign_out(dashboard)
        print("Second student, isolated subjects, and sign-in persistence: passed")
        print("Test subjects removed; both QA accounts signed out. Existing user records were untouched.")


if __name__ == "__main__":
    main()
