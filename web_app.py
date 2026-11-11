"""Run with: python web_app.py [--folder PATH] [--port 0]. Port 0 = OS picks a free port."""
from __future__ import annotations

import argparse
from collections import OrderedDict
from concurrent.futures import Future, ProcessPoolExecutor
from contextlib import asynccontextmanager
import hashlib
import multiprocessing
import os
import socket
from pathlib import Path
import threading
import secrets
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from plotly import __file__ as plotly_file
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from web_analysis import build_plot_data
from audio_formats import SUPPORTED, find_ffmpeg
from session_cache import SessionCache
from file_operations import (plan_transfers, execute_transfers, plan_folders,
                             execute_folders, inventory)

BASE_DIR = Path(__file__).resolve().parent
MAX_ANALYSIS_WORKERS = 32
DEFAULT_ANALYSIS_WORKERS = min(4, os.cpu_count() or 1)


class ScanRequest(BaseModel):
    folder: str = Field(min_length=1, max_length=4096)


class SettingsRequest(BaseModel):
    analysis_workers: int = Field(strict=True, ge=1, le=MAX_ANALYSIS_WORKERS)


class TransferRequest(BaseModel):
    track_ids: list[str] = Field(min_length=1)
    target_folder: str = Field(min_length=1, max_length=4096)
    operation: Literal["copy", "move"]
    keep_structure: bool = Field(default=True, strict=True)
    threshold: int = Field(default=35, strict=True, ge=0, le=100)
    folder_mode: bool = Field(default=False, strict=True)
    preview_token: str | None = None


def analysis_pool(workers):
    # Spawn is supported on Windows, including the onedir build. Workers stay
    # alive across tracks so imports and process startup are paid only once.
    return ProcessPoolExecutor(max_workers=workers,
                               mp_context=multiprocessing.get_context("spawn"))


def create_app(default_folder: Path = BASE_DIR) -> FastAPI:
    work_dir = Path.cwd().resolve()

    @asynccontextmanager
    async def lifespan(app):
        disk = SessionCache(work_dir)
        app.state.session_cache = disk
        app.state.analysis_workers = DEFAULT_ANALYSIS_WORKERS
        app.state.analysis_pool = analysis_pool(DEFAULT_ANALYSIS_WORKERS)
        try:
            yield
        finally:
            # Uvicorn drains active requests before shutdown; also guard writers.
            app.state.analysis_pool.shutdown(wait=True)
            with lock:
                disk.close()
                cache.clear()
                summaries.clear()

    app = FastAPI(title="FLAC / spectral workspace", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    registry: dict[str, Path] = {}
    cache: OrderedDict = OrderedDict()
    summaries: dict = {}
    lock = threading.RLock()
    in_flight: dict[str, Future] = {}
    library_lock = threading.Lock()
    transferring = threading.Event()
    scan_root: Path | None = None
    previews = OrderedDict()

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "仅允许从本地界面访问。"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/config")
    def config():
        return {"default_folder": str(default_folder.resolve()), "max_2d": 4, "max_3d": 8,
                "analysis_workers": app.state.analysis_workers,
                "default_analysis_workers": DEFAULT_ANALYSIS_WORKERS,
                "max_analysis_workers": MAX_ANALYSIS_WORKERS,
                "supported_extensions": sorted(SUPPORTED), "ffmpeg_available": bool(find_ffmpeg())}

    @app.put("/api/settings")
    def settings(body: SettingsRequest):
        with lock:
            if body.analysis_workers != app.state.analysis_workers:
                if in_flight:
                    raise HTTPException(409, "请等待当前分析完成后再调整进程数。")
                previous = app.state.analysis_pool
                app.state.analysis_pool = analysis_pool(body.analysis_workers)
                app.state.analysis_workers = body.analysis_workers
                previous.shutdown(wait=True)
            return {"analysis_workers": app.state.analysis_workers}

    @app.post("/api/scan")
    def scan(body: ScanRequest):
        nonlocal scan_root
        if not library_lock.acquire(blocking=False):
            raise HTTPException(409, "曲库操作进行中，请完成后重试。")
        folder = Path(body.folder).expanduser()
        try:
            folder = folder.resolve(strict=True)
            if not folder.is_dir():
                raise ValueError("请输入音频文件夹路径。")
            files = sorted((p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED
                            and not any(part.startswith(".lossless-lens-") for part in p.parts)),
                           key=lambda p: str(p.relative_to(folder)).casefold())
            entries, found = [], {}
            for p in files:
                resolved = p.resolve()
                track_id = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:24]
                found[track_id] = resolved
                entries.append({"id": track_id, "name": p.name, "relative_path": str(p.relative_to(folder)),
                                "size_bytes": p.stat().st_size})
            with lock:
                scan_root = folder
                registry.clear()
                registry.update(found)
                cache.clear()
                summaries.clear()
                previews.clear()
            return {"folder": str(folder), "tracks": entries}
        except (OSError, ValueError) as exc:
            raise HTTPException(400, f"无法扫描文件夹：{exc}") from exc
        finally:
            library_lock.release()

    def transfer_request(body: TransferRequest, preview=False):
        if not library_lock.acquire(blocking=False):
            raise HTTPException(409, "曲库操作进行中，请完成后重试。")
        try:
            with lock:
                if in_flight:
                    raise HTTPException(409, "请等待当前分析完成后再移动或复制曲目。")
                if scan_root is None:
                    raise HTTPException(409, "请先扫描音频文件夹。")
                transferring.set()
                root = scan_root
                paths = [(track_id, registry.get(track_id)) for track_id in dict.fromkeys(body.track_ids)]
            tracks = []
            for track_id, path in paths:
                if path is None:
                    raise HTTPException(404, "未找到曲目，请重新扫描文件夹。")
                try:
                    stat = path.stat()
                except (FileNotFoundError, NotADirectoryError) as exc:
                    if body.folder_mode and not preview and body.preview_token in previews:
                        raise HTTPException(409, "源范围已变化，预览已失效，请重新预览。") from exc
                    raise
                key = (track_id, stat.st_size, stat.st_mtime_ns)
                report = summaries.get(key) or app.state.session_cache.read(key)
                evidence = report["forensics"] if report else {}
                score = evidence.get("score")
                if (evidence.get("status") not in {"clear", "suspicious"}
                        or score is None or score < body.threshold):
                    raise HTTPException(409, f"{path.name} 没有符合阈值的当前分析结果，请重新分析或调整勾选。")
                tracks.append((track_id, path, (stat.st_size, stat.st_mtime_ns)))
            request_key = (tuple(sorted(body.track_ids)), body.target_folder, body.operation,
                           body.keep_structure, body.threshold, body.folder_mode, str(root))
            confirmed = previews.get(body.preview_token)
            if body.folder_mode and not preview and (confirmed is None or confirmed[0] != request_key):
                raise HTTPException(409, "预览已失效，请重新预览。")
            try:
                if body.folder_mode:
                    target, plans = plan_folders(tracks, root, body.target_folder, body.keep_structure, registry)
                    units = [plan.preview() for plan in plans]
                    signature = tuple((str(p.source), str(p.destination), p.snapshot,
                                       tuple(p.affected_track_ids)) for p in plans)
                else:
                    target, plans = plan_transfers(tracks, root, body.target_folder, body.keep_structure)
                    units = [{"source": str(p.source), "destination": str(p.destination),
                              "selected_track_ids": [p.track_id], "affected_track_ids": [p.track_id],
                              "file_count": 1, "directory_count": 0, "total_bytes": p.fingerprint[0]}
                             for p in plans]
                    signature = tuple((str(p.source), str(p.destination), inventory(p.source)) for p in plans)
            except (OSError, ValueError) as exc:
                if confirmed and not preview:
                    raise HTTPException(409, f"范围或目标已变化，请重新预览：{exc}") from exc
                raise
            if preview:
                token = secrets.token_urlsafe(32)
                previews[token] = (request_key, signature)
                while len(previews) > 64:
                    previews.popitem(last=False)
                return {"target_folder": str(target), "folder_mode": body.folder_mode,
                        "preview_token": token, "units": units,
                        "totals": {"units": len(units), "files": sum(u["file_count"] for u in units),
                                   "directories": sum(u["directory_count"] for u in units),
                                   "bytes": sum(u["total_bytes"] for u in units)}}
            if body.preview_token is not None or body.folder_mode:
                if confirmed != (request_key, signature):
                    raise HTTPException(409, "源或目标已变化，请重新预览。")
                previews.pop(body.preview_token, None)
            affected = {key: registry[key] for u in units for key in u["affected_track_ids"]}
            results = execute_folders(plans, body.operation) if body.folder_mode else execute_transfers(plans, body.operation)
            moved = {key for key, path in affected.items() if not path.exists()} if body.operation == "move" else set()
            with lock:
                for track_id in moved:
                    registry.pop(track_id, None)
                for store in (summaries, cache):
                    for key in list(store):
                        if key[0] in moved:
                            store.pop(key)
                app.state.session_cache.remove_tracks(moved)
            return {"target_folder": str(target), "results": results, "removed_track_ids": sorted(moved)}
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(422, f"无法处理曲目：{exc}") from exc
        finally:
            transferring.clear()
            library_lock.release()

    @app.post("/api/tracks/transfer/preview")
    def preview_transfer(body: TransferRequest):
        return transfer_request(body, preview=True)

    @app.post("/api/tracks/transfer")
    def transfer(body: TransferRequest):
        return transfer_request(body)

    def analyze(track_id: str, include_plots: bool):
        with lock:
            path = registry.get(track_id)
            if path is None:
                raise HTTPException(404, "未找到曲目，请重新扫描文件夹。")
        try:
            stat = path.stat()
        except OSError as exc:
            raise HTTPException(422, f"无法分析 {path.name}：{exc}") from exc
        key = (track_id, stat.st_size, stat.st_mtime_ns)
        with lock:
            if transferring.is_set():
                raise HTTPException(409, "正在移动或复制曲目，请完成后再分析。")
            if not include_plots and key in summaries:
                return summaries[key]
            # Share one result (or error) between simultaneous plot/summary
            # requests for the same track; only the owner writes its cache.
            future = in_flight.get(track_id)
            owner = future is None
            if owner:
                future = in_flight[track_id] = Future()
        try:
            if owner:
                with lock:
                    if key in cache:
                        cache.move_to_end(key)
                        result = cache[key]
                    else:
                        result = None
                if result is None:
                    disk = app.state.session_cache
                    result = disk.read(key)
                    if result is None:
                        computed = app.state.analysis_pool.submit(
                            build_plot_data, path, temp_dir=disk.directory).result()
                        result = {"id": track_id, **computed}
                        after = path.stat()
                        if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                            raise ValueError("文件在分析过程中发生变化，请重试。")
                        disk.write(key, result)
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                    raise ValueError("文件在分析过程中发生变化，请重试。")
                with lock:
                    if registry.get(track_id) == path:
                        for old_key in list(summaries):
                            if old_key[0] == track_id:
                                del summaries[old_key]
                                cache.pop(old_key, None)
                        summaries[key] = {k: v for k, v in result.items() if k not in {"spectrum", "spectrogram"}}
                        cache[key] = result
                        while len(cache) > 12:
                            cache.popitem(last=False)
                future.set_result(result)
            result = future.result()
            return result if include_plots else {k: v for k, v in result.items()
                                                if k not in {"spectrum", "spectrogram"}}
        except Exception as exc:
            if owner:
                future.set_exception(exc)
            if not isinstance(exc, (OSError, RuntimeError, ValueError)):
                raise
            raise HTTPException(422, f"无法分析 {path.name}：{exc}") from exc
        finally:
            if owner:
                with lock:
                    del in_flight[track_id]

    @app.get("/api/tracks/{track_id}/analysis")
    def forensic_data(track_id: str):
        return analyze(track_id, include_plots=False)

    @app.get("/api/tracks/{track_id}")
    def plot_data(track_id: str):
        return analyze(track_id, include_plots=True)

    @app.get("/vendor/plotly.min.js")
    def plotly_js():
        return FileResponse(Path(plotly_file).parent / "package_data" / "plotly.min.js", media_type="text/javascript")

    app.mount("/static", StaticFiles(directory=BASE_DIR / "web"), name="static")

    @app.get("/")
    def index():
        return FileResponse(BASE_DIR / "web" / "index.html")

    return app


if __name__ == "__main__":
    multiprocessing.freeze_support()
    import uvicorn

    parser = argparse.ArgumentParser(description="FLAC 本地频谱对比 Web UI")
    parser.add_argument("--folder", type=Path, default=Path.cwd(), help="默认音频文件夹，递归扫描")
    parser.add_argument("--port", type=int, default=0, help="监听端口；0 表示由系统自动分配可用端口（默认）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()
    # Bind ourselves so the real port is known before printing / opening the browser.
    # Port 0 lets the OS pick a free port, avoiding Windows reserved ranges (WinError 10013).
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", args.port))
    except OSError as exc:
        sock.close()
        raise SystemExit(f"无法绑定 127.0.0.1:{args.port}（{exc}）。请改用 --port 0 让系统自动分配端口。")
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    print(f"LosslessLens: {url}  (close this window or press Ctrl+C to quit)", flush=True)
    if not args.no_browser:
        import webbrowser
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    config = uvicorn.Config(create_app(args.folder), host="127.0.0.1", port=port)
    uvicorn.Server(config).run(sockets=[sock])
