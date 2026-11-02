from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import soundfile as sf

from web_analysis import build_plot_data
from web_app import create_app, MAX_ANALYSIS_WORKERS


class AnalysisWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        audio = .4 * np.sin(2 * np.pi * 3000 * np.arange(48000) / 48000)
        for name in ("one.flac", "two.flac", "three.flac"):
            sf.write(self.folder / name, audio, 48000, subtype="PCM_24")
        self.app = create_app(self.folder)

    def urls(self, client):
        tracks = client.post("/api/scan", json={"folder": str(self.folder)}).json()["tracks"]
        return [f"/api/tracks/{track['id']}" for track in tracks]

    def test_settings_validation_and_real_process_results(self):
        with TestClient(self.app) as client:
            config = client.get("/api/config").json()
            self.assertGreaterEqual(config["analysis_workers"], 1)
            self.assertEqual(config["max_analysis_workers"], MAX_ANALYSIS_WORKERS)
            for value in (0, MAX_ANALYSIS_WORKERS + 1, 1.5, "2", True):
                self.assertEqual(client.put("/api/settings", json={"analysis_workers": value}).status_code, 422)
            urls = self.urls(client)
            for workers, selected in ((1, urls[:1]), (2, urls[1:])):
                self.assertEqual(client.put("/api/settings", json={"analysis_workers": workers}).json(),
                                 {"analysis_workers": workers})
                with ThreadPoolExecutor(max_workers=2) as requests:
                    responses = list(requests.map(client.get, selected))
                for response in responses:
                    self.assertEqual(response.status_code, 200)
                    actual = response.json()
                    self.assertEqual(actual, {"id": actual["id"], **build_plot_data(self.folder / actual["name"])})
            self.assertEqual(client.get("/api/config").json()["analysis_workers"], 2)

    def test_distinct_tracks_overlap_and_settings_wait_until_idle(self):
        release = threading.Event()
        both_started = threading.Event()
        counter_lock = threading.Lock()
        started = 0

        def controlled_build(*args, **kwargs):
            nonlocal started
            with counter_lock:
                started += 1
                if started == 2:
                    both_started.set()
            if not release.wait(10):
                raise RuntimeError("test worker timed out")
            return build_plot_data(*args, **kwargs)

        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=2) as compute, ThreadPoolExecutor(max_workers=2) as requests:
            client.put("/api/settings", json={"analysis_workers": 2})
            urls = self.urls(client)
            with patch.object(self.app.state.analysis_pool, "submit",
                              side_effect=lambda fn, *a, **kw: compute.submit(controlled_build, *a, **kw)):
                pending = [requests.submit(client.get, url + "/analysis") for url in urls[:2]]
                try:
                    self.assertTrue(both_started.wait(5), "different tracks must not share a global analysis lock")
                    self.assertEqual(client.put("/api/settings", json={"analysis_workers": 1}).status_code, 409)
                    self.assertEqual(client.post("/api/tracks/transfer", json={
                        "track_ids": [urls[0].rsplit("/", 1)[-1]],
                        "target_folder": str(self.folder / "target"), "operation": "copy",
                    }).status_code, 409)
                    self.assertFalse((self.folder / "target").exists())
                finally:
                    release.set()
                self.assertTrue(all(job.result().status_code == 200 for job in pending))
            self.assertEqual(client.put("/api/settings", json={"analysis_workers": 1}).status_code, 200)

    def test_same_track_shares_work_and_failure_can_retry(self):
        release = threading.Event()
        started = threading.Event()
        joined = threading.Event()
        # Observe the duplicate waiting on the shared Future, without sleeps.
        from concurrent.futures import Future

        class ObservedFuture(Future):
            def result(self, timeout=None):
                joined.set()
                return super().result(timeout)

        def fail(*args, **kwargs):
            started.set()
            if not release.wait(10):
                raise RuntimeError("test worker timed out")
            raise ValueError("decode failed")

        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=1) as compute, ThreadPoolExecutor(max_workers=2) as requests:
            url = self.urls(client)[0]
            with patch("web_app.Future", ObservedFuture), patch.object(self.app.state.analysis_pool, "submit",
                    side_effect=lambda fn, *a, **kw: compute.submit(fail, *a, **kw)) as submit:
                first = requests.submit(client.get, url)
                try:
                    self.assertTrue(started.wait(5))
                    second = requests.submit(client.get, url + "/analysis")
                    self.assertTrue(joined.wait(5))
                finally:
                    release.set()
                self.assertEqual(first.result().status_code, 422)
                self.assertEqual(second.result().status_code, 422)
                self.assertEqual(submit.call_count, 1)
            # The failed job must not remain in the deduplication map.
            self.assertEqual(client.get(url).status_code, 200)


if __name__ == "__main__":
    unittest.main()
