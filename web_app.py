"""Run with: python web_app.py [--folder PATH] [--port 8765]."""
from __future__ import annotations

import argparse
from collections import OrderedDict
import hashlib
from pathlib import Path
import threading
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

BASE_DIR = Path(__file__).resolve().parent


class ScanRequest(BaseModel):
    folder: str = Field(min_length=1, max_length=4096)


def create_app(default_folder: Path = BASE_DIR) -> FastAPI:
    app = FastAPI(title="FLAC / spectral workspace", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    registry: dict[str, Path] = {}
    cache: OrderedDict = OrderedDict()
    lock = threading.RLock()
    analysis_lock = threading.Lock()

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
                "supported_extensions": sorted(SUPPORTED), "ffmpeg_available": bool(find_ffmpeg())}

    @app.post("/api/scan")
    def scan(body: ScanRequest):
        folder = Path(body.folder).expanduser()
        try:
            folder = folder.resolve(strict=True)
            if not folder.is_dir():
                raise ValueError("请输入音频文件夹路径。")
            files = sorted((p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED),
                           key=lambda p: str(p.relative_to(folder)).casefold())
            entries, found = [], {}
            for p in files:
                resolved = p.resolve()
                track_id = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:24]
                found[track_id] = resolved
                entries.append({"id": track_id, "name": p.name, "relative_path": str(p.relative_to(folder)),
                                "size_bytes": p.stat().st_size})
            with lock:
                registry.clear()
                registry.update(found)
                cache.clear()
            return {"folder": str(folder), "tracks": entries}
        except (OSError, ValueError) as exc:
            raise HTTPException(400, f"无法扫描文件夹：{exc}") from exc

    @app.get("/api/tracks/{track_id}")
    def plot_data(track_id: str):
        with lock:
            path = registry.get(track_id)
        if path is None:
            raise HTTPException(404, "未找到曲目，请重新扫描文件夹。")
        try:
            stat = path.stat()
            key = (track_id, stat.st_size, stat.st_mtime_ns)
            # Serialize expensive decodes; prevent parallel requests multiplying memory use.
            with analysis_lock:
                with lock:
                    if key in cache:
                        cache.move_to_end(key)
                        return cache[key]
                result = {"id": track_id, **build_plot_data(path)}
                with lock:
                    cache[key] = result
                    while len(cache) > 12:
                        cache.popitem(last=False)
                return result
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(422, f"无法分析 {path.name}：{exc}") from exc

    @app.get("/vendor/plotly.min.js")
    def plotly_js():
        return FileResponse(Path(plotly_file).parent / "package_data" / "plotly.min.js", media_type="text/javascript")

    app.mount("/static", StaticFiles(directory=BASE_DIR / "web"), name="static")

    @app.get("/")
    def index():
        return FileResponse(BASE_DIR / "web" / "index.html")

    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="FLAC 本地频谱对比 Web UI")
    parser.add_argument("--folder", type=Path, default=BASE_DIR, help="默认音频文件夹，递归扫描")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(create_app(args.folder), host="127.0.0.1", port=args.port)
