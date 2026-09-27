"""Bounded-memory, full-track plot data for the local web application.

Channels are averaged in the power domain, so opposite-phase stereo does not
cancel out. Display reduction uses maxima to retain narrow peaks/transients.
This module does not change the notebook/CLI's forensic heuristics.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from audio_formats import open_plot_audio

from flac_forensics import _estimate_cutoff, _spectral_edge
from web_forensics import PaddingEvidence, assess_features

FFT_SIZE = 8192
TIME_BINS = 320
FREQUENCY_BINS = 513
FLOOR_DB = -120


def build_plot_data(path: Path, *, include_plots=True) -> dict:
    with open_plot_audio(path) as (audio, source):
        if audio.frames < 32:
            raise ValueError("音频过短：至少需要 32 个采样点。")
        sr, frames, channels = audio.samplerate, audio.frames, audio.channels
        nfft = min(FFT_SIZE, frames)
        hop = nfft // 2
        duration = frames / sr
        window = np.hanning(nfft)
        scale = sr * np.sum(window ** 2)
        frequencies = np.fft.rfftfreq(nfft, 1 / sr)
        # Keep fixed-size accumulators regardless of track duration.
        n_columns = min(TIME_BINS, 1 + max(0, int(np.ceil((frames - nfft) / hop))))
        groups = np.array_split(np.arange(len(frequencies)), min(FREQUENCY_BINS, len(frequencies)))
        starts = np.array([g[0] for g in groups])
        display_frequencies = np.array([frequencies[g].mean() for g in groups])
        heat = np.zeros((len(groups), n_columns))
        time_counts = np.zeros(n_columns, dtype=int)
        psd_sum = np.zeros(len(frequencies))
        count = 0
        padding = PaddingEvidence(source.get("bit_depth"))
        for block in audio.blocks(blocksize=nfft, overlap=nfft-hop, dtype="float64", always_2d=True):
            if not np.isfinite(block).all():
                raise ValueError("音频包含非有限采样值，无法绘图。")
            # Count each sample once despite overlapping FFT windows.
            padding.add(block if count == 0 else block[hop:])
            if len(block) < nfft:
                block = np.pad(block, ((0, nfft-len(block)), (0, 0)))
            power = np.mean(np.abs(np.fft.rfft(block * window[:, None], axis=0)) ** 2, axis=1) / scale
            power[1:-1 if nfft % 2 == 0 else None] *= 2
            psd_sum += power
            center = min((count * hop + nfft / 2) / sr, duration)
            column = min(n_columns - 1, int(center / duration * n_columns))
            heat[:, column] = np.maximum(heat[:, column], np.maximum.reduceat(power, starts))
            time_counts[column] += 1
            count += 1
        psd = psd_sum / count
        peak = float(psd.max())
        heat_peak = float(heat.max())
        psd_db = 10 * np.log10(np.maximum(psd, 1e-30))
        relative = np.clip(10 * np.log10(np.maximum(psd, 1e-30) / max(peak, 1e-30)), FLOOR_DB, 0)
        heat_db = np.clip(10 * np.log10(np.maximum(heat, 1e-30) / max(heat_peak, 1e-30)), FLOOR_DB, 0)
        if peak == 0:
            relative[:] = FLOOR_DB
            heat_db[:] = FLOOR_DB
        # Very short inputs can leave unused time buckets; keep them as missing,
        # never invent or repeat signal in those buckets.
        heat_rows = np.rint(heat_db).astype(int).tolist()
        for column in np.flatnonzero(time_counts == 0):
            for row in heat_rows:
                row[int(column)] = None
        cutoff, confidence, notes = _estimate_cutoff(frequencies, psd_db, sr / 2)
        # Spectrum remains at native FFT resolution for accurate peak hover.
        result = {
            "name": path.name,
            "info": {
                "sample_rate": sr, "channels": channels, "frames": frames,
                "duration_sec": duration, **source,
            },
            "summary": {
                "cutoff_hz": cutoff, "cutoff_confidence": confidence,
                "edge_95_hz": _spectral_edge(frequencies, psd, .95),
                "edge_99_hz": _spectral_edge(frequencies, psd, .99),
                "silent": peak == 0, "notes": notes,
            },
            "spectrum": {
                "frequency_khz": np.round(frequencies / 1000, 6).tolist(),
                "relative_db": np.round(relative, 2).tolist(),
            },
            "spectrogram": {
                "frequency_khz": np.round(display_frequencies / 1000, 6).tolist(),
                "time_sec": np.round((np.arange(n_columns) + .5) * duration / n_columns, 6).tolist(),
                "relative_db": heat_rows,
            },
            "analysis": {
                "fft_size": nfft, "hop_size": hop, "windows": count,
                "frequency_resolution_hz": sr / nfft,
                "time_bin_sec": duration / n_columns,
                "channel_mode": "mean_power", "reduction": "max",
                "normalization": "per_track_peak", "floor_db": FLOOR_DB,
            },
        }
        result["forensics"] = assess_features(result["info"], result["summary"], padding.fraction)
        if not include_plots:
            del result["spectrum"], result["spectrogram"]
        return result
