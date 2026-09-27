from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import soundfile as sf

from web_analysis import build_plot_data
from web_app import create_app
from web_forensics import PaddingEvidence, assess_features


class ForensicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.rng = np.random.default_rng(72)

    def write(self, name, data, sr=48000):
        path = self.folder / name
        sf.write(path, data, sr, subtype="PCM_24")
        return path

    def noise(self):
        return self.rng.uniform(-.5, .5, 48000)

    def test_broadband_and_real_16_to_24_padding(self):
        signal = self.noise()
        clean = build_plot_data(self.write("broad.flac", signal))["forensics"]
        padded = build_plot_data(self.write("padded.flac", np.rint(signal * 32768) / 32768))["forensics"]
        self.assertEqual(clean["status"], "clear")
        self.assertEqual(clean["score"], 0)
        self.assertEqual(padded["status"], "suspicious")
        self.assertEqual(padded["score"], 95)
        self.assertEqual(padded["padding_16bit_fraction"], 1)

    def test_real_lowpass_and_broadband_order(self):
        signal = self.noise()
        spectrum = np.fft.rfft(signal)
        spectrum[np.fft.rfftfreq(len(signal), 1 / 48000) > 16000] = 0
        filtered = np.fft.irfft(spectrum, n=len(signal))
        result = build_plot_data(self.write("lowpass.flac", filtered))["forensics"]
        self.assertEqual(result["status"], "suspicious")
        self.assertGreaterEqual(result["score"], 35)
        self.assertLess(result["score"], 95)

    def test_silence_short_audio_and_lossy_are_not_green(self):
        for name, signal in [("silent.flac", np.zeros(48000)), ("short.flac", self.noise()[:100])]:
            result = build_plot_data(self.write(name, signal))["forensics"]
            self.assertEqual(result["status"], "inconclusive")
            self.assertIsNone(result["score"])
        result = assess_features({"subtype": "MPEG_LAYER_III"}, {})
        self.assertEqual(result["status"], "lossy")
        self.assertIsNone(result["score"])

    def test_padding_counts_all_channels_and_ignores_silence(self):
        evidence = PaddingEvidence(24)
        evidence.add(np.zeros((10000, 2)))
        self.assertIsNone(evidence.fraction)
        signal = self.noise()
        evidence.add(np.column_stack([np.rint(signal * 32768) / 32768, signal]))
        self.assertAlmostEqual(evidence.fraction, .5, delta=.01)
        aligned = PaddingEvidence(32)
        aligned.add(np.rint(signal * 32768) / 32768)
        self.assertEqual(aligned.fraction, 1)

    def test_score_increases_with_cutoff_strength(self):
        info = {"subtype": "PCM_24", "duration_sec": 1, "sample_rate": 48000}
        summary = {"silent": False, "cutoff_hz": 16000, "cutoff_confidence": .4, "edge_99_hz": 16000}
        weak = assess_features(info, summary)
        strong = assess_features(info, {**summary, "cutoff_confidence": 1})
        self.assertLess(weak["score"], strong["score"])
        self.assertEqual(strong["score_kind"], "heuristic_feature_strength")

    def test_summary_api_cache_file_change_and_failure_isolation(self):
        path = self.write("valid.flac", self.noise())
        (self.folder / "broken.flac").write_text("bad")
        with TestClient(create_app(self.folder)) as client, patch("web_app.build_plot_data", wraps=build_plot_data) as build:
            entries = client.post("/api/scan", json={"folder": str(self.folder)}).json()["tracks"]
            ids = {t["name"]: t["id"] for t in entries}
            url = f"/api/tracks/{ids['valid.flac']}/analysis"
            first = client.get(url).json()
            self.assertNotIn("spectrogram", first)
            self.assertNotIn("spectrum", first)
            self.assertEqual(first["forensics"]["status"], "clear")
            self.assertEqual(client.get(url).json(), first)
            self.assertEqual(build.call_count, 1)
            self.assertEqual(client.get(f"/api/tracks/{ids['broken.flac']}/analysis").status_code, 422)
            self.assertEqual(client.get(url).status_code, 200)
            noise = self.noise()
            self.write(path.name, np.rint(np.tile(noise, 2) * 32768) / 32768)
            self.assertEqual(client.get(url).json()["forensics"]["status"], "suspicious")
            plot = client.get(f"/api/tracks/{ids['valid.flac']}").json()
            self.assertIn("spectrogram", plot)
            self.assertEqual(plot["forensics"], client.get(url).json()["forensics"])
            calls = build.call_count
            client.post("/api/scan", json={"folder": str(self.folder)})
            self.assertEqual(client.get(url).status_code, 200)
            self.assertEqual(build.call_count, calls)
            self.assertEqual(client.get("/api/tracks/missing/analysis").status_code, 404)

    def test_file_modified_during_analysis_is_not_cached(self):
        path = self.write("changing.flac", self.noise())
        def changed(path, **kwargs):
            result = build_plot_data(path, **kwargs)
            self.write(path.name, np.zeros(96000))
            return result
        with TestClient(create_app(self.folder)) as client:
            track = client.post("/api/scan", json={"folder": str(self.folder)}).json()["tracks"][0]
            url = f"/api/tracks/{track['id']}/analysis"
            with patch("web_app.build_plot_data", side_effect=changed):
                self.assertEqual(client.get(url).status_code, 422)
            self.assertEqual(client.get(url).json()["forensics"]["status"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
