"""Verify the Vercel ASGI entrypoint's HTTP and real Streamlit WebSocket flow."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

from planner.accounts import Accounts
from pathlib import Path

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect


def render(socket_client, query="", state=None, components=None):
    message = BackMsg()
    message.rerun_script.query_string = query
    if state:
        widget = message.rerun_script.widget_states.widgets.add()
        widget.id, widget.json_value = state
    socket_client.send(message.SerializeToString())
    labels = []
    for _ in range(100):
        message = ForwardMsg()
        message.ParseFromString(socket_client.recv(timeout=10))
        if message.HasField("delta"):
            element = message.delta.new_element
            if element.HasField("exception"):
                raise RuntimeError(element.exception.message)
            if components is not None and element.HasField("bidi_component"):
                components.append(element.bidi_component)
            if element.HasField("radio"):
                labels.append(element.radio.label)
            if element.HasField("alert"):
                labels.append(element.alert.body)
            if element.HasField("markdown"):
                labels.append(element.markdown.body)
        if message.HasField("script_finished"):
            return labels
    raise RuntimeError("Dashboard did not finish rendering.")


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = dict(os.environ, STUDY_PLANNER_DB=str(Path(directory)/"asgi.sqlite3"),
                   STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
        for key in ["VERCEL", "DATABASE_URL", "STUDY_PLANNER_PASSWORD"]:
            env.pop(key, None)
        with (Path(directory)/"server.log").open("w+") as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        output.seek(0)
                        raise RuntimeError(output.read())
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                            assert response.status == 200
                            assert json.load(response)["status"] == "ok"
                        break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("ASGI server did not start.")
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                    assert response.status == 200
                origin = f"http://127.0.0.1:{port}"
                with urllib.request.urlopen(f"{origin}/test", timeout=2) as response:
                    assert response.geturl() == f"{origin}/?workspace=test"
                accounts = Accounts(Path(directory) / "asgi.sqlite3")
                accounts.register("Smoke Tester", "smoke_tester", "smoke-password-1234")
                token = accounts.sign_in("smoke_tester", "smoke-password-1234")
                request = urllib.request.Request(
                    f"{origin}/api/session", data=token.encode(), headers={"Sec-Fetch-Site": "same-origin"}
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    assert response.status == 204
                    cookie = response.headers["Set-Cookie"]
                    assert "study_planner_session=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
                ws_url = f"ws://127.0.0.1:{port}/_stcore/stream"
                with connect(ws_url, subprotocols=["streamlit"], origin=origin, open_timeout=5) as client:
                    assert "Account" in render(client)
                with connect(ws_url, subprotocols=["streamlit"], origin=origin, open_timeout=5) as client:
                    components = []
                    assert any("Loading your browser" in label for label in render(client, "workspace=test", components=components))
                    load_id = components[0].id
                    components.clear()
                    assert "Workspace" in render(client, "workspace=test", (load_id, '{"snapshot":""}'), components)
                    assert any("format_version" in component.json for component in components)
                with connect(ws_url, subprotocols=["streamlit"], origin=origin, open_timeout=5,
                             additional_headers={"Cookie": cookie.split(";", 1)[0]}) as client:
                    assert "Workspace" in render(client)
                accounts.sign_out(token)
                try:
                    urllib.request.urlopen(request, timeout=2)
                except urllib.error.HTTPError as exc:
                    assert exc.code == 401
                else:
                    raise AssertionError("A revoked token was accepted.")
                print("ASGI health, /test route, WebSocket render, persistent cookie reconnect, and revocation: passed")
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
