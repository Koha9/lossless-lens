# FLAC Forensics Tool

一个用于筛查 FLAC / PCM 是否存在“有损转无损”或“升采样”迹象的小工具。

## 文件

- `flac_forensics.ipynb`：文件夹批量分析的交互入口
- `flac_forensics.py`：核心分析逻辑
- `requirements.txt`：Python 依赖
- `environment.yml`：Anaconda 环境配置

## 安装

```bash
pip install -r requirements.txt
```

如果 `soundfile` 安装后仍无法读取 FLAC，请确保系统有 `libsndfile`。

## Web UI：频谱与时频对比

在 `flac-forensics` 环境安装 Web 依赖并启动（PowerShell）：

```powershell
& C:\Users\UCUNI\anaconda3\envs\flac-forensics\python.exe -m pip install -r requirements-web.txt
& C:\Users\UCUNI\anaconda3\envs\flac-forensics\python.exe web_app.py --folder "D:\Music"
```

打开 http://127.0.0.1:8765 。不传 `--folder` 时默认扫描本项目目录；端口可通过 `--port 8766` 更改。其他机器上使用项目环境内的 Python 运行同样的脚本即可。

- 输入本机可访问的音频文件夹（也支持 UNC 路径），递归扫描 FLAC、WAV/WAVE、AIFF/AIFC、MP3/MP2、M4A/M4B、AAC、OGG/OGA、Opus、WMA、APE、WavPack（WV）和 CAF。首次打开自动用前两首生成预览。
- 曲库默认采用紧凑目录树，文件夹可展开／折叠，数字显示曲目数及已选数量。提供「目录树／列表」切换和全部展开／折叠；切换保留勾选，显示偏好保存在当前浏览器。搜索自动展开匹配的目录，清除搜索后恢复原来的展开状态。
- 在左侧勾选曲目，点击「生成对比」。支持搜索曲名或文件夹；解码失败会单独标出，不会影响其他曲目。
- **2D 对比**：1–4 首频谱叠加，时频图分面排列；时频图缩放会同步坐标轴。
- **3D 斜向堆叠**：1–8 首曲目分层显示；频谱为三维曲线，时频图为带颜色的平行平面，高度表示曲目编号。拖动旋转、滚轮缩放，可调整层间距、不透明度和重置视角。
- 可统一频率上限、动态范围，或按相对进度对齐不同时长的歌曲；两种图均可导出 PNG。
- 图表库由本机 Python 的 Plotly 包提供，运行时无需 CDN 或互联网。服务只监听 `127.0.0.1`，音频不上传云端、不修改源文件。

Web 绘图覆盖整首音频，以最多 8192 点 Hann 窗和 50% 重叠进行流式 FFT，按声道平均功率，避免反相声道抵消。频谱使用全曲平均功率并归一化到峰值 0 dB；时频图单独按全曲时频峰值归一化。适合比较频率分布，**不能比较绝对响度**。静音以 −120 dB 显示。

时频图为显示而聚合到最多 513 个频率格 × 320 个时间格，每格保留最大能量；3D 再聚合至最多 129 × 128 格。聚合可保留弱小窄带中的峰值，但不是完整原始 STFT，悬停读数为显示格数据。坐标保持各曲目的实际采样率和时长；超出曲目范围不补齐数据。更多说明见页面底部「读图说明与分析口径」。

Web 摘要复用核心的能量边界和截止检测；Notebook / CLI 的完整鉴定和位深检查保持独立，原有使用方式不变。后端按文件大小和修改时间缓存最近 12 首结果；点击重新生成时会检查缓存是否仍有效。扫描新文件夹会清空缓存。

解码优先使用 SoundFile；M4A/AAC/WMA/APE 等需要 FFmpeg 回退。安装 FFmpeg 后使 `ffmpeg` 和 `ffprobe` 在 PATH 中可用，或在启动前将 `FLAC_FORENSICS_FFMPEG` 设置为 `ffmpeg.exe` 的完整路径（同目录放置 `ffprobe.exe`）。页面会显示 FFmpeg 是否可用；具体编码能否读取仍取决于解码器构建和文件是否完整，不支持加密音频。

FFmpeg 回退读取第一条音轨，保留采样率和声道数，暂存为浮点 PCM 后执行相同的全曲分析，结束或失败后自动清理临时文件；需要足够临时磁盘空间（约 `时长秒 × 采样率 × 声道数 × 8` 字节）。摘要显示源编码和已知的源位深，有损格式不把解码 PCM 的位深标为源文件位深。有损文件也可用于频谱对比，但不能因此推断为无损来源。此格式扩展适用于 Web UI，原 CLI / Notebook 的 FLAC 批量扫描不变。

Web 文件：`web_app.py`（本地 API）、`web_analysis.py`（绘图数据）、`web/`（无构建步骤的前端）。

验证：

```powershell
& C:\Users\UCUNI\anaconda3\envs\flac-forensics\python.exe -m pip install -r requirements-dev.txt
& C:\Users\UCUNI\anaconda3\envs\flac-forensics\python.exe -m unittest discover -s tests -v
```

## Notebook 用法

打开 `flac_forensics.ipynb`，选择 `Python (flac-forensics)` 内核，将：

```python
FOLDER = Path(r"D:\music\album")
CSV_PATH = FOLDER / "flac_analysis.csv"
```

改成目标文件夹，然后依次运行即可。程序会扫描其子文件夹中的所有 `.flac` 文件，在 Notebook 输出每个文件的详细报告，并生成一份 CSV。无法分析的文件也会出现在 CSV 中，`status` 为 `error`，原因写在 `error` 列。

## CLI 用法

批量分析文件夹：

```bash
python flac_forensics.py "D:\music\album" --csv "D:\music\album\flac_analysis.csv"
```

不指定 `--csv` 时，默认写入指定文件夹下的 `flac_analysis.csv`。如果有文件分析失败，CLI 会继续处理其他文件，最后返回非零退出码。

单文件分析：

```bash
python flac_forensics.py "your_file.flac"
```

同时保存 JSON 和图：

```bash
python flac_forensics.py "your_file.flac" \
  --json report.json \
  --spectrum spectrum.png \
  --spectrogram spectrogram.png
```

## 检测内容

- FLAC/PCM 基本参数
- 平均文件码率
- 高频频带能量
- 95% / 99% spectral edge
- 疑似砖墙式高频截止
- 24/32-bit 文件的低字节使用情况
- 简单 16->24 bit 补零检测
- 88.2/96/176.4/192 kHz 文件的可疑低带宽提示
- 48 kHz 文件顶部高频活动与音乐内容的相关性

## 重要限制

“16 kHz 截止”并不自动等于 MP3 转 FLAC。

以下情况也可能造成明显高频截止：

- 原始录音设备带宽有限
- 老母带 / 磁带 / 电话或广播来源
- lo-fi 制作
- 有意低通或抗混叠滤波
- 发行母带本身已被处理
- DSP / 重采样链路

因此输出是**启发式判断**，适合筛查和横向比较，不应当当作来源链的绝对证明。
