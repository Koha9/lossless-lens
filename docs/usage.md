# LosslessLens 使用指南

[English overview](../README.md) · [简体中文首页](../README.zh-CN.md)

## 音频格式与 FFmpeg

Web UI 支持 FLAC、WAV/WAVE、AIFF/AIFC、MP3/MP2、M4A/M4B、AAC、OGG/OGA、Opus、WMA、APE、WavPack（WV）和 CAF。优先通过 SoundFile 解码；M4A、AAC、WMA、APE 等可能需要 FFmpeg 回退，实际支持情况取决于解码器构建和文件完整性。不支持加密音频。

让 `ffmpeg` 和 `ffprobe` 在 PATH 中可用，或在启动前指定 FFmpeg 路径，同目录放置 `ffprobe.exe`：

```powershell
$env:FLAC_FORENSICS_FFMPEG = "C:\Tools\ffmpeg\bin\ffmpeg.exe"
```

回退解码读取第一条音轨，保留采样率和声道数，临时保存为浮点 PCM。临时磁盘空间约为 `时长秒 × 采样率 × 声道数 × 8` 字节，处理后清理。并发解码会增加空间占用。

## 曲库与分析设置

界面默认使用英文，可在页面右上角切换为简体中文；选择会保存在当前浏览器。以下操作名称以中文界面为例。

- 支持目录树、列表、文件夹递归勾选和名称搜索。搜索只过滤显示，勾选文件夹及「全部文件」仍包含隐藏的子文件。
- 批量分析不限 2D / 3D 的对比数量。失败不阻断后续曲目；「停止后续分析」会等待正在处理的曲目完成。
- 「分析进程数」可设为 1–32，默认取逻辑 CPU 核心数与 4 中的较小值，1 为串行。更多进程会增加资源占用，不保证总是更快。
- 设置保存在当前浏览器，点击保存后应用。任务进行中可以查看设置，完成后再修改。
- 刷新页面或重新扫描会清除界面的分析状态；再次请求可复用本次服务会话的缓存。

## 评分与图表

Web 筛查综合高频截止、位深补零和高采样率低带宽特征，输出 0–100 的启发式特征评分，35 分及以上标为可疑，当前最高输出为 95。静音、过短音频、未知编码和已知有损格式单独标注，不给出同类评分。

绿色表示本次未检出明显特征，不代表确认来源真实。文件夹颜色取已完成子文件的最高评分，不代表整个文件夹都可疑。录音设备、老母带、低通滤波、DSP 和重采样都可能产生相似特征。

图表覆盖整首音频，使用最多 8192 点 Hann 窗、50% 重叠 FFT，按声道平均功率，避免反相声道抵消。频谱与时频图分别按每首曲目的峰值归一化，适合比较形状，不能比较绝对响度。

时频图聚合到最多 513 × 320 格，每格保留最大能量；3D 再聚合至最多 129 × 128 格。悬停数值是显示分辨率的数据。3D 高度表示曲目层，颜色表示相对功率。页面底部的读图说明也可随时查阅。

## 勾选与文件整理

「可疑曲目勾选阈值」为 0–100 的整数，默认 35，只影响一键勾选和移动／复制范围，不改变分析评分、颜色或判断依据。

「勾选可疑」用评分大于或等于阈值的已分析曲目替换当前勾选，包含搜索隐藏项，排除无评分、失败和未分析曲目。「移动／复制」只处理已勾选且符合阈值的曲目，不连带封面等其他文件。

弹窗默认复制，默认保留目录结构。以扫描根目录 `D:\Music\Artist` 为例：

| 源文件相对路径 | 保留结构 | 不保留结构 |
| --- | --- | --- |
| `A\B\1.flac` | `TARGET\A\B\1.flac` | `TARGET\1.flac` |
| `A\C\2.flac` | `TARGET\A\C\2.flac` | `TARGET\2.flac` |

目标目录需要完整本地路径或 UNC 路径，不额外套上 `Artist` 这一层。目标文件已存在，或扁平存放产生重名时，会在执行前阻止整批操作，不覆盖文件。

执行中逐首报告结果，某首失败后继续处理其他曲目。未完成副本会尝试清理，清理失败会明确提示。移动会在完整复制及元数据保存成功后删除源文件；删除失败时保留两份并报告「已复制，源文件未删除」。成功移动的曲目从当前曲库和图表移除。

文件整理期间无法扫描或分析。源文件自分析后发生变化时，需要重新分析。若请求中断，请核对源目录与目标目录，再决定如何处理剩余文件。

## 会话缓存

缓存和 FFmpeg 临时文件位于**启动工作目录**下随机命名的 `.lossless-lens-*` 子目录，`--folder` 不改变缓存位置。启动目录必须可写。缓存保存显示分辨率的完整分析数据，不保存原始 PCM 或完整 STFT；内存保留最近 12 首完整结果。

缓存按路径、大小和纳秒修改时间校验，文件变化或缓存损坏时重建；保持相同大小和修改时间的外部修改无法被识别。缓存随分析曲目数增长。

在终端按 Ctrl+C 正常退出会删除本次会话目录；关闭浏览器不会停止服务。强制结束、崩溃或断电可能留下目录，确认对应服务已停止后可手动删除。

## 命令行

CLI 的文件夹扫描以 FLAC 为目标；Web 的多格式扩展不改变命令行入口。

```sh
# 批量分析；不指定 --csv 时写入音频文件夹中的 flac_analysis.csv
conda run -n flac-forensics python flac_forensics.py "D:\Music\album" --csv report.csv

# 单文件 FLAC / WAV，按需输出 JSON 与图表
conda run -n flac-forensics python flac_forensics.py "track.flac" --json report.json --spectrum spectrum.png --spectrogram spectrogram.png
```

批量失败文件也写入 CSV，包含 `status=error` 和原因；程序继续处理其余文件，最后返回非零退出码。

核心依赖见 [requirements.txt](../requirements.txt)。

## Windows 打包

先按首页安装 Web 依赖，停止正在运行的 LosslessLens 服务，再从项目根目录执行：

```powershell
.\build_onedir.ps1 -Python "$env:USERPROFILE\anaconda3\envs\flac-forensics\python.exe"
```

Conda 安装位置不同，或使用其他 Python 环境时，替换 `-Python` 路径。脚本检查依赖和 exe 启动，使用所选环境的原生 DLL；打包工具、缓存及暂存产物位于 `build` 下。

最终输出为 `dist\LosslessLens`，分发时复制**整个目录**，不能只复制 exe。目标机器无需 Python 或 Conda；FFmpeg / ffprobe 不随包提供。该目录包提供 Web 入口，不包含 CLI 绘图功能。

```powershell
Set-Location .\dist\LosslessLens
.\LosslessLens.exe --folder "D:\Music" --port 19000
```

## 开发与测试

沿用首页的 Conda 环境，JavaScript 测试另需 Node.js：

```sh
conda run -n flac-forensics python -m pip install -r requirements-dev.txt
conda run -n flac-forensics python -m unittest discover -s tests -v
node --test tests/test_library_model.js tests/test_analysis_queue.js tests/test_i18n.js
```

后端入口为 [web_app.py](../web_app.py)，分析和评分分别位于 [web_analysis.py](../web_analysis.py)、[web_forensics.py](../web_forensics.py)，文件整理位于 [file_operations.py](../file_operations.py)，前端位于 [web](../web)。
