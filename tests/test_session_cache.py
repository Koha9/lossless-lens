import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import soundfile as sf

from web_app import create_app


class SessionCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.music = self.root / "music"
        self.music.mkdir()
        self.work = self.root / "work"
        self.work.mkdir()

    def app(self):
        with patch("web_app.Path.cwd", return_value=self.work):
            return create_app(self.music)

    def write(self, name="tone.wav", frequency=3000):
        path = self.music / name
        sf.write(path, .5 * np.sin(2 * np.pi * frequency * np.arange(48000) / 48000),
                 48000, subtype="PCM_24")
        return path

    def scan(self, client):
        return client.post("/api/scan", json={"folder": str(self.music)}).json()["tracks"]

    def test_summary_saves_full_data_rescan_reuses_and_shutdown_cleans(self):
        self.write()
        app = self.app()
        with TestClient(app) as client, patch.object(app.state.analysis_pool, "submit", wraps=app.state.analysis_pool.submit) as build:
            url = f"/api/tracks/{self.scan(client)[0]['id']}"
            summary = client.get(url + "/analysis").json()
            directory = app.state.session_cache.directory
            self.assertEqual(directory.parent, self.work)
            record = json.loads(next(directory.glob("*.json")).read_text(encoding="utf-8"))
            self.assertIn("spectrogram", record["result"])
            self.assertIn("spectrum", record["result"])
            self.assertNotIn("spectrum", summary)
            self.scan(client)  # clear memory, force a disk hit
            self.assertEqual(client.get(url).json(), record["result"])
            self.assertEqual(build.call_count, 1)
            self.assertEqual(build.call_args.kwargs["temp_dir"], directory)
            self.assertEqual(list(self.music.iterdir()), [self.music / "tone.wav"])
        self.assertFalse(directory.exists())
        self.assertEqual(list(self.work.iterdir()), [])

    def test_lru_eviction_keeps_disk_data(self):
        for i in range(13):
            self.write(f"{i:02}.wav")
        app = self.app()
        with TestClient(app) as client, patch.object(app.state.analysis_pool, "submit", wraps=app.state.analysis_pool.submit) as build:
            tracks = self.scan(client)
            for track in tracks:
                self.assertEqual(client.get(f"/api/tracks/{track['id']}/analysis").status_code, 200)
            self.assertEqual(client.get(f"/api/tracks/{tracks[0]['id']}").status_code, 200)
            self.assertEqual(build.call_count, 13)

    def test_corrupt_cache_and_changed_source_rebuild(self):
        path = self.write()
        app = self.app()
        with TestClient(app) as client, patch.object(app.state.analysis_pool, "submit", wraps=app.state.analysis_pool.submit) as build:
            url = f"/api/tracks/{self.scan(client)[0]['id']}"
            original = client.get(url).json()
            cache_file = next(app.state.session_cache.directory.glob("*.json"))
            cache_file.write_text("broken", encoding="utf-8")
            self.scan(client)
            self.assertEqual(client.get(url).json(), original)
            old_stat = path.stat()
            self.write(frequency=6000)
            os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1000000000))
            self.scan(client)
            self.assertNotEqual(client.get(url).json()["spectrum"], original["spectrum"])
            self.assertEqual(build.call_count, 3)
            self.assertEqual(len(list(app.state.session_cache.directory.glob("*.json"))), 1)

    def test_separate_sessions_and_cleanup_on_exception(self):
        first, second = self.app(), self.app()
        with TestClient(first), TestClient(second):
            one, two = first.state.session_cache.directory, second.state.session_cache.directory
            self.assertNotEqual(one, two)
        self.assertFalse(one.exists())
        self.assertFalse(two.exists())
        with self.assertRaisesRegex(RuntimeError, "test exit"):
            with TestClient(first):
                directory = first.state.session_cache.directory
                raise RuntimeError("test exit")
        self.assertFalse(directory.exists())


if __name__ == "__main__":
    unittest.main()
