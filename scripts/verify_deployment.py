"""Verify live HTTP, database, private sign-in, and dashboard navigation.

Reads the workspace password from the local ignored .env.local file. It never
prints credentials or changes study data. Run with the production URL argument.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect


class Dashboard:
    def __init__(self, socket):
        self.socket = socket
        self.elements = []
        self.page_hash = ""

    def rerun(self, widgets=()):
        started = time.monotonic()
        message = BackMsg()
        state = message.rerun_script
        state.page_script_hash = self.page_hash
        for widget_id, field, value in widgets:
            widget = state.widget_states.widgets.add(id=widget_id)
            setattr(widget, field, value)
        self.socket.send(message.SerializeToString())
        self.elements = []
        deadline = time.monotonic() + 90
        for _ in range(500):
            if time.monotonic() > deadline:
                raise TimeoutError("The dashboard did not finish rendering within 90 seconds.")
            message = ForwardMsg()
            message.ParseFromString(self.socket.recv(timeout=min(45, max(1, deadline-time.monotonic()))))
            if message.HasField("new_session"):
                self.page_hash = message.new_session.page_script_hash
            if message.HasField("delta"):
                element = message.delta.new_element
                if element.HasField("exception"):
                    raise RuntimeError(element.exception.message)
                self.elements.append(element)
            if message.HasField("script_finished"):
                if message.script_finished == ForwardMsg.FINISHED_WITH_COMPILE_ERROR:
                    raise RuntimeError("Deployment script could not compile.")
                if message.script_finished in (ForwardMsg.FINISHED_SUCCESSFULLY,
                                                ForwardMsg.FINISHED_FRAGMENT_RUN_SUCCESSFULLY):
                    self.last_render_seconds = time.monotonic() - started
                    return self.last_render_seconds
                self.elements = []
        raise RuntimeError("Dashboard did not finish rendering.")

    def widget(self, kind, label):
        return next(getattr(e, kind) for e in self.elements
                    if e.HasField(kind) and getattr(e, kind).label == label)


def main():
    url = sys.argv[1].rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Use an HTTPS production URL.")
    for path in ["/", "/api/health", "/_stcore/health"]:
        with urllib.request.urlopen(url + path, timeout=45) as response:
            body = response.read()
            assert response.status == 200
            if path == "/api/health":
                assert json.loads(body)["status"] == "ok"
        print(f"HTTP {path}: passed")
    root = Path(__file__).resolve().parents[1]
    password = next(json.loads(line.split("=", 1)[1]) for line in (root/".env.local").read_text().splitlines()
                    if line.startswith("STUDY_PLANNER_PASSWORD="))
    with connect(f"wss://{parsed.netloc}/_stcore/stream", subprotocols=["streamlit"],
                 origin=url, open_timeout=30, max_size=20*1024*1024) as socket:
        dashboard = Dashboard(socket)
        dashboard.rerun()
        mode = dashboard.widget("radio", "Account")
        assert "Create account" in mode.options and "Sign in" in mode.options
        print("Registration and sign-in entry screen: passed")
        dashboard.rerun([(mode.id, "string_value", "Existing workspace")])
        password_field = dashboard.widget("text_input", "Workspace password")
        submit = dashboard.widget("button", "Open my planner")
        print("Private workspace gate: passed")
        dashboard.rerun([(password_field.id, "string_value", password),
                         (submit.id, "trigger_value", True)])
        workspace = dashboard.widget("radio", "Workspace")
        print(f"Authenticated dashboard with hosted storage: passed ({dashboard.last_render_seconds:.2f}s)")
        for page in ["Subjects", "Weekly plan", "Practice", "Notes & AI", "Progress", "Today"]:
            dashboard.rerun([(workspace.id, "string_value", page)])
            workspace = dashboard.widget("radio", "Workspace")
            print(f"Dashboard {page}: passed ({dashboard.last_render_seconds:.2f}s)")
    print("Production verification completed without changing study records.")


if __name__ == "__main__":
    main()
