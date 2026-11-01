"""Publish the pinned Streamlit browser files separately from the Python function.

Run this before Vercel CLI deployment. Only public framework assets go into
public/; study data and server configuration stay out.
"""
from importlib.metadata import version as installed_version
from pathlib import Path
import re
import shutil
import streamlit


def prepare(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "static", destination / "static", dirs_exist_ok=True)
    for name in ("favicon.png", "manifest.json"):
        shutil.copy2(source / name, destination / name)
    html = (source / "index.html").read_text()
    html = html.replace("<title>Streamlit</title>", "<title>AI Study Planner</title>")
    html = html.replace('<div id="root"></div>', '''<div id="root">
      <main role="status" style="max-width:36rem;margin:18vh auto;padding:2rem;font:18px/1.6 system-ui,sans-serif;color:#243b33">
        <h1 style="font-size:2rem">🌱 AI Study Planner</h1>
        <p>Opening your private study workspace…</p>
      </main>
    </div>''')
    (destination / "index.html").write_text(html)


def main():
    root = Path(__file__).resolve().parents[1]
    version = re.search(r"^streamlit==([^\s]+)$", (root / "requirements.txt").read_text(), re.M).group(1)
    if installed_version("streamlit") != version:
        raise RuntimeError(f"Install requirements.txt first: browser assets must match Streamlit {version}.")
    prepare(Path(streamlit.__file__).parent / "static", root / "public")
    print(f"Prepared Streamlit {version} browser assets for CDN delivery.")


if __name__ == "__main__":
    main()
