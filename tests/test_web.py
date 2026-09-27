from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import soundfile as sf

from web_analysis import build_plot_data, TIME_BINS, FREQUENCY_BINS
from web_app import create_app
from audio_formats import SUPPORTED, find_ffmpeg


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data, sr=48000):
        path = self.folder / name
        sf.write(path, data, sr, subtype="PCM_24")
        return path

    def tone(self, frequency=3000, sr=48000, seconds=1):
        return .5 * np.sin(2 * np.pi * frequency * np.arange(int(sr * seconds)) / sr)

    def test_tone_peak_and_antiphase_stereo(self):
        tone = self.tone()
        d = build_plot_data(self.write("反相.flac", np.column_stack([tone, -tone])))
        spectrum = d["spectrum"]
        index = int(np.argmax(spectrum["relative_db"]))
        self.assertAlmostEqual(spectrum["frequency_khz"][index], 3, delta=.006)
        self.assertEqual(spectrum["relative_db"][index], 0)
        self.assertFalse(d["summary"]["silent"])
        self.assertAlmostEqual(d["summary"]["edge_99_hz"], 3000, delta=20)
        self.assertEqual(d["info"]["channels"], 2)

    def test_entire_track_includes_late_tone(self):
        data = np.concatenate([np.zeros(48000), self.tone(6000)])
        d = build_plot_data(self.write("late.wav", data))
        s = d["spectrogram"]
        heat = np.array(s["relative_db"], dtype=float)
        early = np.array(s["time_sec"]) < .7
        late = np.array(s["time_sec"]) > 1.3
        self.assertLess(np.nanmax(heat[:, early]), -100)
        self.assertGreater(np.nanmax(heat[:, late]), -1)
        self.assertGreater(max(s["time_sec"]), 1.8)

    def test_silence_and_short_audio(self):
        d = build_plot_data(self.write("silent.flac", np.zeros(48000)))
        self.assertTrue(d["summary"]["silent"])
        self.assertEqual(set(d["spectrum"]["relative_db"]), {-120})
        self.assertEqual(d["summary"]["edge_99_hz"], 0)
        d = build_plot_data(self.write("short.wav", self.tone(seconds=.001)))
        self.assertEqual(len(d["spectrogram"]["time_sec"]), 1)
        with self.assertRaisesRegex(ValueError, "过短"):
            build_plot_data(self.write("tiny.wav", np.zeros(12)))

    def test_bounded_payload_and_distinct_nyquist(self):
        for sr in [8000, 44100, 96000]:
            d = build_plot_data(self.write(f"{sr}.flac", self.tone(1000, sr, 2), sr))
            s = d["spectrogram"]
            self.assertLessEqual(len(s["time_sec"]), TIME_BINS)
            self.assertLessEqual(len(s["frequency_khz"]), FREQUENCY_BINS)
            self.assertEqual(d["spectrum"]["frequency_khz"][-1], sr / 2000)
            self.assertEqual(len(s["relative_db"]), len(s["frequency_khz"]))
            self.assertTrue(all(len(row) == len(s["time_sec"]) for row in s["relative_db"]))

    def test_long_track_reduction_covers_last_window(self):
        tone = self.tone(1000, 48000, 32)
        tone[-48000:] = self.tone(9000)
        d = build_plot_data(self.write("long.flac", tone))
        s = d["spectrogram"]
        self.assertEqual(len(s["time_sec"]), TIME_BINS)
        self.assertEqual(len(s["frequency_khz"]), FREQUENCY_BINS)
        self.assertGreater(s["time_sec"][-1], 31.9)
        row = int(np.argmin(np.abs(np.array(s["frequency_khz"]) - 9)))
        self.assertGreater(s["relative_db"][row][-1], -3)

    def test_scan_api_errors_and_cache_invalidation(self):
        path = self.write("曲目.flac", self.tone(3000))
        (self.folder / "broken.flac").write_text("not audio")
        (self.folder / "ignore.txt").write_text("not audio")
        with TestClient(create_app(self.folder)) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/static/app.js").status_code, 200)
            self.assertEqual(client.get("/vendor/plotly.min.js").status_code, 200)
            self.assertEqual(client.get("/api/tracks/unknown").status_code, 404)
            self.assertEqual(client.post("/api/scan", json={"folder": str(self.folder / "missing")}).status_code, 400)
            result = client.post("/api/scan", json={"folder": str(self.folder)}).json()
            self.assertEqual(len(result["tracks"]), 2)
            ids = {t["name"]: t["id"] for t in result["tracks"]}
            url = f"/api/tracks/{ids[path.name]}"
            d = client.get(url).json()
            self.assertEqual(client.get(url).json(), d)
            sf.write(path, self.tone(6000, seconds=2), 48000, subtype="PCM_24")
            updated = client.get(url).json()
            self.assertEqual(updated["info"]["duration_sec"], 2)
            self.assertNotEqual(d["spectrum"], updated["spectrum"])
            self.assertEqual(client.get(f"/api/tracks/{ids['broken.flac']}").status_code, 422)
            self.assertEqual(client.post("/api/scan", json={"folder": str(self.folder)}, headers={"Origin": "https://example.com"}).status_code, 403)

    def test_scan_common_extensions_and_nested_names(self):
        album = self.folder / "专辑 [音频]"
        album.mkdir()
        for ext in SUPPORTED:
            (album / f"track{ext.upper()}").touch()
        (album / "cover.jpg").touch()
        with TestClient(create_app(self.folder)) as client:
            config = client.get("/api/config").json()
            self.assertEqual(set(config["supported_extensions"]), SUPPORTED)
            tracks = client.post("/api/scan", json={"folder": str(self.folder)}).json()["tracks"]
            self.assertEqual(len(tracks), len(SUPPORTED))
            self.assertTrue(all(t["relative_path"].startswith(album.name) for t in tracks))

    def test_missing_ffmpeg_message(self):
        path = self.folder / "test.m4a"
        path.write_bytes(b"invalid")
        with patch("audio_formats.find_ffmpeg", return_value=None):
            with self.assertRaisesRegex(ValueError, "需要 FFmpeg"):
                build_plot_data(path)

    @unittest.skipUnless(find_ffmpeg(), "FFmpeg is required for codec integration tests")
    def test_real_common_audio_codecs(self):
        source = self.write("源音频.wav", np.column_stack([self.tone(), self.tone()]))
        fixtures = [("MP3", "libmp3lame", None), ("m4a", "aac", None),
                    ("aac", "aac", None), ("ogg", "libvorbis", None),
                    ("opus", "libopus", None), ("wma", "wmav2", None),
                    ("wv", "wavpack", 24), ("alac.m4a", "alac", 24)]
        for extension, codec, bits in fixtures:
            with self.subTest(codec=codec):
                target = self.folder / f"测试 [{codec}].{extension}"
                subprocess.run([find_ffmpeg(), "-nostdin", "-v", "error", "-i", str(source),
                                "-c:a", codec, *(["-bits_per_raw_sample", str(bits)] if bits else []),
                                str(target)], check=True, capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                data = build_plot_data(target)
                self.assertEqual(data["info"]["sample_rate"], 48000)
                self.assertEqual(data["info"]["channels"], 2)
                self.assertAlmostEqual(data["info"]["duration_sec"], 1, delta=.15)
                self.assertEqual(data["info"]["bit_depth"], bits)
                peak = int(np.argmax(data["spectrum"]["relative_db"]))
                self.assertAlmostEqual(data["spectrum"]["frequency_khz"][peak], 3, delta=.02)
                if codec not in {"alac", "wavpack"}:
                    self.assertEqual(data["forensics"]["status"], "lossy")
                    self.assertIsNone(data["forensics"]["score"])
                if codec == "alac":
                    self.assertEqual(data["info"]["subtype"], "ALAC")
                    self.assertEqual(data["info"]["decoder"], "ffmpeg")


if __name__ == "__main__":
    unittest.main()
