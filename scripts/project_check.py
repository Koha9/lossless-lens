"""Local baseline checks; no package installs, external APIs, or user music."""
import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def check_guards():
    for name in ("LOSSLESS_LENS_REAL_AI", "LOSSLESS_LENS_EXTERNAL_ACTIONS"):
        if os.environ.get(name, "0") not in ("", "0"):
            raise RuntimeError(f"{name} must be disabled; this project grants no external calls")
    for remote in subprocess.check_output(["git", "remote"], cwd=ROOT, text=True).splitlines():
        urls = subprocess.check_output(
            ["git", "remote", "get-url", "--push", "--all", remote], cwd=ROOT, text=True).splitlines()
        if urls != ["DISABLED"]:
            raise RuntimeError("Worktree push guard missing; run scripts/configure_worktree.ps1")
    hooks = subprocess.check_output(["git", "config", "--get", "core.hooksPath"], cwd=ROOT, text=True).strip()
    if hooks != ".githooks" or not (ROOT / hooks / "pre-push").is_file():
        raise RuntimeError("Project pre-push hook missing")


def smoke():
    import numpy as np
    import soundfile as sf
    from fastapi.testclient import TestClient
    from web_app import create_app

    # Real local decoding + process worker analysis; TestClient uses no network port.
    with tempfile.TemporaryDirectory(prefix="ll-smoke-", dir=ROOT) as temp:
        folder = Path(temp)
        sf.write(folder / "tone.flac", .2 * np.sin(2 * np.pi * 3000 * np.arange(48000) / 48000), 48000)
        with TestClient(create_app(folder)) as client:
            for url in ("/", "/api/config", "/static/app.js", "/vendor/plotly.min.js"):
                response = client.get(url)
                response.raise_for_status()
            response = client.post("/api/scan", json={"folder": str(folder)})
            response.raise_for_status()
            tracks = response.json()["tracks"]
            assert len(tracks) == 1, tracks
            response = client.get(f"/api/tracks/{tracks[0]['id']}/analysis")
            response.raise_for_status()
            assert "forensics" in response.json(), response.text
    print("PASS smoke: static assets, scan, real FLAC analysis, lifecycle cleanup", flush=True)


def full_check():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in tracked:
        if name.endswith(".py"):
            ast.parse((ROOT / name).read_text(encoding="utf-8-sig"), filename=name)
        elif name.endswith(".js"):
            run("node", "--check", name)
    run("git", "diff", "--check")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    run("node", "--test", "tests/test_library_model.js", "tests/test_analysis_queue.js", "tests/test_i18n.js")
    # This app has no bundler. The smoke is the assembly check for Python and static assets.
    smoke()
    print("PASS local checks: syntax, diff, Python/JS tests, app assembly", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    check_guards()
    smoke() if args.smoke else full_check()
