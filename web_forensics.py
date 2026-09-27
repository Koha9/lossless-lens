"""Transparent screening scores, not calibrated probabilities of provenance."""
from __future__ import annotations

import numpy as np


class PaddingEvidence:
    """Count active integer samples on a 16-bit grid, with bounded memory."""

    def __init__(self, bits):
        self.bits = bits if bits in (24, 32) else None
        self.active = 0
        self.aligned = 0

    def add(self, block):
        if self.bits is None:
            return
        # libsndfile normalizes PCM by 2**(bits-1), not its maximum.
        integers = np.rint(np.clip(block, -1, 1) * (1 << (self.bits - 1))).astype(np.int64)
        active = integers[integers != 0]
        self.active += active.size
        self.aligned += int(np.count_nonzero((active & ((1 << (self.bits - 16)) - 1)) == 0))

    @property
    def fraction(self):
        return self.aligned / self.active if self.active >= 4096 else None


def assess_features(info, summary, padding_fraction=None):
    """0..100 is feature strength; 35 is the flag threshold.

    Cutoff: up to 75, padding: up to 95, limited hi-res bandwidth: 25.
    Multiple features add 10 to the maximum, capped at 95.
    """
    def result(status, score, reasons):
        return {"status": status, "score": score, "reasons": reasons,
                "score_kind": "heuristic_feature_strength", "threshold": 35,
                "padding_16bit_fraction": padding_fraction}

    codec = info["subtype"].upper()
    if codec in {"MPEG_LAYER_III", "MPEG_LAYER_II", "MP3", "MP2", "AAC", "VORBIS",
                 "OPUS", "WMAV1", "WMAV2", "WMA", "GSM610", "ULAW", "ALAW"} or "ADPCM" in codec:
        return result("lossy", None, ["源文件使用已知有损编码，不适用伪无损筛查。"])
    if summary["silent"] or info["duration_sec"] < .25:
        return result("inconclusive", None, ["静音或音频不足 0.25 秒，证据不足。"])
    if not (codec.startswith("PCM_") or codec in {"FLAC", "ALAC", "APE", "WAVPACK",
            "WMALOSSLESS", "FLOAT", "DOUBLE"}):
        return result("inconclusive", None, ["无法确认源编码，保留频谱但不作伪无损判断。"])

    scores, reasons = [], []
    cutoff, confidence = summary["cutoff_hz"], summary["cutoff_confidence"]
    if cutoff is not None and confidence >= .35:
        below_band = cutoff < info["sample_rate"] * .44
        scores.append(40 + 35 * confidence if below_band else 20 * confidence)
        reasons.append(f"约 {cutoff / 1000:.2f} kHz 出现持续高频截止；截止特征强度 {confidence:.0%}。")
    if padding_fraction is not None and padding_fraction > .995:
        scores.append(85 + 10 * padding_fraction)
        reasons.append(f"{padding_fraction:.2%} 的非零样本落在 16-bit 网格上，疑似高位深补零。")
    if info["sample_rate"] >= 88200 and summary["edge_99_hz"] < 23000:
        scores.append(25)
        reasons.append("高采样率文件的 99% 能量位于 23 kHz 以下，可能带宽受限或经过升采样。")
    score = round(min(95, max(scores, default=0) + 10 * max(0, len(scores) - 1)))
    if not reasons:
        reasons.append("未检测出明显高频截止、16-bit 补零或高采样率低带宽特征。")
    reasons.append("评分是启发式特征强度，不是真伪概率；录音带宽、母带滤波也可能产生相似特征。")
    return result("suspicious" if score >= 35 else "clear", score, reasons)
