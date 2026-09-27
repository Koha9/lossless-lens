
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import csv
import json
import math
import shutil
import subprocess
import wave

import numpy as np
import matplotlib.pyplot as plt

try:
    import soundfile as sf
except Exception as e:
    sf = None

try:
    from scipy.signal import welch
except Exception:
    welch = None


@dataclass
class AudioInfo:
    path: str
    format: str
    subtype: str
    channels: int
    sample_rate: int
    frames: int
    duration_sec: float
    bit_depth_declared: Optional[int]
    file_size_bytes: int
    average_bitrate_kbps: float


@dataclass
class SpectrumMetrics:
    nyquist_hz: float
    cutoff_estimate_hz: Optional[float]
    cutoff_confidence: float
    highband_energy_db: Dict[str, float]
    spectral_edge_95_hz: float
    spectral_edge_99_hz: float
    hf_activity_correlation: Optional[float]
    notes: List[str]


@dataclass
class BitDepthMetrics:
    declared_bit_depth: Optional[int]
    likely_zero_padded: Optional[bool]
    low_byte_unique_values: Optional[int]
    low_byte_entropy_bits: Optional[float]
    notes: List[str]


@dataclass
class AnalysisResult:
    info: AudioInfo
    spectrum: SpectrumMetrics
    bit_depth: BitDepthMetrics
    verdict: str
    confidence: str
    rationale: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _declared_bit_depth(subtype: str) -> Optional[int]:
    s = (subtype or "").upper()
    mapping = {
        "PCM_S8": 8, "PCM_U8": 8,
        "PCM_16": 16, "PCM_24": 24, "PCM_32": 32,
        "FLOAT": 32, "DOUBLE": 64,
    }
    return mapping.get(s)


def read_audio(path: str | Path) -> Tuple[np.ndarray, AudioInfo]:
    """
    Decode audio to float64 PCM in shape (frames, channels).
    Requires libsndfile via python-soundfile for FLAC.
    """
    if sf is None:
        raise RuntimeError(
            "python-soundfile is required. Install with: pip install soundfile"
        )

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    meta = sf.info(str(path))
    data, sr = sf.read(str(path), dtype="float64", always_2d=True)

    bit_depth = _declared_bit_depth(meta.subtype)
    duration = len(data) / sr if sr else 0.0
    file_size = path.stat().st_size
    avg_kbps = (file_size * 8 / max(duration, 1e-12)) / 1000.0

    info = AudioInfo(
        path=str(path),
        format=meta.format,
        subtype=meta.subtype,
        channels=data.shape[1],
        sample_rate=sr,
        frames=len(data),
        duration_sec=duration,
        bit_depth_declared=bit_depth,
        file_size_bytes=file_size,
        average_bitrate_kbps=avg_kbps,
    )
    return data, info


def _mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        return data.astype(np.float64, copy=False)
    return np.mean(data, axis=1, dtype=np.float64)


def _db_power(x: np.ndarray, eps: float = 1e-24) -> float:
    if x.size == 0:
        return float("-inf")
    p = float(np.mean(np.square(x, dtype=np.float64)))
    return 10.0 * math.log10(max(p, eps))


def _band_energy_from_psd(freqs: np.ndarray, psd: np.ndarray, lo: float, hi: float) -> float:
    mask = (freqs >= lo) & (freqs < hi)
    if not np.any(mask):
        return float("-inf")
    p = float(np.mean(psd[mask]))
    return 10.0 * math.log10(max(p, 1e-30))


def _spectral_edge(freqs: np.ndarray, psd: np.ndarray, frac: float) -> float:
    psd = np.maximum(psd, 0)
    c = np.cumsum(psd)
    if c[-1] <= 0:
        return 0.0
    idx = int(np.searchsorted(c, frac * c[-1]))
    idx = min(max(idx, 0), len(freqs) - 1)
    return float(freqs[idx])


def _estimate_cutoff(freqs: np.ndarray, psd_db: np.ndarray, nyq: float) -> Tuple[Optional[float], float, List[str]]:
    """
    Heuristic brick-wall detector.
    Looks for a sustained drop in the upper half of the spectrum.
    This is deliberately conservative: low-pass filtering != proof of lossy encoding.
    """
    notes = []
    if len(freqs) < 100:
        return None, 0.0, ["Insufficient spectral resolution."]

    valid = (freqs >= max(8000.0, nyq * 0.35)) & (freqs <= nyq * 0.98)
    f = freqs[valid]
    y = psd_db[valid]
    if len(f) < 50:
        return None, 0.0, ["Not enough high-frequency bins."]

    # Smooth over ~200 Hz.
    df = np.median(np.diff(f))
    k = max(3, int(round(200.0 / max(df, 1e-9))))
    if k % 2 == 0:
        k += 1
    kernel = np.ones(k) / k
    ys = np.convolve(y, kernel, mode="same")

    # Compare local windows before/after each candidate.
    best = None
    for i in range(k * 2, len(f) - k * 2):
        freq = f[i]
        if freq < 11000:
            continue
        before = np.median(ys[max(0, i-k*2):i])
        after = np.median(ys[i:min(len(ys), i+k*2)])
        drop = before - after

        # Require post-cut region to stay substantially lower for at least ~1 kHz.
        j = min(len(f), i + max(k * 2, int(1000 / max(df, 1e-9))))
        sustained = np.median(ys[i:j])
        sustain_drop = before - sustained

        score = 0.55 * drop + 0.45 * sustain_drop
        if best is None or score > best[0]:
            best = (score, freq, drop, sustain_drop, before, sustained)

    if best is None:
        return None, 0.0, ["No usable cutoff candidate found."]

    score, freq, drop, sustain_drop, before, sustained = best

    # Confidence is intentionally limited because mastering EQ can mimic this.
    conf = float(np.clip((score - 6.0) / 24.0, 0.0, 1.0))
    if drop >= 12 and sustain_drop >= 12:
        notes.append(
            f"Strong upper-band drop near {freq/1000:.2f} kHz "
            f"(local drop ~{drop:.1f} dB; sustained ~{sustain_drop:.1f} dB)."
        )
        return float(freq), conf, notes

    notes.append("No strong brick-wall cutoff detected.")
    return None, conf * 0.4, notes


def _segment_band_energy(
    x: np.ndarray,
    sr: int,
    band: Tuple[float, float],
    segment_sec: float = 2.0
) -> np.ndarray:
    n = max(1024, int(segment_sec * sr))
    vals = []
    for start in range(0, max(len(x) - n + 1, 1), n):
        seg = x[start:start+n]
        if len(seg) < 1024:
            continue
        win = np.hanning(len(seg))
        spec = np.fft.rfft(seg * win)
        freqs = np.fft.rfftfreq(len(seg), 1 / sr)
        p = np.abs(spec) ** 2
        mask = (freqs >= band[0]) & (freqs < band[1])
        vals.append(10*np.log10(max(float(np.mean(p[mask])) if np.any(mask) else 1e-30, 1e-30)))
    return np.asarray(vals, dtype=float)


def analyze_spectrum(data: np.ndarray, sr: int) -> SpectrumMetrics:
    x = _mono(data)
    nyq = sr / 2.0

    # Use Welch PSD if available; otherwise fall back to a long FFT.
    if welch is not None:
        nperseg = min(len(x), 65536)
        if nperseg < 4096:
            nperseg = len(x)
        freqs, psd = welch(
            x,
            fs=sr,
            window="hann",
            nperseg=nperseg,
            noverlap=nperseg // 2 if nperseg >= 2 else 0,
            detrend=False,
            scaling="density",
        )
    else:
        n = min(len(x), 1 << 20)
        seg = x[:n] * np.hanning(n)
        spec = np.fft.rfft(seg)
        freqs = np.fft.rfftfreq(n, 1 / sr)
        psd = (np.abs(spec) ** 2) / max(n, 1)

    psd = np.maximum(psd, 1e-30)
    psd_db = 10 * np.log10(psd)

    cutoff, cutoff_conf, notes = _estimate_cutoff(freqs, psd_db, nyq)

    edges = {
        "0-8k": (0, min(8000, nyq)),
        "8-12k": (8000, min(12000, nyq)),
        "12-16k": (12000, min(16000, nyq)),
        "16-18k": (16000, min(18000, nyq)),
        "18-20k": (18000, min(20000, nyq)),
        "20-22k": (20000, min(22000, nyq)),
        "22k-Nyquist": (22000, nyq),
    }
    band_db = {}
    for name, (lo, hi) in edges.items():
        if lo >= nyq or hi <= lo:
            continue
        band_db[name] = _band_energy_from_psd(freqs, psd, lo, hi)

    e95 = _spectral_edge(freqs, psd, 0.95)
    e99 = _spectral_edge(freqs, psd, 0.99)

    # Correlation between upper-mid HF and top-HF activity.
    corr = None
    if nyq >= 22000:
        a = _segment_band_energy(x, sr, (18000, min(22000, nyq)))
        b = _segment_band_energy(x, sr, (22000, nyq))
        if len(a) >= 4 and len(a) == len(b) and np.std(a) > 1e-9 and np.std(b) > 1e-9:
            corr = float(np.corrcoef(a, b)[0, 1])

    return SpectrumMetrics(
        nyquist_hz=nyq,
        cutoff_estimate_hz=cutoff,
        cutoff_confidence=cutoff_conf,
        highband_energy_db=band_db,
        spectral_edge_95_hz=e95,
        spectral_edge_99_hz=e99,
        hf_activity_correlation=corr,
        notes=notes,
    )


def analyze_bit_depth(data: np.ndarray, declared_bits: Optional[int]) -> BitDepthMetrics:
    notes = []

    if declared_bits not in (16, 24, 32):
        return BitDepthMetrics(
            declared_bit_depth=declared_bits,
            likely_zero_padded=None,
            low_byte_unique_values=None,
            low_byte_entropy_bits=None,
            notes=["Bit-depth padding test is only implemented for integer PCM-like 16/24/32-bit content."],
        )

    # soundfile gives normalized float. Reconstruct integer grid approximately.
    max_int = (1 << (declared_bits - 1)) - 1
    ints = np.rint(np.clip(data[:, 0], -1, 1) * max_int).astype(np.int64)

    if declared_bits < 24:
        return BitDepthMetrics(
            declared_bit_depth=declared_bits,
            likely_zero_padded=False,
            low_byte_unique_values=None,
            low_byte_entropy_bits=None,
            notes=["No '16-bit padded to 24-bit' test needed for declared depth below 24-bit."],
        )

    low = np.bitwise_and(ints, 0xFF).astype(np.uint8)
    hist = np.bincount(low, minlength=256).astype(float)
    probs = hist[hist > 0] / hist.sum()
    entropy = float(-(probs * np.log2(probs)).sum())
    unique = int(np.count_nonzero(hist))

    zero_frac = float(hist[0] / hist.sum())
    padded = bool(zero_frac > 0.995 or unique <= 4)

    if padded:
        notes.append(
            "Lowest byte is almost constant/empty, consistent with simple lower-bit padding."
        )
    else:
        notes.append(
            "Lowest byte contains substantial variation; simple 16->24 bit zero-padding is not indicated."
        )

    return BitDepthMetrics(
        declared_bit_depth=declared_bits,
        likely_zero_padded=padded,
        low_byte_unique_values=unique,
        low_byte_entropy_bits=entropy,
        notes=notes,
    )


def classify(info: AudioInfo, spectrum: SpectrumMetrics, bitdepth: BitDepthMetrics) -> Tuple[str, str, List[str]]:
    rationale = []
    suspicious = 0

    if spectrum.cutoff_estimate_hz is not None and spectrum.cutoff_confidence >= 0.35:
        khz = spectrum.cutoff_estimate_hz / 1000
        rationale.append(f"Detected a sustained upper-band cutoff around {khz:.2f} kHz.")
        # Stronger suspicion when cutoff is conspicuously below Nyquist.
        if spectrum.cutoff_estimate_hz < info.sample_rate * 0.44:
            suspicious += 2
        else:
            suspicious += 1

    if bitdepth.likely_zero_padded is True:
        suspicious += 2
        rationale.append("Declared high bit depth appears consistent with simple zero-padding.")

    if info.sample_rate >= 88200 and spectrum.spectral_edge_99_hz < 23000:
        suspicious += 1
        rationale.append(
            "Hi-res sample rate carries little energy above ~22 kHz; possible upsampling, "
            "although mastering/recording bandwidth can also cause this."
        )

    if spectrum.hf_activity_correlation is not None and spectrum.hf_activity_correlation > 0.6:
        rationale.append(
            f"Top-band activity tracks musical HF content (correlation {spectrum.hf_activity_correlation:.2f}), "
            "which argues against a completely empty padded high-frequency region."
        )

    if suspicious >= 3:
        verdict = "疑似假无损 / 疑似升采样"
        confidence = "中等"
    elif suspicious >= 2:
        verdict = "存在可疑特征，但不能单凭频谱定性"
        confidence = "中等"
    else:
        verdict = "未发现明显假无损特征"
        confidence = "中等"

    rationale.append(
        "注意：频谱低通、母带滤波、老录音设备和有损编码可能产生相似现象；"
        "本工具提供启发式判断，不是来源链的法证证明。"
    )
    return verdict, confidence, rationale


def analyze_file(path: str | Path) -> AnalysisResult:
    data, info = read_audio(path)
    spectrum = analyze_spectrum(data, info.sample_rate)
    bitdepth = analyze_bit_depth(data, info.bit_depth_declared)
    verdict, confidence, rationale = classify(info, spectrum, bitdepth)
    return AnalysisResult(
        info=info,
        spectrum=spectrum,
        bit_depth=bitdepth,
        verdict=verdict,
        confidence=confidence,
        rationale=rationale,
    )


CSV_COLUMNS = [
    "file", "status", "error", "format", "subtype", "sample_rate_hz",
    "channels", "bit_depth", "duration_sec", "file_size_bytes",
    "average_bitrate_kbps", "spectral_edge_95_hz", "spectral_edge_99_hz",
    "cutoff_estimate_hz", "cutoff_confidence", "hf_activity_correlation",
    "likely_zero_padded", "low_byte_unique_values", "low_byte_entropy_bits",
    "verdict", "confidence", "rationale",
]


def _summary_row(result: AnalysisResult, relative_path: Path) -> Dict[str, Any]:
    i, s, b = result.info, result.spectrum, result.bit_depth
    return {
        "file": str(relative_path), "status": "ok", "error": "",
        "format": i.format, "subtype": i.subtype,
        "sample_rate_hz": i.sample_rate, "channels": i.channels,
        "bit_depth": i.bit_depth_declared, "duration_sec": i.duration_sec,
        "file_size_bytes": i.file_size_bytes,
        "average_bitrate_kbps": i.average_bitrate_kbps,
        "spectral_edge_95_hz": s.spectral_edge_95_hz,
        "spectral_edge_99_hz": s.spectral_edge_99_hz,
        "cutoff_estimate_hz": s.cutoff_estimate_hz,
        "cutoff_confidence": s.cutoff_confidence,
        "hf_activity_correlation": s.hf_activity_correlation,
        "likely_zero_padded": b.likely_zero_padded,
        "low_byte_unique_values": b.low_byte_unique_values,
        "low_byte_entropy_bits": b.low_byte_entropy_bits,
        "verdict": result.verdict, "confidence": result.confidence,
        "rationale": " | ".join(result.rationale),
    }


def analyze_folder(
    folder: str | Path, csv_path: str | Path | None = None
) -> Tuple[List[AnalysisResult], List[Tuple[Path, str]]]:
    """Analyze FLAC files recursively and save one CSV row per file.

    Returns successful results and (path, error) pairs for failed files.
    """
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise NotADirectoryError(folder)
    files = sorted(
        (p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".flac"),
        key=lambda p: str(p.relative_to(folder)).casefold(),
    )
    if not files:
        raise ValueError(f"No FLAC files found in: {folder}")

    output = Path(csv_path) if csv_path is not None else folder / "flac_analysis.csv"
    results: List[AnalysisResult] = []
    errors: List[Tuple[Path, str]] = []
    rows = []
    for path in files:
        try:
            result = analyze_file(path)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append((path, message))
            rows.append({"file": str(path.relative_to(folder)), "status": "error", "error": message})
        else:
            results.append(result)
            rows.append(_summary_row(result, path.relative_to(folder)))

    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return results, errors


def plot_spectrum(path: str | Path, out_path: str | Path | None = None, max_seconds: Optional[float] = None):
    data, info = read_audio(path)
    x = _mono(data)
    if max_seconds is not None:
        x = x[: int(max_seconds * info.sample_rate)]

    n = min(len(x), 1 << 20)
    if n < 1024:
        raise ValueError("Audio too short for spectrum plot.")

    seg = x[:n] * np.hanning(n)
    spec = np.fft.rfft(seg)
    freqs = np.fft.rfftfreq(n, 1 / info.sample_rate)
    mag = 20 * np.log10(np.maximum(np.abs(spec), 1e-12))
    mag -= np.max(mag)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(freqs / 1000.0, mag, linewidth=0.8)
    ax.set_xlim(0, info.sample_rate / 2000.0)
    ax.set_ylim(-120, 3)
    ax.set_xlabel("Frequency (kHz)")
    ax.set_ylabel("Relative magnitude (dB)")
    ax.set_title(Path(path).name)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()

    if out_path:
        fig.savefig(out_path, dpi=160)
    return fig, ax


def plot_spectrogram(path: str | Path, out_path: str | Path | None = None):
    data, info = read_audio(path)
    x = _mono(data)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.specgram(
        x,
        NFFT=4096,
        Fs=info.sample_rate,
        noverlap=3072,
        scale="dB",
        mode="psd",
    )
    ax.set_ylim(0, info.sample_rate / 2)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(Path(path).name)
    fig.tight_layout()

    if out_path:
        fig.savefig(out_path, dpi=160)
    return fig, ax


def print_report(result: AnalysisResult) -> None:
    i = result.info
    s = result.spectrum
    b = result.bit_depth

    print("=" * 72)
    print("FLAC / PCM forensic heuristic report")
    print("=" * 72)
    print(f"File:        {i.path}")
    print(f"Format:      {i.format} / {i.subtype}")
    print(f"Audio:       {i.sample_rate} Hz / {i.channels} ch / {i.bit_depth_declared}-bit")
    print(f"Duration:    {i.duration_sec:.3f} s")
    print(f"Avg bitrate: {i.average_bitrate_kbps:.1f} kbps")
    print()
    print(f"Verdict:     {result.verdict}")
    print(f"Confidence:  {result.confidence}")
    print()
    print("Spectrum:")
    print(f"  Nyquist:           {s.nyquist_hz/1000:.3f} kHz")
    print(f"  Spectral edge 95%: {s.spectral_edge_95_hz/1000:.3f} kHz")
    print(f"  Spectral edge 99%: {s.spectral_edge_99_hz/1000:.3f} kHz")
    if s.cutoff_estimate_hz is not None:
        print(f"  Cutoff estimate:   {s.cutoff_estimate_hz/1000:.3f} kHz")
        print(f"  Cutoff confidence: {s.cutoff_confidence:.2f}")
    else:
        print("  Cutoff estimate:   none")
    if s.hf_activity_correlation is not None:
        print(f"  HF correlation:    {s.hf_activity_correlation:.3f}")
    print("  Band energies:")
    for k, v in s.highband_energy_db.items():
        print(f"    {k:>14}: {v:8.2f} dB")
    print()
    print("Bit depth:")
    print(f"  Declared:           {b.declared_bit_depth}")
    print(f"  Zero-padded likely: {b.likely_zero_padded}")
    if b.low_byte_unique_values is not None:
        print(f"  Low-byte unique:    {b.low_byte_unique_values}/256")
    if b.low_byte_entropy_bits is not None:
        print(f"  Low-byte entropy:   {b.low_byte_entropy_bits:.3f} bits")
    print()
    print("Rationale:")
    for line in result.rationale:
        print(f"  - {line}")


def save_json(result: AnalysisResult, out_path: str | Path) -> None:
    Path(out_path).write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Heuristic FLAC / PCM fake-lossless analyzer")
    parser.add_argument("audio", help="Path to a FLAC/WAV file or a folder of FLAC files")
    parser.add_argument("--csv", dest="csv_path", help="Summary CSV path for folder analysis")
    parser.add_argument("--json", dest="json_path", help="Save report as JSON")
    parser.add_argument("--spectrum", dest="spectrum_path", help="Save spectrum PNG")
    parser.add_argument("--spectrogram", dest="spectrogram_path", help="Save spectrogram PNG")
    args = parser.parse_args()

    if Path(args.audio).is_dir():
        if args.json_path or args.spectrum_path or args.spectrogram_path:
            parser.error("--json, --spectrum and --spectrogram require a single audio file")
        results, errors = analyze_folder(args.audio, args.csv_path)
        for result in results:
            print_report(result)
        for path, message in errors:
            print(f"FAILED: {path}: {message}")
        print(f"Analyzed {len(results)} file(s); {len(errors)} failed.")
        print(f"CSV: {args.csv_path or Path(args.audio).resolve() / 'flac_analysis.csv'}")
        raise SystemExit(0 if not errors else 1)
    if args.csv_path:
        parser.error("--csv requires a folder")
    result = analyze_file(args.audio)
    print_report(result)

    if args.json_path:
        save_json(result, args.json_path)
    if args.spectrum_path:
        plot_spectrum(args.audio, args.spectrum_path)
    if args.spectrogram_path:
        plot_spectrogram(args.audio, args.spectrogram_path)

    if args.spectrum_path or args.spectrogram_path:
        plt.show()
