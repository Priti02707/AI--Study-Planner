"""Verify the Vercel ASGI entrypoint's HTTP and real Streamlit WebSocket flow."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect


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
                with connect(f"ws://127.0.0.1:{port}/_stcore/stream", subprotocols=["streamlit"],
                             origin=f"http://127.0.0.1:{port}", open_timeout=5) as socket_client:
                    message = BackMsg()
                    message.rerun_script.query_string = ""
                    socket_client.send(message.SerializeToString())
                    rendered, completed = False, False
                    for _ in range(100):
                        message = ForwardMsg()
                        message.ParseFromString(socket_client.recv(timeout=10))
                        if message.HasField("delta"):
                            rendered = True
                            element = message.delta.new_element
                            if element.HasField("exception"):
                                raise RuntimeError(element.exception.message)
                        if message.HasField("script_finished"):
                            completed = True
                            break
                    assert rendered and completed, "Dashboard did not render over WebSocket."
                print("ASGI health: 200; HTML: 200; WebSocket dashboard render: passed")
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
