"""Checks for the public browser bundle served independently of the ASGI app."""
import re
import tempfile
import unittest
from pathlib import Path

import streamlit

from scripts.prepare_static import prepare


class StaticBundleTests(unittest.TestCase):
    def test_browser_entrypoint_references_existing_assets(self):
        source = Path(streamlit.__file__).parent / "static"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            prepare(source, destination)
            html = (destination / "index.html").read_text()
            self.assertIn("<title>AI Study Planner</title>", html)
            self.assertIn('role="status"', html)
            references = re.findall(r'(?:href|src)="\./([^"]+)"', html)
            self.assertGreater(len(references), 0)
            for reference in references:
                self.assertTrue((destination / reference).is_file(), reference)
            self.assertEqual(set(p.name for p in destination.iterdir()),
                             {"index.html", "static", "favicon.png", "manifest.json"})

    def test_export_does_not_copy_server_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            (source / "static").mkdir(parents=True)
            (source / "static" / "app.hash.js").write_text("browser code")
            for name in ["index.html", "favicon.png", "manifest.json", ".env.local", "app.py"]:
                (source / name).write_text(name)
            destination = Path(directory) / "public"
            prepare(source, destination)
            self.assertFalse((destination / ".env.local").exists())
            self.assertFalse((destination / "app.py").exists())
            self.assertEqual((destination / "static" / "app.hash.js").read_text(), "browser code")


if __name__ == "__main__":
    unittest.main()
