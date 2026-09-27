# LosslessLens

**简体中文** | [English](README.en.md)

本地音频筛查与频谱对比工具，用于发现 FLAC / PCM 中可能存在的有损转码、升采样和位深补零迹象。提供 Web UI、Notebook 和命令行三种入口。

> 分析结果是启发式特征提示，不是音源真伪的证明。高频截止可能来自录音带宽、母带滤波或制作处理；未检出异常也不能证明来源真实。

## AI使用声明
本项目大部分代码由 Codex GPT-6 在约 30 分钟内编写。
作者只提供了总体需求，简单查看了核心逻辑，大部分代码并没有进行详细审查。
工具目前满足俺自己的使用需求，所以**如果计划将其用于重要判断，请考虑上述审查范围以及分析方法本身的限制。**

## 功能概览

| 入口 | 适用场景 | 输出 |
| --- | --- | --- |
| Web UI | 递归扫描曲库、勾选批量筛查、多格式音频对比 | 文件状态、评分依据、2D / 3D 图表、PNG |
| Notebook | 交互式查看 FLAC 批量分析报告 | 逐文件报告、CSV 汇总 |
| CLI | 批量分析 FLAC 文件夹或分析单个 FLAC / WAV 文件 | CSV，或单文件 JSON、频谱图、时频图 |

- Web 音频处理在本机完成，服务仅监听 `127.0.0.1`，不修改源音频。
- 图表使用本地 Plotly，无需运行时访问 CDN。
- Web 界面及部分分析报告目前以中文为主；英文 README 不代表界面已提供英文切换。

## 导航

[快速开始](#快速开始) · [Web UI](#web-ui) · [Notebook 用法](#notebook-用法) · [CLI 用法](#cli-用法) · [检测内容](#检测内容) · [重要限制](#重要限制) · [开发与验证](#开发与验证) · [关于 AI](#关于-ai)

## 快速开始

### 1. 创建环境

以下示例使用 Windows PowerShell 和 Anaconda，请从项目根目录执行。`$Conda` 按常见的用户目录安装位置设置；若安装在其他位置，请改成实际 `conda.exe` 路径。后续命令沿用此变量，无需激活环境。

```powershell
$Conda = Join-Path $env:USERPROFILE "anaconda3\Scripts\conda.exe"
& $Conda env create -f environment.yml
```

环境名为 `flac-forensics`，配置使用 Python 3.12。如果环境已存在，可用 `& $Conda env update -n flac-forensics -f environment.yml` 更新依赖。

### 2. 启动 Web UI

```powershell
& $Conda run -n flac-forensics python -m pip install -r requirements-web.txt
& $Conda run --no-capture-output -n flac-forensics python web_app.py --folder "D:\Music"
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。首次进入只扫描目录，勾选文件后点击「分析所选」或「生成对比」。在终端按 `Ctrl+C` 停止服务。

- 省略 `--folder` 时扫描启动工作目录；使用 `--port 8766` 更改端口。
- 仅使用 Notebook / CLI 时，基础环境已包含核心依赖，无需安装 Web 依赖。
- 使用其他 Python 环境时，通过该环境的解释器运行 `-m pip install -r requirements.txt`（核心）或 `requirements-web.txt`（Web），再运行相应脚本。若 SoundFile 无法读取 FLAC，请检查系统的 `libsndfile`。
- Linux / macOS 可使用自己的 Conda 路径执行相同的 `conda run` 命令，并替换音频目录。

## Web UI

### 曲库、批量筛查与对比

- 输入本机可访问的音频文件夹（也支持 UNC 路径），递归扫描 FLAC、WAV/WAVE、AIFF/AIFC、MP3/MP2、M4A/M4B、AAC、OGG/OGA、Opus、WMA、APE、WavPack（WV）和 CAF。首次打开只扫描目录，不自动分析文件。
- 曲库默认采用紧凑目录树，文件夹可展开／折叠，数字显示曲目数及已选数量。提供「目录树／列表」切换和全部展开／折叠；切换保留勾选，显示偏好保存在当前浏览器。搜索自动展开匹配的目录，清除搜索后恢复原来的展开状态。
- 勾选单个文件、整个文件夹或「全部文件」，点击「分析所选」；批量分析不受 2D / 3D 曲目数限制。父目录支持全选／半选，递归包含子目录。**搜索只过滤显示，勾选文件夹仍包含搜索隐藏的子文件**；「全部文件」也作用于整个扫描结果。
- 分析逐文件执行并显示进度，每完成一首立即更新文件树。可「停止后续分析」：当前文件完成后停止，保留已完成结果；未处理的文件恢复原状态。失败不阻断后续文件，重新点击分析可重试。
- 灰色：未分析；绿色：本次未检测出明显伪无损特征；黄至红：检测出可疑特征，评分越高底色越深、越偏红。蓝色区分等待／分析中及证据不足，紫色表示分析失败。每行也显示文字状态，点击「详情」查看判断依据。
- 文件夹显示已分析数量、可疑数量、最高评分和失败数量；颜色取已完成子文件的最高评分，不代表文件夹内所有文件都已分析或都可疑。切换目录树／列表、搜索和清空勾选不会丢失结果；**重新扫描、刷新页面会清除结果**，本次没有引入持久化结果库。
- 选择少量文件点击「生成对比」，图表结果也会更新对应文件的筛查状态。超出下述数量限制时仅禁用对比按钮，仍可分析全部勾选文件。
- **2D 对比**：1–4 首频谱叠加，时频图分面排列；时频图缩放会同步坐标轴。
- **3D 斜向堆叠**：1–8 首曲目分层显示；频谱为三维曲线，时频图为带颜色的平行平面，高度表示曲目编号。拖动旋转、滚轮缩放，可调整层间距、不透明度和重置视角。
- 可统一频率上限、动态范围，或按相对进度对齐不同时长的歌曲；两种图均可导出 PNG。
- 图表库由本机 Python 的 Plotly 包提供，运行时无需 CDN 或互联网。服务只监听 `127.0.0.1`，音频不上传云端、不修改源文件。

### 绘图与分析口径

Web 绘图覆盖整首音频，以最多 8192 点 Hann 窗和 50% 重叠进行流式 FFT，按声道平均功率，避免反相声道抵消。频谱使用全曲平均功率并归一化到峰值 0 dB；时频图单独按全曲时频峰值归一化。适合比较频率分布，**不能比较绝对响度**。静音以 −120 dB 显示。

时频图为显示而聚合到最多 513 个频率格 × 320 个时间格，每格保留最大能量；3D 再聚合至最多 129 × 128 格。聚合可保留弱小窄带中的峰值，但不是完整原始 STFT，悬停读数为显示格数据。坐标保持各曲目的实际采样率和时长；超出曲目范围不补齐数据。更多说明见页面底部「读图说明与分析口径」。

Web 摘要复用核心的能量边界和截止检测；Notebook / CLI 的完整鉴定和位深检查保持独立，原有使用方式不变。Web 的位深筛查遍历全部声道的非零样本，以整数 PCM 的准确归一化比例检查 16-bit 网格，避免静音样本被误当成补零证据。

### 本次运行的数据缓存

首次分析（包括「分析所选」）会把频谱数组、时频图矩阵、坐标、音频信息、分析参数、指标和筛查结果一起写入 JSON；保存的是上述显示分辨率的分析数据，不是原始 PCM 或完整 STFT。之后生成对比、刷新页面、重新扫描或超过内存最近 12 首的限制，都能复用磁盘数据，避免重复解码和 FFT。前端显示状态仍会在刷新／扫描时重置，再次请求数据会读取缓存。

缓存仅位于**进程启动时的工作目录（cwd）**下随机命名的 `.lossless-lens-*` 会话子目录。`--folder` 只改变音频扫描目录，不改变缓存位置；运行期间切换曲库也不改变缓存位置。FFmpeg 解码临时 WAV 同样位于该会话目录，单曲处理后立即清理。启动目录必须可写，失败时不回退到系统临时目录或 AppData。

缓存按文件路径、大小和纳秒修改时间校验；文件变动会重新分析并覆盖该曲目的旧数据，损坏的缓存会重建，分析途中变动会提示重试。保留相同大小和修改时间的外部修改无法被此校验识别。会话磁盘用量随分析曲目数增加；内存仍仅保留最近 12 首完整数据。

在运行服务的终端按 **Ctrl+C** 正常退出，会删除本次会话目录和所有缓存。关闭浏览器不会退出服务。强制结束进程、断电或崩溃可能留下目录，服务停止后可手动删除对应 `.lossless-lens-*`；不同实例各用独立目录，互不清理。下次启动重新分析，不复用旧会话。

### Windows `--onedir` 打包

在项目根目录的 PowerShell 执行（先按快速开始安装 Web 依赖）：

```powershell
.\build_onedir.ps1
# 或指定项目环境解释器：
.\build_onedir.ps1 -Python "C:\path\to\env\python.exe"
```

脚本调用 PyInstaller `--onedir --console`，将网页、Plotly 本地资源和 Python 运行依赖放入 `dist\LosslessLens\`。打包工具自动安装在 `build\packaging-tools`，构建临时文件和工具缓存都位于项目 `build\` 下。输出是目录包，分发时复制**整个 `LosslessLens` 文件夹**，不能只复制 exe；目标机器无需安装 Python/Conda。

```powershell
Set-Location .\dist\LosslessLens
.\LosslessLens.exe --folder "D:\Music" --port 8765
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)，退出时在终端按 Ctrl+C。此例缓存位于 `dist\LosslessLens\.lossless-lens-*`。FFmpeg/ffprobe 不包含在目录包中，需要相关格式时按下方说明另行配置。打包仅提供 Web 入口，不包含 Notebook / CLI 绘图功能。参数说明见 [PyInstaller 官方文档](https://pyinstaller.org/en/stable/usage.html)。

### 如何理解评分

**评分口径（不是确定率或真伪概率）：** 使用可解释的 0–100 特征评分，35 分为可疑阈值，当前最高输出 95 分。显著低于 Nyquist 的高频截止按检测强度记 40–75 分，靠近 Nyquist 的截止最多 20 分；24/32-bit 文件中超过 99.5% 的非零样本落在 16-bit 网格上记约 95 分（至少 4096 个非零样本）；高采样率但 99% 能量低于 23 kHz 记 25 分。多种特征同时存在时，在最高单项分上每多一项加 10，封顶 95。音频不足 0.25 秒、静音或未知编码不给分；已知有损格式标记为不适用。母带低通、录音带宽与制作处理也能触发这些特征；绿色同样不能证明来源真实。

### 格式支持与 FFmpeg

解码优先使用 SoundFile；M4A/AAC/WMA/APE 等需要 FFmpeg 回退。安装 FFmpeg 后使 `ffmpeg` 和 `ffprobe` 在 PATH 中可用，或在启动前将 `FLAC_FORENSICS_FFMPEG` 设置为 `ffmpeg.exe` 的完整路径（同目录放置 `ffprobe.exe`）。页面会显示 FFmpeg 是否可用；具体编码能否读取仍取决于解码器构建和文件是否完整，不支持加密音频。

FFmpeg 回退读取第一条音轨，保留采样率和声道数，暂存为浮点 PCM 后执行相同的全曲分析，结束或失败后自动清理临时文件；需要足够临时磁盘空间（约 `时长秒 × 采样率 × 声道数 × 8` 字节）。摘要显示源编码和已知的源位深，有损格式不把解码 PCM 的位深标为源文件位深。有损文件也可用于频谱对比，但不能因此推断为无损来源。此格式扩展适用于 Web UI，原 CLI / Notebook 的 FLAC 批量扫描不变。

## Notebook 用法

先在现有 Jupyter 或编辑器中注册项目内核（`environment.yml` 包含 `ipykernel`，不包含 Jupyter 界面）：

```powershell
& $Conda run -n flac-forensics python -m ipykernel install --user --name flac-forensics --display-name "Python (flac-forensics)"
```

在 Jupyter Notebook / JupyterLab 或支持 Notebook 的编辑器中打开 [flac_forensics.ipynb](flac_forensics.ipynb)，选择 `Python (flac-forensics)` 内核，将：

```python
FOLDER = Path(r"D:\music\album")
CSV_PATH = FOLDER / "flac_analysis.csv"
```

改成目标文件夹，然后依次运行即可。程序会扫描其子文件夹中的所有 `.flac` 文件，在 Notebook 输出每个文件的详细报告，并生成一份 CSV。无法分析的文件也会出现在 CSV 中，`status` 为 `error`，原因写在 `error` 列。

## CLI 用法

以下命令沿用快速开始中设置的 `$Conda`。

批量分析文件夹及其子目录中的 FLAC：

```powershell
& $Conda run -n flac-forensics python flac_forensics.py "D:\Music\album" --csv "D:\Music\album\flac_analysis.csv"
```

不指定 `--csv` 时，默认写入目标文件夹下的 `flac_analysis.csv`。分析失败的文件也写入 CSV，`status` 为 `error`，原因写入 `error` 列。CLI 会继续处理其他文件，最后返回非零退出码。

单文件分析：

```powershell
& $Conda run -n flac-forensics python flac_forensics.py "your_file.flac"
```

同时保存 JSON、频谱图和时频图：

```powershell
& $Conda run -n flac-forensics python flac_forensics.py "your_file.flac" --json report.json --spectrum spectrum.png --spectrogram spectrogram.png
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

## 项目结构

| 路径 | 用途 |
| --- | --- |
| [flac_forensics.py](flac_forensics.py) | 核心分析逻辑与 CLI |
| [flac_forensics.ipynb](flac_forensics.ipynb) | 交互式文件夹分析 |
| [web_app.py](web_app.py) | 本地 Web API 与启动入口 |
| [web_analysis.py](web_analysis.py) | 流式分析与绘图数据 |
| [web_forensics.py](web_forensics.py) | Web 筛查评分规则 |
| [audio_formats.py](audio_formats.py) | 格式识别与 FFmpeg 解码回退 |
| [web/](web/) | 无构建步骤的前端 |
| [tests/](tests/) | Python 与 JavaScript 测试 |
| [environment.yml](environment.yml) | Conda 环境配置 |
| `requirements*.txt` | 核心、Web 与开发依赖 |

## 开发与验证

沿用快速开始中的环境。JavaScript 测试另外需要可用的 Node.js：

```powershell
& $Conda run -n flac-forensics python -m pip install -r requirements-dev.txt
& $Conda run -n flac-forensics python -m unittest discover -s tests -v
node --test tests/test_library_model.js
```
