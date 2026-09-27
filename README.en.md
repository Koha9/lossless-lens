# LosslessLens

[简体中文](README.md) | **English**

A local audio screening and spectrum comparison tool for spotting possible lossy-to-lossless transcodes, upsampling, and padded bit depth in FLAC / PCM audio. Use the Web UI, a Notebook, or the command line.

> Results are heuristic indicators, not proof of an audio file's provenance. Recording bandwidth, mastering filters, and production choices can produce similar patterns. A clean result does not prove an authentic lossless source.

## About AI
Most of this project was written by Codex GPT-6 in about 30 minutes. 
The author provided the general requirements and performed a quick sanity check of the core logic, but most of the code has not been reviewed in detail.
It currently meets the author's needs. **Keep that review scope and the analysis limitations in mind before relying on it for important decisions.**

## Features at a glance

| Interface | Best for | Output |
| --- | --- | --- |
| Web UI | Recursive library browsing, selected-file screening, multi-format comparisons | File statuses, score explanations, 2D / 3D charts, PNG exports |
| Notebook | Interactive batch reports for FLAC files | Per-file reports and a CSV summary |
| CLI | Recursive FLAC folder analysis or individual FLAC / WAV analysis | CSV, or single-file JSON, spectrum and spectrogram images |

- Web audio processing stays on your machine. The server listens only on `127.0.0.1` and does not modify source audio.
- Charts use the locally installed Plotly package, without a runtime CDN connection.
- The Web UI and some analysis reports are currently primarily in Chinese. This English README does not add an English interface switch.

## Contents

[Quick start](#quick-start) · [Web UI](#web-ui) · [Notebook usage](#notebook-usage) · [CLI usage](#cli-usage) · [What it detects](#what-it-detects) · [Limitations](#limitations) · [Development and validation](#development-and-validation) · [About AI](#about-ai)

## Quick start

### 1. Create the environment

These examples use Windows PowerShell and Anaconda. Run them from the project root. `$Conda` uses the usual per-user installation location; change it to your actual `conda.exe` path if necessary. Later commands reuse this variable without activating the environment.

```powershell
$Conda = Join-Path $env:USERPROFILE "anaconda3\Scripts\conda.exe"
& $Conda env create -f environment.yml
```

The environment is named `flac-forensics` and specifies Python 3.12. If it already exists, update its dependencies with `& $Conda env update -n flac-forensics -f environment.yml`.

### 2. Start the Web UI

```powershell
& $Conda run -n flac-forensics python -m pip install -r requirements-web.txt
& $Conda run --no-capture-output -n flac-forensics python web_app.py --folder "D:\Music"
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The initial scan only lists files. Select files and click **分析所选** (Analyze selected) or **生成对比** (Generate comparison). Press `Ctrl+C` in the terminal to stop the server.

- Without `--folder`, the app scans the project directory. Use `--port 8766` to change the port.
- For Notebook / CLI use only, the base environment already includes the core dependencies; Web dependencies are optional.
- With another Python environment, use its interpreter to run `-m pip install -r requirements.txt` for core features or `requirements-web.txt` for the Web UI, then run the corresponding script. If SoundFile cannot read FLAC, check that `libsndfile` is available.
- On Linux / macOS, use your own Conda executable with the same `conda run` arguments and replace the audio paths.

## Web UI

### Library browsing and batch screening

1. Enter a locally accessible audio folder, including a UNC path if needed. Scanning is recursive and does not automatically analyze audio.
2. Select individual files, folders, or all files, then click **分析所选** (Analyze selected). Folder selection recursively includes subfolders and supports partial-selection indicators.
3. Read the per-file status and open **详情** (Details) for the evidence behind a result.
4. Select a few files and click **生成对比** (Generate comparison) to inspect their spectra and spectrograms. Comparisons also update the selected files' screening results.

The default compact directory tree shows track and selection counts. You can switch between tree and list views or expand / collapse all folders. Selection survives view changes, and display preferences are stored in the current browser. Search expands matching folders; clearing it restores the previous expansion state.

**Search only filters what is displayed. Selecting a folder still selects its hidden descendants, and Select all applies to the entire scan.** Batch analysis has no 2D / 3D track-count limit; exceeding the comparison limit only disables the comparison button.

Analysis runs one file at a time and updates progress after each file. **停止后续分析** (Stop subsequent analysis) finishes the current file, keeps completed results, and restores unprocessed files to their previous state. One failure does not stop the batch; run analysis again to retry.

| Color | Meaning |
| --- | --- |
| Gray | Not analyzed |
| Green | No obvious suspicious features detected in this run |
| Yellow to red | Suspicious features; darker / redder colors indicate higher scores |
| Blue | Queued, analyzing, or insufficient evidence; check the text status |
| Purple | Analysis failed |

Folders show analyzed and suspicious counts, the highest score, and failure counts. Their color reflects the highest score among completed descendants, not a verdict on every file. Search, view changes, and clearing selections preserve results. **Rescanning or refreshing the page clears results; there is no persistent results database.**

### Spectrum comparisons

- **2D comparison:** 1–4 tracks, overlaid spectra, and separate spectrogram panels with synchronized axis zooming.
- **3D stacked comparison:** 1–8 tracks, with spectral curves and colored spectrogram planes separated by track index. Height represents the track index. Rotate, zoom, adjust spacing and opacity, or reset the view.
- Set a common frequency limit and dynamic range, or align tracks of different lengths by relative progress. Both chart types support PNG export.

### Plotting and analysis details

Web plots cover the full track using streaming FFTs with Hann windows of up to 8192 samples and 50% overlap. Channel powers are averaged to avoid cancellation between opposite-phase channels. Spectra use full-track mean power normalized to a peak of 0 dB; spectrograms use their own full-track time-frequency peak. These plots compare frequency distributions, **not absolute loudness**. Silence is shown at −120 dB.

For display, spectrograms are aggregated to at most 513 frequency bins × 320 time bins, retaining maximum energy in each cell. The 3D view further reduces this to at most 129 × 128 cells. This preserves peaks in small, narrow bands but is not the complete raw STFT; hover values describe display cells. Coordinates retain each track's actual sample rate and duration, without padding beyond its range. Further notes appear at the bottom of the page under **读图说明与分析口径**.

Web summaries reuse the core spectral-edge and cutoff detection. The full Notebook / CLI assessment and bit-depth checks remain separate. Web bit-depth screening examines nonzero samples across all channels using the exact integer-PCM normalization scale to test alignment to a 16-bit grid; silence is excluded from padding evidence.

The backend caches plotting data for the latest 12 files using file size and modification time, and keeps lightweight summaries within the current scan. Analysis and comparison requests check the cache; a file changed during analysis requires a retry. Every scan clears the cache.

### Interpreting scores

Scores measure heuristic feature strength on a 0–100 scale; **they are not confidence percentages or probabilities of authenticity**. The suspicious threshold is 35, and the current implementation caps scores at 95.

| Feature | Contribution |
| --- | --- |
| High-frequency cutoff well below Nyquist | A 40–75 rule scaled by detected strength |
| Cutoff near Nyquist | Up to 20 |
| More than 99.5% of nonzero samples in a 24/32-bit file lie on a 16-bit grid | About 95; requires at least 4096 nonzero samples |
| Sample rate of at least 88.2 kHz, but 99% of energy lies below 23 kHz | 25 |
| Multiple features | Highest individual score plus 10 per additional feature, capped at 95 |

Silence, audio shorter than 0.25 seconds, and unknown encodings receive no score. Known lossy encodings are marked not applicable. Mastering filters, recording bandwidth, and production processing can trigger these features; green does not prove authenticity.

### Supported formats and FFmpeg

Web scanning recognizes FLAC, WAV/WAVE, AIFF/AIFC, MP3/MP2, M4A/M4B, AAC, OGG/OGA, Opus, WMA, APE, WavPack (WV), and CAF.

Decoding first tries SoundFile. Formats such as M4A, AAC, WMA, and APE may require the FFmpeg fallback. Make `ffmpeg` and `ffprobe` available on PATH, or set `FLAC_FORENSICS_FFMPEG` to the full path of `ffmpeg.exe` before startup, with `ffprobe.exe` beside it. The page reports FFmpeg availability. Actual codec support depends on the decoder build and file integrity; encrypted audio is unsupported.

The fallback reads the first audio stream, preserves sample rate and channel count, and temporarily decodes it to floating-point PCM for the same full-track analysis. Temporary files are cleaned up on success or failure. Allow approximately `duration in seconds × sample rate × channels × 8` bytes of temporary disk space.

Summaries show the source encoding and source bit depth when known. For lossy sources, decoded PCM bit depth is not reported as the original bit depth. Lossy files can participate in spectrum comparisons, but this does not establish a lossless origin. **Expanded format support applies to the Web UI; CLI / Notebook folder scans still target FLAC files.**

## Notebook usage

Register the project kernel in your existing Jupyter installation or editor. `environment.yml` includes `ipykernel`, but not the Jupyter user interface:

```powershell
& $Conda run -n flac-forensics python -m ipykernel install --user --name flac-forensics --display-name "Python (flac-forensics)"
```

Open [flac_forensics.ipynb](flac_forensics.ipynb) in Jupyter Notebook / JupyterLab or a Notebook-capable editor, select **Python (flac-forensics)**, and edit:

```python
FOLDER = Path(r"D:\Music\album")
CSV_PATH = FOLDER / "flac_analysis.csv"
```

Run the cells in order. The Notebook recursively analyzes `.flac` files, displays detailed per-file reports, and writes a CSV summary. Failed files are included with `status=error` and the reason in the `error` column.

## CLI usage

These commands reuse `$Conda` from Quick start.

Recursively analyze a folder of FLAC files:

```powershell
& $Conda run -n flac-forensics python flac_forensics.py "D:\Music\album" --csv "D:\Music\album\flac_analysis.csv"
```

Without `--csv`, the output defaults to `flac_analysis.csv` in the target folder. Failed files are recorded with `status=error` and an `error` message. The CLI continues with the remaining files and returns a nonzero exit code if any analysis fails.

Analyze one file:

```powershell
& $Conda run -n flac-forensics python flac_forensics.py "your_file.flac"
```

Save JSON, a spectrum, and a spectrogram:

```powershell
& $Conda run -n flac-forensics python flac_forensics.py "your_file.flac" --json report.json --spectrum spectrum.png --spectrogram spectrogram.png
```

## What it detects

- Basic FLAC / PCM properties and average file bitrate.
- High-frequency band energy and 95% / 99% spectral edges.
- Suspected brick-wall high-frequency cutoffs.
- Low-byte usage in 24/32-bit files and simple 16-to-24-bit zero padding.
- Suspiciously limited bandwidth in 88.2 / 96 / 176.4 / 192 kHz files.
- Correlation between activity at the top of the spectrum and musical content in 48 kHz files.

## Limitations

A 16 kHz cutoff does not automatically mean MP3 was converted to FLAC. Limited recording hardware, older masters or tape, telephone or broadcast sources, lo-fi production, intentional low-pass or anti-aliasing filters, processed release masters, and DSP / resampling chains can all produce noticeable cutoffs.

Treat results as **heuristic screening and comparison aids**, not definitive evidence of an audio file's source history.

## Project layout

| Path | Purpose |
| --- | --- |
| [flac_forensics.py](flac_forensics.py) | Core analysis and CLI |
| [flac_forensics.ipynb](flac_forensics.ipynb) | Interactive folder analysis |
| [web_app.py](web_app.py) | Local Web API and entry point |
| [web_analysis.py](web_analysis.py) | Streaming analysis and plotting data |
| [web_forensics.py](web_forensics.py) | Web screening rules |
| [audio_formats.py](audio_formats.py) | Format handling and FFmpeg fallback |
| [web/](web/) | Frontend with no build step |
| [tests/](tests/) | Python and JavaScript tests |
| [environment.yml](environment.yml) | Conda environment definition |
| `requirements*.txt` | Core, Web, and development dependencies |

## Development and validation

Use the environment from Quick start. The JavaScript test also requires Node.js:

```powershell
& $Conda run -n flac-forensics python -m pip install -r requirements-dev.txt
& $Conda run -n flac-forensics python -m unittest discover -s tests -v
node --test tests/test_library_model.js
```