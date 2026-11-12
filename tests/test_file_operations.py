from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import soundfile as sf

from file_operations import plan_transfers, execute_transfers, plan_folders, execute_folders
from web_app import create_app


class FileOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.music = self.root / "aran"
        self.sources = [self.music / "A/B/1.flac", self.music / "A/C/2.flac"]
        for index, source in enumerate(self.sources):
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(f"audio-{index}".encode())

    def tracks(self):
        return [(str(index), source, (source.stat().st_size, source.stat().st_mtime_ns))
                for index, source in enumerate(self.sources)]

    def test_copy_preserves_relative_tree_or_flattens_exactly(self):
        for keep in (True, False):
            target, plans = plan_transfers(self.tracks(), self.music, str(self.root / str(keep)), keep)
            results = execute_transfers(plans, "copy")
            self.assertEqual([item["status"] for item in results], ["copied", "copied"])
            for source in self.sources:
                destination = target / (source.relative_to(self.music) if keep else source.name)
                self.assertEqual(destination.read_bytes(), source.read_bytes())
                self.assertEqual(destination.stat().st_mtime_ns, source.stat().st_mtime_ns)
            self.assertFalse((target / "aran").exists())

    def test_move_removes_only_successfully_copied_sources(self):
        cover = self.music / "A/B/cover.jpg"
        cover.write_bytes(b"cover")
        target, plans = plan_transfers(self.tracks(), self.music, str(self.root / "target"), True)
        self.assertEqual([item["status"] for item in execute_transfers(plans, "move")], ["moved", "moved"])
        self.assertFalse(any(source.exists() for source in self.sources))
        self.assertEqual((target / "A/B/1.flac").read_bytes(), b"audio-0")
        self.assertTrue(cover.exists())

    def test_preflight_rejects_existing_and_duplicate_flat_targets(self):
        target = self.root / "target"
        target.mkdir()
        (target / "2.flac").write_bytes(b"keep me")
        with self.assertRaises(FileExistsError):
            plan_transfers(self.tracks(), self.music, str(target), False)
        self.assertFalse((target / "1.flac").exists())
        self.assertEqual((target / "2.flac").read_bytes(), b"keep me")
        duplicate = self.music / "D/1.flac"
        duplicate.parent.mkdir()
        duplicate.write_bytes(b"duplicate")
        self.sources.append(duplicate)
        with self.assertRaises(FileExistsError):
            plan_transfers(self.tracks(), self.music, str(self.root / "new-target"), False)
        self.assertFalse((self.root / "new-target").exists())
        self.assertTrue(all(source.exists() for source in self.sources))

    def test_partial_copy_is_cleaned_and_later_tracks_continue(self):
        import shutil
        copy = shutil.copyfileobj
        def fail_first(source, destination, **kwargs):
            if Path(source.name) == self.sources[0]:
                destination.write(b"partial")
                raise OSError("disk write failed")
            return copy(source, destination, **kwargs)
        target, plans = plan_transfers(self.tracks(), self.music, str(self.root / "target"), False)
        with patch("file_operations.shutil.copyfileobj", side_effect=fail_first):
            results = execute_transfers(plans, "move")
        self.assertEqual([item["status"] for item in results], ["error", "moved"])
        self.assertTrue(self.sources[0].exists())
        self.assertFalse((target / "1.flac").exists())
        self.assertTrue((target / "2.flac").exists())

    def test_failed_source_removal_reports_complete_copy_separately(self):
        unlink = Path.unlink
        def deny_first(source, *args, **kwargs):
            if source == self.sources[0]:
                raise PermissionError("source locked")
            return unlink(source, *args, **kwargs)
        target, plans = plan_transfers(self.tracks(), self.music, str(self.root / "target"), False)
        with patch.object(Path, "unlink", deny_first):
            results = execute_transfers(plans, "move")
        self.assertEqual([item["status"] for item in results], ["copied_not_removed", "moved"])
        self.assertEqual((target / "1.flac").read_bytes(), self.sources[0].read_bytes())
        self.assertIn("source locked", results[0]["error"])

    def test_changed_source_during_copy_is_kept(self):
        import shutil
        copy = shutil.copyfileobj
        def change_source(source, destination, **kwargs):
            copy(source, destination, **kwargs)
            self.sources[0].write_bytes(b"changed audio content")
        target, plans = plan_transfers(self.tracks()[:1], self.music, str(self.root / "target"), False)
        with patch("file_operations.shutil.copyfileobj", side_effect=change_source):
            result = execute_transfers(plans, "move")[0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.sources[0].read_bytes(), b"changed audio content")
        self.assertFalse((target / "1.flac").exists())

    def test_target_appearing_after_preflight_is_never_overwritten(self):
        target, plans = plan_transfers(self.tracks(), self.music, str(self.root / "target"), False)
        target.mkdir()
        (target / "1.flac").write_bytes(b"another writer")
        results = execute_transfers(plans, "move")
        self.assertEqual([item["status"] for item in results], ["error", "moved"])
        self.assertEqual((target / "1.flac").read_bytes(), b"another writer")
        self.assertTrue(self.sources[0].exists())

    def test_relative_target_and_sources_outside_scan_root_are_rejected(self):
        with self.assertRaises(ValueError):
            plan_transfers(self.tracks(), self.music, "relative-target", True)
        with self.assertRaises(ValueError):
            plan_transfers(self.tracks(), self.music / "A/B", str(self.root / "target"), True)
        self.assertFalse((self.root / "target").exists())


class FolderOperationTests(unittest.TestCase):
    setUp = FileOperationTests.setUp
    tracks = FileOperationTests.tracks

    def plan(self, keep=True):
        return plan_folders(self.tracks(), self.music, str(self.root / "target"), keep,
                            {key: path for key, path, _ in self.tracks()})

    def test_recursive_copy_move_metadata_and_all_bytes(self):
        album = self.sources[0].parent
        (album / ".hidden").write_bytes(b"hidden")
        (album / "art").mkdir()
        (album / "art/cover.jpg").write_bytes(b"image")
        (album / "empty").mkdir()
        before = {p.relative_to(self.music): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.music.rglob("*") if p.is_file()}
        target, plans = self.plan()
        self.assertFalse(target.exists())
        self.assertEqual(sum(p.preview()["file_count"] for p in plans), 4)
        self.assertEqual([r["status"] for r in execute_folders(plans, "copy")], ["copied", "copied"])
        for path, (content, mtime) in before.items():
            self.assertEqual((target / path).read_bytes(), content)
            self.assertEqual((target / path).stat().st_mtime_ns, mtime)
        target2, plans2 = plan_folders(self.tracks(), self.music, str(self.root / "moved"), False, {})
        self.assertEqual([r["status"] for r in execute_folders(plans2, "move")], ["moved", "moved"])
        self.assertTrue((target2 / "B/empty").is_dir())
        self.assertFalse(any(p.exists() for p in self.sources))
        self.assertEqual(list(self.root.rglob(".lossless-lens-transfer-*.json")), [])

    def test_dedup_and_ancestor_merge(self):
        nested = self.sources[0].parent / "disc/3.flac"
        nested.parent.mkdir()
        nested.write_bytes(b"third")
        self.sources.extend([self.sources[0], nested])
        _, plans = self.plan()
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0].selected_track_ids, ["0", "2", "3"])
        self.assertEqual(plans[0].preview()["file_count"], 2)

    def test_root_overlap_links_and_conflicts_rejected(self):
        for target in (self.music, self.sources[0].parent / "inside"):
            with self.assertRaises(ValueError):
                plan_folders(self.tracks(), self.music, str(target), True, {})
        with self.assertRaises(ValueError):
            plan_folders(self.tracks(), self.sources[0].parent, str(self.root / "t"), True, {})
        target, _ = self.plan()
        (target / "A/B").mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.plan()
        # Windows junctions do not require symlink creation privileges.
        if sys.platform == "win32":
            link = self.sources[0].parent / "junction"
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.sources[1].parent)],
                           check=True, capture_output=True)
            try:
                with self.assertRaises(ValueError):
                    plan_folders(self.tracks(), self.music, str(self.root / "other"), True, {})
            finally:
                link.rmdir()

    def test_copy_or_metadata_failure_and_interrupt_preserve_sources(self):
        for failure in (OSError("disk full"), KeyboardInterrupt(), SystemExit(3)):
            target, plans = self.plan()
            with patch("file_operations.shutil.copyfileobj", side_effect=failure):
                result = execute_folders(plans[:1], "move")[0]
            self.assertEqual(result["status"], "error")
            self.assertTrue(all(p.exists() for p in self.sources))
            self.assertTrue(any(p.endswith(".json") for p in result["residual_targets"]))
            import shutil
            shutil.rmtree(target)
        _, plans = self.plan()
        with patch("file_operations.shutil.copystat", side_effect=OSError("metadata")):
            self.assertEqual(execute_folders(plans[:1], "move")[0]["status"], "error")
        self.assertTrue(all(p.exists() for p in self.sources))

    def test_partial_delete_reports_precise_remaining(self):
        extra = self.sources[0].parent / "0.flac"
        extra.write_bytes(b"extra")
        _, plans = self.plan()
        unlink = Path.unlink
        def deny(path, *args, **kwargs):
            if path == extra:
                raise PermissionError("locked")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", deny):
            result = execute_folders(plans[:1], "move")[0]
        self.assertEqual(result["status"], "copied_not_removed")
        self.assertFalse(self.sources[0].exists())
        self.assertIn(str(extra), result["remaining_sources"])
        self.assertNotIn(str(self.sources[0]), result["remaining_sources"])

    def test_changed_source_and_destination_race_preserve_source(self):
        target, plans = self.plan()
        (self.sources[0].parent / "new.jpg").write_bytes(b"new")
        self.assertEqual(execute_folders(plans[:1], "move")[0]["status"], "error")
        self.assertFalse(target.exists())
        _, plans = self.plan()
        plans[0].destination.mkdir(parents=True)
        marker = plans[0].destination / "owner"
        marker.write_bytes(b"other writer")
        result = execute_folders(plans[:1], "move")[0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(marker.read_bytes(), b"other writer")
        self.assertTrue(self.sources[0].exists())

    def test_source_mutation_during_directory_copy_prevents_all_deletions(self):
        import shutil
        copy = shutil.copyfileobj
        _, plans = self.plan()
        def mutate(incoming, outgoing, **kwargs):
            copy(incoming, outgoing, **kwargs)
            (self.sources[0].parent / "late.jpg").write_bytes(b"new file during copy")
        with patch("file_operations.shutil.copyfileobj", side_effect=mutate):
            result = execute_folders(plans[:1], "move")[0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.sources[0].read_bytes(), b"audio-0")
        self.assertTrue((self.sources[0].parent / "late.jpg").exists())
        self.assertIn(str(self.sources[0]), result["remaining_sources"])

    def test_process_termination_leaves_durable_recovery_manifest_and_source(self):
        code = '''
import os, sys
from pathlib import Path
from unittest.mock import patch
from file_operations import plan_folders, execute_folders
root = Path(sys.argv[1])
source = root / "aran/A/B/1.flac"
info = source.stat()
_, plans = plan_folders([("id", source, (info.st_size, info.st_mtime_ns))],
                       root / "aran", str(root / "target"), True, {})
def interrupt(*args, **kwargs):
    os._exit(23)
with patch("file_operations.shutil.copyfileobj", side_effect=interrupt):
    execute_folders(plans, "move")
'''
        process = subprocess.run([sys.executable, "-c", code, str(self.root)], capture_output=True)
        self.assertEqual(process.returncode, 23, process.stderr)
        manifests = list(self.root.rglob(".lossless-lens-transfer-*.json"))
        self.assertEqual(len(manifests), 1)
        record = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(record["source"], str(self.sources[0].parent))
        self.assertEqual(self.sources[0].read_bytes(), b"audio-0")
        self.assertTrue(Path(record["destination"]).exists())


class TransferApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.music = self.root / "aran"
        self.source = self.music / "A/B/1.flac"
        self.source.parent.mkdir(parents=True)
        audio = np.rint(.4 * np.sin(2 * np.pi * 3000 * np.arange(48000) / 48000) * 32768) / 32768
        sf.write(self.source, audio, 48000, subtype="PCM_24")
        self.app = create_app(self.music)

    def prepare(self, client, analyze=True):
        track = client.post("/api/scan", json={"folder": str(self.music)}).json()["tracks"][0]
        if analyze:
            response = client.get(f"/api/tracks/{track['id']}/analysis")
            self.assertEqual(response.status_code, 200)
            self.assertGreaterEqual(response.json()["forensics"]["score"], 35)
        return {"track_ids": [track["id"]], "target_folder": str(self.root / "target"), "operation": "copy"}

    def test_copy_then_move_default_structure_and_registry_update(self):
        with TestClient(self.app) as client:
            body = self.prepare(client)
            original = self.source.read_bytes()
            copied = client.post("/api/tracks/transfer", json=body)
            self.assertEqual(copied.status_code, 200)
            self.assertEqual(copied.json()["results"][0]["status"], "copied")
            self.assertEqual((self.root / "target/A/B/1.flac").read_bytes(), original)
            moved = client.post("/api/tracks/transfer", json={**body, "operation": "move", "target_folder": str(self.root / "moved"), "keep_structure": False})
            self.assertEqual(moved.status_code, 200)
            self.assertFalse(self.source.exists())
            self.assertEqual((self.root / "moved/1.flac").read_bytes(), original)
            self.assertEqual(client.get(f"/api/tracks/{body['track_ids'][0]}").status_code, 404)

    def test_unanalyzed_and_changed_analysis_sources_ignore_legal_thresholds(self):
        with TestClient(self.app) as client:
            body = self.prepare(client, analyze=False)
            for threshold in (0, 35, 100):
                target = self.root / f"unanalysed-{threshold}"
                response = client.post("/api/tracks/transfer", json={**body, "threshold": threshold, "target_folder": str(target)})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual((target / "A/B/1.flac").read_bytes(), self.source.read_bytes())
                self.assertTrue(self.source.exists())
            self.assertEqual(client.get(f"/api/tracks/{body['track_ids'][0]}/analysis").status_code, 200)
            with self.source.open("ab") as stream:
                stream.write(b"changed since analysis")
            response = client.post("/api/tracks/transfer", json={**body, "threshold": 100})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual((self.root / "target/A/B/1.flac").read_bytes(), self.source.read_bytes())

    def test_destination_conflict_never_overwrites_or_changes_source(self):
        with TestClient(self.app) as client:
            body = self.prepare(client, analyze=False)
            original = self.source.read_bytes()
            target = self.root / "target/A/B/1.flac"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"existing")
            for operation in ("copy", "move"):
                response = client.post("/api/tracks/transfer", json={**body, "operation": operation})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(target.read_bytes(), b"existing")
                self.assertEqual(self.source.read_bytes(), original)

    def test_changed_source_after_preview_requires_repreview(self):
        with TestClient(self.app) as client:
            body = self.prepare(client, analyze=False)
            for operation in ("copy", "move"):
                request = {**body, "operation": operation}
                preview = client.post("/api/tracks/transfer/preview", json=request)
                self.assertEqual(preview.status_code, 200, preview.text)
                with self.source.open("ab") as stream:
                    stream.write(b"changed after preview")
                changed = self.source.read_bytes()
                response = client.post("/api/tracks/transfer", json={**request, "preview_token": preview.json()["preview_token"]})
                self.assertEqual(response.status_code, 409)
                self.assertIn("重新预览", response.json()["detail"])
                self.assertEqual(self.source.read_bytes(), changed)
                self.assertFalse((self.root / "target").exists())

    def test_transfer_excludes_scan_analysis_and_other_transfers(self):
        started, release = threading.Event(), threading.Event()
        def controlled(plans, operation):
            started.set()
            if not release.wait(10):
                raise RuntimeError("test timed out")
            return execute_transfers(plans, operation)
        with TestClient(self.app) as client, ThreadPoolExecutor(max_workers=1) as requests:
            body = self.prepare(client)
            with patch("web_app.execute_transfers", side_effect=controlled):
                request = requests.submit(client.post, "/api/tracks/transfer", json=body)
                try:
                    self.assertTrue(started.wait(5))
                    self.assertEqual(client.post("/api/scan", json={"folder": str(self.music)}).status_code, 409)
                    self.assertEqual(client.get(f"/api/tracks/{body['track_ids'][0]}/analysis").status_code, 409)
                    self.assertEqual(client.post("/api/tracks/transfer", json=body).status_code, 409)
                finally:
                    release.set()
                self.assertEqual(request.result().status_code, 200)

    def test_invalid_requests_and_unknown_tracks(self):
        with TestClient(self.app) as client:
            body = self.prepare(client, analyze=False)
            for change in ({"threshold": -1}, {"threshold": 101}, {"threshold": 2.5}, {"threshold": True}, {"threshold": "35"}, {"operation": "delete"}, {"track_ids": []}):
                self.assertEqual(client.post("/api/tracks/transfer", json={**body, **change}).status_code, 422)
            self.assertEqual(client.post("/api/tracks/transfer", json={**body, "track_ids": ["missing"]}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
