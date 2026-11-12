"""Disposable full-analysis cache, confined to the startup working directory."""
import json
from pathlib import Path
import tempfile


class SessionCache:
    def __init__(self, work_dir: Path):
        # Explicit dir is mandatory: never fall back to the user's temp directory.
        self._temp = tempfile.TemporaryDirectory(prefix=".lossless-lens-", dir=work_dir)
        self.directory = Path(self._temp.name)

    def read(self, key):
        try:
            record = json.loads((self.directory / f"{key[0]}.json").read_text(encoding="utf-8"))
            result = record["result"]
            if record["key"] == list(key) and all(
                isinstance(result.get(field), dict)
                for field in ("info", "summary", "spectrum", "spectrogram", "analysis", "forensics")
            ):
                return result
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return None

    def write(self, key, result):
        target = self.directory / f"{key[0]}.json"
        pending = target.with_suffix(".tmp")
        try:
            with pending.open("w", encoding="utf-8") as stream:
                json.dump({"key": key, "result": result}, stream,
                          ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)

    def close(self):
        self._temp.cleanup()

    def remove_tracks(self, track_ids):
        for track_id in track_ids:
            (self.directory / f"{track_id}.json").unlink(missing_ok=True)
            (self.directory / f"{track_id}.tmp").unlink(missing_ok=True)
