"""Local audio decoding for web plots; source files are never modified."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import soundfile as sf

from flac_forensics import _declared_bit_depth

SUPPORTED = {".flac", ".wav", ".wave", ".aif", ".aiff", ".aifc", ".mp3", ".mp2",
             ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".opus", ".wma", ".ape", ".wv", ".caf"}


def find_ffmpeg():
    return shutil.which(os.environ.get("FLAC_FORENSICS_FFMPEG", "ffmpeg"))


def _run(command, timeout):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError("音频解码超时，请检查文件或选择较短的音频。") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-1500:]
        raise ValueError(f"音频无法解码：{detail}")
    return result.stdout


def _source_metadata(path, ffmpeg):
    sibling = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    ffprobe = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
    metadata = {"format": path.suffix[1:].upper(), "subtype": "未知编码", "bit_depth": None}
    if not ffprobe:
        return metadata
    raw = _run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                "stream=codec_name,bits_per_raw_sample,bits_per_sample", "-of", "json", str(path)], 30)
    streams = json.loads(raw).get("streams", [])
    if not streams:
        raise ValueError("文件中没有可读取的音轨。")
    stream = streams[0]
    codec = stream.get("codec_name", "unknown")
    metadata["subtype"] = codec.upper()
    # Only lossless/PCM source metadata can describe an original sample depth.
    if codec in {"alac", "flac", "ape", "wavpack", "wmalossless"} or codec.startswith("pcm_"):
        for field in ("bits_per_raw_sample", "bits_per_sample"):
            try:
                bits = int(stream.get(field, 0))
            except (ValueError, TypeError):
                bits = 0
            if bits > 0:
                metadata["bit_depth"] = bits
                break
    return metadata


@contextmanager
def open_plot_audio(path):
    path = Path(path).resolve(strict=True)
    try:
        audio = sf.SoundFile(path)
    except sf.LibsndfileError:
        audio = None
    if audio is not None:
        with audio:
            yield audio, {"format": audio.format, "subtype": audio.subtype,
                          "bit_depth": _declared_bit_depth(audio.subtype), "decoder": "soundfile"}
        return
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise ValueError("当前格式需要 FFmpeg，或文件已损坏。请安装 FFmpeg 并加入 PATH，"
                         "也可设置 FLAC_FORENSICS_FFMPEG 为 ffmpeg.exe 完整路径，然后重启服务。")
    metadata = _source_metadata(path, ffmpeg)
    # Use disk-backed float64 PCM without changing sample rate or channel count.
    # Cleanup also runs when analysis raises or decoding fails.
    with tempfile.TemporaryDirectory(prefix="audio-plot-") as folder:
        decoded = Path(folder) / "decoded.wav"
        _run([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-map", "0:a:0",
              "-vn", "-c:a", "pcm_f64le", "-rf64", "auto", str(decoded)], 600)
        with sf.SoundFile(decoded) as audio:
            yield audio, {**metadata, "decoder": "ffmpeg"}
