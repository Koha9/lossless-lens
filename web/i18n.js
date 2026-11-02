"use strict";

// Chinese source text is retained so language switching never changes analysis data.
const LensI18n = (() => {
  let language = "en";
  let originalTitle = "";
  const english = {
    "FLAC Lab · 频谱对比工作台": "FLAC Lab · Spectrum workspace",
    "FLAC Lab 首页": "FLAC Lab home", "界面语言": "Interface language",
    "设置": "Settings", "本地分析": "Local analysis", "音频曲库": "Audio library",
    "音频文件夹": "Audio folder", "D:\\Music 或 UNC 路径": "D:\\Music or UNC path",
    "扫描": "Scan", "包含子文件夹 · 常见无损 / 有损音频": "Includes subfolders · Lossless / lossy audio",
    "包含子文件夹 · M4A / AAC 等格式需安装 FFmpeg": "Includes subfolders · M4A / AAC may need FFmpeg",
    "搜索曲名或文件夹…": "Search tracks or folders…", "搜索曲目": "Search tracks",
    "曲库显示方式": "Library view", "目录树": "Tree", "列表": "List",
    "展开": "Expand", "折叠": "Collapse", "全部文件": "All files", "清空选择": "Clear selection",
    "分析颜色图例": "Analysis color key", "灰：未分析": "Gray: not analyzed", "绿：低 → 红：高": "Green: low → Red: high",
    "特征评分 0–100，非真伪概率。文件夹勾选包含全部子文件。": "Feature score 0–100, not authenticity. Folder selection includes descendants.",
    "按已分析结果替换当前勾选，包含搜索隐藏项": "Replace selection with matching analyzed tracks, including hidden results",
    "移动／复制": "Move / copy", "扫描文件夹后，在这里勾选曲目。": "Scan a folder, then select tracks here.",
    "分析所选": "Analyze selected", "停止后续分析": "Stop queued analysis", "生成对比": "Compare",
    "频谱分析工作台": "Spectrum workspace", "读图说明": "Reading the charts", "对比设置": "Comparison settings",
    "显示模式": "Display mode", "2D 对比": "2D comparison", "3D 斜向堆叠": "3D stacked",
    "频率上限": "Frequency limit", "完整频段": "Full range", "动态范围": "Dynamic range",
    "时间坐标": "Time axis", "实际时长 / s": "Seconds", "相对进度 / %": "Progress / %",
    "层间距": "Layer spacing", "时频图不透明度": "Spectrogram opacity", "拖动旋转 · 滚轮缩放": "Drag to rotate · Scroll to zoom",
    "重置视角 ↺": "Reset view ↺", "正在连接本地分析服务…": "Connecting to local analysis service…",
    "批量分析进度": "Batch analysis progress", "当前图表曲目": "Displayed tracks",
    "选择曲目后开始分析": "Select tracks to get started",
    "左侧勾选文件或文件夹 → 分析所选；选择少量曲目 → 生成对比。": "Select files or folders → Analyze selected. Select a few tracks → Compare.",
    "分析状态直接显示在目录树中，点击「详情」查看依据。": "Results appear in the library. Open Details to review the evidence.",
    "频率响应": "Frequency spectrum", "Relative magnitude — Frequency · 全曲平均功率，峰值归一化": "Relative magnitude — Frequency · Full-track average power, peak-normalized",
    "导出 PNG ↓": "Export PNG ↓", "相对幅度与频率对比图": "Relative magnitude versus frequency",
    "时频分布": "Spectrogram", "Frequency — Time · 相同频率、时间范围与色阶": "Frequency — Time · Shared axes and color scale",
    "Frequency — Time · 高度代表曲目层，颜色代表相对功率": "Frequency — Time · Height is track index, color is relative power",
    "频率与时间对比图": "Frequency versus time",
    "颜色表示各曲目相对峰值的功率 dB，数值越接近 0，能量越强。": "Color shows power relative to each track's peak in dB. Values nearer 0 indicate stronger energy.",
    "曲目摘要": "Track summary", "当前图表中的曲目 · 全曲分析": "Displayed tracks · Full-track analysis",
    "曲目": "Track", "曲目层": "Track layer", "采样率 / 位深或编码": "Sample rate / Bit depth or codec",
    "时长": "Duration", "99% 能量边界": "99% spectral edge", "疑似高频截止": "Suspected cutoff",
    "读图说明与分析口径": "How to read these charts", "频谱：": "Spectrum:", "时频图：": "Spectrogram:",
    "对比：": "Comparison:", "归一化与限制：": "Normalization and limitations:",
    "整首音频使用 Hann 窗、最多 8192 点 FFT、50% 重叠；先分别计算每个声道的功率，再平均，避免反相立体声被抵消。平均功率转换为相对 dB，每首歌的频谱峰值为 0 dB。": "Full-track analysis uses a Hann window, up to 8192 FFT points and 50% overlap. Channel power is averaged to avoid phase cancellation. Each track's spectrum is normalized to a 0 dB peak.",
    "横轴为时间，纵轴为频率，颜色表示相对功率。全曲压缩到最多 320 个时间格和 513 个频率格，每格保留最大能量；3D 再压缩至最多 128 × 129 格以保持交互流畅。悬停读数代表显示格，不代表未压缩的瞬时值。": "Time runs horizontally, frequency vertically, and color shows relative power. Display data is reduced to at most 320 time bins by 513 frequency bins using maxima; 3D uses at most 128 by 129 bins. Hover values describe display bins, not the original STFT.",
    "2D 叠加频谱并分面显示时频图；3D 将曲目放在独立层上，时频图高度表示曲目编号，不是响度。使用相同坐标范围和 −120 至 0 dB 色阶；较短曲目、较低采样率以外的区域为空。可切换为相对进度对齐不同长度曲目。": "2D overlays spectra and separates spectrograms. 3D places tracks on separate layers; height is track index, not loudness. Axes and the −120 to 0 dB scale are shared. Areas beyond a track's duration or sample rate remain empty. Relative progress aligns tracks of different lengths.",
    "频谱与时频图分别按各曲目的各自峰值归一化，因此适合比较形状，不能用于比较绝对响度。静音显示为底噪色并单独标记。截止频率沿用项目的启发式检测；低通、老录音或母带处理也会造成截止，不能单凭图表判断有损转无损。文件树评分综合高频截止、16-bit 网格补零与高采样率低带宽特征，35 分及以上标为可疑；它是可解释的启发式特征强度，不是经过校准的真伪概率。绿色仅表示本次未检测出明显特征，不保证来源真实。静音、短音频、未知编码与已知有损编码单独标注。结果保留到重新扫描或刷新页面；文件夹颜色取已完成子文件最高评分，并显示完成数量。": "Spectrum and spectrogram peaks are normalized separately per track, so charts compare shapes, not absolute loudness. Silence is marked separately. Cutoffs can also result from low-pass filters, old recordings or mastering. Scores combine cutoff, 16-bit padding and limited hi-res bandwidth features; 35 or above is suspicious. Scores are heuristic indicators, not calibrated authenticity probabilities. Green does not prove authenticity. Unscored sources are labeled separately. Refreshing or rescanning resets displayed results. Folder color reflects its highest completed score.",
    "音频在本机处理 · 不上传云端": "Processed locally · No cloud upload",
    "详情": "Details", "分析详情": "Analysis details", "关闭 ×": "Close ×", "关闭": "Close",
    "绿色表示本次未检测出明显特征，不代表确认真实无损。重新扫描或刷新页面将清除结果。": "Green means no obvious features were found, not proof of lossless provenance. Rescanning or refreshing clears displayed results.",
    "PNG 预览": "PNG preview", "当前对比图表的 PNG 导出预览": "PNG export preview of the current comparison",
    "保存 PNG ↓": "Save PNG ↓", "若内置浏览器未弹出下载，可右键图片保存，或在外部浏览器打开本地页面。": "If the embedded browser does not download, save the image from its context menu or open the local page in another browser.",
    "歌曲分析": "Track analysis", "同时处理多首歌曲，减少批量分析的等待时间。": "Analyze several tracks at once to reduce batch processing time.",
    "分析进程数": "Analysis processes", "1 为串行处理。更多进程会增加 CPU、内存与临时磁盘占用，数量越大不一定越快；单首歌曲的分析方法保持一致。": "1 runs serially. More processes use more CPU, memory and temporary disk space; a higher count is not always faster. Each track uses the same analysis method.",
    "可疑曲目勾选阈值": "Suspicious selection threshold",
    "默认 35 分，选择评分大于或等于此值的已分析曲目。只影响一键勾选与移动／复制范围，不改变分析评分、颜色或判断依据。": "Default: 35. Select analyzed tracks at or above this score. This affects selection and transfers only, not scores, colors or evidence.",
    "恢复默认值": "Restore defaults", "取消": "Cancel", "保存设置": "Save settings", "正在保存…": "Saving…",
    "正在保存设置…": "Saving settings…", "当前任务进行中，完成后可调整进程数。": "A task is running. Settings can be changed when it finishes.",
    "保存后对后续分析生效。此偏好保存在当前浏览器。": "Saved settings apply to subsequent work and are remembered in this browser.",
    "移动／复制可疑曲目": "Move / copy suspicious tracks", "处理方式": "Operation", "复制": "Copy", "移动": "Move",
    "目标目录": "Destination", "目标文件夹（完整路径或 UNC 路径）": "Destination folder (absolute or UNC path)",
    "D:\\可疑曲目 或 \\\\NAS\\share\\可疑曲目": "D:\\Review or \\\\NAS\\share\\Review",
    "保持原有目录结构": "Preserve folder structure", "目标路径预览": "Destination preview", "文件操作结果": "Transfer results",
    "目标存在同名文件或多首曲目映射到同一位置时，会阻止本次操作，不覆盖文件。": "Existing files or duplicate destination names block the batch. Files are never overwritten.",
    "开始复制": "Start copying", "等待正在处理的曲目完成…": "Waiting for active tracks…",
    "移动会在完整复制成功后删除源文件；源目录中的封面和其他文件保持原位。": "Moving removes sources after complete copies succeed. Covers and other files stay in place.",
    "复制会保留源文件；只处理列出的音频文件。": "Copying keeps the sources. Only the listed audio files are processed.",
    "请求未完成，请核对源目录和目标目录后再重试。": "The request did not complete. Check source and destination folders before retrying.",
    "已复制": "Copied", "已移动": "Moved", "已复制，源文件未删除": "Copied; source not removed", "失败": "Failed",
    "未分析": "Not analyzed", "等待分析": "Queued", "正在分析…": "Analyzing…", "分析失败 · 可重试": "Analysis failed · Retry available",
    "证据不足": "Insufficient evidence", "已知有损格式 · 不适用": "Known lossy codec · Not applicable", "未检测出明显特征": "No obvious features",
    "检测出可疑特征": "Suspicious features", "未知状态": "Unknown status", "未见异常": "No flags", "可疑": "Suspicious", "有损编码": "Lossy codec",
    "没有匹配的曲目，试试其他关键词。": "No matching tracks. Try another search.", "此文件夹内没有可用音频。请检查路径后重新扫描。": "No supported audio in this folder. Check the path and rescan.",
    "正在扫描音频文件夹…": "Scanning audio folder…", "没有找到支持的音频文件，请更换文件夹。": "No supported audio files found. Choose another folder.",
    "请先点击「生成对比」更新为当前勾选的最多 4 首，再切换 2D。": "Compare the current selection of up to 4 tracks before switching to 2D.",
    "静音": "Silent", "未检测到": "Not detected", "生成 PNG…": "Generating PNG…",
    "已清空选择，当前图表仍显示上一次对比结果。勾选曲目后可重新生成。": "Selection cleared. The previous comparison remains visible; select tracks to compare again.",
    "图表库未能加载。请确认已安装 requirements-web.txt，然后刷新页面。": "Chart library unavailable. Install requirements-web.txt and refresh the page.",
    "勾选此文件，点击「分析所选」。": "Select this file and click Analyze selected.",
    "源文件使用已知有损编码，不适用伪无损筛查。": "The source uses a known lossy codec; lossless-provenance screening does not apply.",
    "静音或音频不足 0.25 秒，证据不足。": "The audio is silent or shorter than 0.25 seconds; evidence is insufficient.",
    "无法确认源编码，保留频谱但不作伪无损判断。": "The source codec is unknown. Spectrum data is available, but no provenance verdict is given.",
    "高采样率文件的 99% 能量位于 23 kHz 以下，可能带宽受限或经过升采样。": "99% of this hi-res track's energy is below 23 kHz; bandwidth may be limited or the track upsampled.",
    "未检测出明显高频截止、16-bit 补零或高采样率低带宽特征。": "No obvious cutoff, 16-bit padding or limited hi-res bandwidth was detected.",
    "评分是启发式特征强度，不是真伪概率；录音带宽、母带滤波也可能产生相似特征。": "The score is a heuristic feature indicator, not an authenticity probability. Recording bandwidth and mastering filters can produce similar features.",
    "仅允许从本地界面访问。": "Access is restricted to the local interface.", "请输入音频文件夹路径。": "Enter an audio folder path.",
    "曲库操作进行中，请完成后重试。": "A library operation is running. Try again when it finishes.",
    "请等待当前分析完成后再调整进程数。": "Wait for analysis to finish before changing the process count.",
    "请等待当前分析完成后再移动或复制曲目。": "Wait for analysis to finish before moving or copying tracks.",
    "请先扫描音频文件夹。": "Scan an audio folder first.", "未找到曲目，请重新扫描文件夹。": "Track not found. Rescan the folder.",
    "正在移动或复制曲目，请完成后再分析。": "A transfer is running. Wait before starting analysis.",
    "文件在分析过程中发生变化，请重试。": "The file changed during analysis. Try again.",
    "音频过短：至少需要 32 个采样点。": "Audio is too short; at least 32 samples are required.",
    "音频包含非有限采样值，无法绘图。": "Audio contains non-finite samples and cannot be plotted.",
    "音频解码超时，请检查文件或选择较短的音频。": "Audio decoding timed out. Check the file or choose a shorter track.",
    "文件中没有可读取的音轨。": "No readable audio stream was found.", "未知编码": "Unknown codec",
    "当前格式需要 FFmpeg，或文件已损坏。请安装 FFmpeg 并加入 PATH，也可设置 FLAC_FORENSICS_FFMPEG 为 ffmpeg.exe 完整路径，然后重启服务。": "This format requires FFmpeg, or the file is damaged. Install FFmpeg on PATH or set FLAC_FORENSICS_FFMPEG to ffmpeg.exe, then restart the service.",
    "目标文件夹必须是完整路径（盘符路径或 UNC 路径）。": "The destination must be an absolute drive or UNC path.",
    "目标路径不是文件夹。": "The destination path is not a folder.",
    "源文件在处理过程中发生变化，已保留源文件，请重新分析。": "The source changed during the transfer and was kept. Analyze it again."
  };
  const patterns = [
    [/^已选 (\d+) 首$/, (_, n) => `${n} selected`],
    [/^已选 (\d+) \/ (\d+) 首（含子文件夹）$/, (_, n, all) => `${n} / ${all} selected (including subfolders)`],
    [/^勾选可疑 · ≥ (\d+) 分$/, (_, n) => `Select suspicious · ≥ ${n}`],
    [/^移动／复制(?: · (\d+) 首)?$/, (_, n) => `Move / copy${n ? ` · ${n}` : ""}`],
    [/^批量分析不限数量 · (2D|3D) 对比最多 (\d+) 首$/, (_, mode, n) => `Unlimited batch analysis · ${mode}: up to ${n} tracks`],
    [/^(生成对比|分析所选)(?: · (\d+) 首)?( ↗)?$/, (_, action, n, arrow) => `${action === "生成对比" ? "Compare" : "Analyze selected"}${n ? ` · ${n}` : ""}${arrow || ""}`],
    [/^设置已保存 · (\d+) 个分析进程 · 可疑勾选阈值 ≥ (\d+) 分。$/, (_, n, score) => `Settings saved · ${n} processes · Selection threshold ≥ ${score}.`],
    [/^默认 (\d+) 个进程（根据 CPU 核心数，上限为 4）。可设置 1–(\d+)。$/, (_, n, max) => `Default: ${n} processes (CPU-based, capped at 4). Allowed: 1–${max}.`],
    [/^已勾选 (\d+) 首评分 ≥ (\d+) 分的曲目（含搜索隐藏项），已替换之前的勾选。$/, (_, n, score) => `Selected ${n} tracks scoring ≥ ${score}, including hidden results. Previous selection replaced.`],
    [/^本次处理已勾选且评分 ≥ (\d+) 分的 (\d+) 首曲目。$/, (_, score, n) => `Process ${n} selected tracks scoring ≥ ${score}.`],
    [/^相对路径根目录：(.+)（目标路径不包含该根目录的名称）$/, (_, folder) => `Relative-path root: ${folder} (the root folder name is not added to the destination)`],
    [/^开始(复制|移动) (\d+) 首$/, (_, action, n) => `${action === "复制" ? "Copy" : "Move"} ${n} tracks`],
    [/^正在(复制|移动) (\d+) 首曲目…$/, (_, action, n) => `${action === "复制" ? "Copying" : "Moving"} ${n} tracks…`],
    [/^(复制|移动)完成 (\d+) 首 · 未完成 (\d+) 首(。详细结果见操作弹窗。)?$/, (_, action, n, failed, extra) => `${action === "复制" ? "Copied" : "Moved"} ${n} · Incomplete ${failed}${extra ? ". See the transfer dialog for details." : ""}`],
    [/^(已复制，源文件未删除|已复制|已移动|失败)：(.+) → (.+?)(?:；(.+))?$/, (_, label, from, to, error) => `${translate(label)}: ${from} → ${to}${error ? `; ${translate(error)}` : ""}`],
    [/^分析详情：(.+)$/, (_, name) => `Analysis details: ${name}`],
    [/^选择文件夹 (.+)（含全部子文件）$/, (_, folder) => `Select folder ${folder} (all descendants)`],
    [/^(.+) · 勾选包含全部子文件（含搜索隐藏项）；颜色取已完成文件中的最高评分$/, (_, folder) => `${folder} · Selection includes hidden descendants; color shows the highest completed score`],
    [/^(未见异常|可疑|有损编码)( \d+)?$/, (_, label, score) => `${translate(label)}${score || ""}`],
    [/^(未分析|等待分析|正在分析…|分析失败 · 可重试|证据不足|已知有损格式 · 不适用|未检测出明显特征|检测出可疑特征|未知状态) · (\d+)\/100$/, (_, label, score) => `${translate(label)} · ${score}/100`],
    [/^已分析 (\d+)\/(\d+)( · 可疑 \d+)?( · 最高 \d+)?( · 失败 \d+)?( · 分析中)?$/, (_, n, all, suspicious, worst, failed, pending) => `Analyzed ${n}/${all}${suspicious ? ` · Suspicious ${suspicious.match(/\d+/)[0]}` : ""}${worst ? ` · Max ${worst.match(/\d+/)[0]}` : ""}${failed ? ` · Failed ${failed.match(/\d+/)[0]}` : ""}${pending ? " · Running" : ""}`],
    [/^找到 (\d+) 首曲目。勾选文件或文件夹，点击「分析所选」。$/, (_, n) => `Found ${n} tracks. Select files or folders, then click Analyze selected.`],
    [/^(\d+) \/ (\d+) · 正在分析 (\d+) 首( · 等待正在处理的曲目完成后停止)?$/, (_, n, all, active, stop) => `${n} / ${all} · Analyzing ${active} tracks${stop ? " · Stopping after active tracks finish" : ""}`],
    [/^(已停止|分析完成) · 已处理 (\d+) \/ (\d+) · 失败 (\d+)(。结果已标在文件树上，点击「详情」查看依据。)?$/, (_, status, n, all, failed, extra) => `${status === "已停止" ? "Stopped" : "Analysis complete"} · Processed ${n} / ${all} · Failed ${failed}${extra ? ". Open Details in the library to review evidence." : ""}`],
    [/^正在准备对比 (\d+) \/ (\d+)：(.+) · 首次读取将覆盖整首音频$/, (_, n, all, name) => `Preparing comparison ${n} / ${all}: ${name} · First analysis reads the full track`],
    [/^已显示 (\d+) 首曲目 · 全曲分析 · (统一坐标与色阶|拖动图表旋转视角)( · (\d+) 首为静音)?$/, (_, n, mode, silent, count) => `Showing ${n} tracks · Full-track analysis · ${mode === "统一坐标与色阶" ? "Shared axes and color scale" : "Drag charts to rotate"}${silent ? ` · ${count} silent` : ""}`],
    [/^(\d+) 首已显示，(\d+) 首分析失败。左侧可查看具体原因，重新生成可重试。$/, (_, n, failed) => `${n} tracks displayed; ${failed} failed. Review the library errors and compare again to retry.`],
    [/^图表渲染失败：(.+)。可尝试 2D 模式。$/, (_, error) => `Chart rendering failed: ${translate(error)}. Try 2D mode.`],
    [/^图表渲染失败：(.+)。请尝试切换 2D。$/, (_, error) => `Chart rendering failed: ${translate(error)}. Try switching to 2D.`],
    [/^(频谱|时频图) · PNG 预览$/, (_, chart) => `${chart === "频谱" ? "Spectrum" : "Spectrogram"} · PNG preview`],
    [/^曲目 (\d+)$/, (_, n) => `Track ${n}`],
    [/^约 ([\d.]+) kHz 出现持续高频截止；截止特征强度 ([\d.]+%)。$/, (_, cutoff, confidence) => `A sustained cutoff appears around ${cutoff} kHz; cutoff feature strength: ${confidence}.`],
    [/^([\d.]+%) 的非零样本落在 16-bit 网格上，疑似高位深补零。$/, (_, fraction) => `${fraction} of nonzero samples align to a 16-bit grid, suggesting padded bit depth.`],
    [/^(.+) 没有符合阈值的当前分析结果，请重新分析或调整勾选。$/, (_, name) => `${name} has no current analysis meeting the threshold. Analyze again or adjust the selection.`],
    [/^无法分析 (.+?)：(.+)$/, (_, name, reason) => `Cannot analyze ${name}: ${translate(reason)}`],
    [/^(无法扫描文件夹|无法处理曲目|音频无法解码|导出失败|未能恢复分析进程数)：(.+)$/, (_, action, reason) => `${{"无法扫描文件夹":"Cannot scan folder","无法处理曲目":"Cannot transfer tracks","音频无法解码":"Cannot decode audio","导出失败":"Export failed","未能恢复分析进程数":"Cannot restore process count"}[action]}: ${translate(reason)}`],
    [/^请求失败 \((\d+)\)$/, (_, code) => `Request failed (${code})`],
    [/^目标已存在，未执行任何文件操作：(.+)$/, (_, path) => `Destination already exists; no transfers were performed: ${path}`],
    [/^多首曲目具有相同目标路径：(.+)。请保留目录结构或更换目标。$/, (_, path) => `Multiple tracks share a destination: ${path}. Preserve folders or choose another destination.`],
    [/^曲目不在本次扫描根目录内：(.+)$/, (_, path) => `Track is outside the scanned root: ${path}`],
    [/^目标子目录指向目标文件夹之外：(.+)$/, (_, path) => `A destination subfolder points outside the destination root: ${path}`],
    [/^已复制，但无法删除源文件：(.+)$/, (_, error) => `Copied, but the source could not be removed: ${error}`],
    [/^(.+)；无法清理未完成的目标文件：(.+)$/, (_, error, cleanup) => `${translate(error)}; could not remove the incomplete destination: ${cleanup}`]
  ];

  function translate(value, target = language) {
    const source = String(value);
    if (target !== "en") return source;
    const key = source.trim();
    let result = Object.hasOwn(english, key) ? english[key] : undefined;
    if (result === undefined) {
      for (const [pattern, replace] of patterns) {
        if (pattern.test(key)) { result = key.replace(pattern, replace); break; }
      }
    }
    return result === undefined ? source : source.replace(key, () => result);
  }
  function text(node, source) {
    const child = document.createTextNode(translate(source));
    child.lensSource = String(source);
    node.replaceChildren(child);
  }
  function attribute(node, name, source) {
    node.lensAttributes ??= {};
    node.lensAttributes[name] = String(source);
    node.setAttribute(name, translate(source));
  }
  function localize(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (["SCRIPT", "STYLE"].includes(node.parentElement?.tagName) || !node.nodeValue.trim()) continue;
      node.lensSource ??= node.nodeValue;
      node.nodeValue = translate(node.lensSource);
    }
    for (const node of root.querySelectorAll("[title], [placeholder], [aria-label], [alt]")) {
      for (const name of ["title", "placeholder", "aria-label", "alt"]) {
        if (node.hasAttribute(name)) attribute(node, name, node.lensAttributes?.[name] ?? node.getAttribute(name));
      }
    }
  }
  function resolveLanguage(query, saved) {
    return [query, saved].find(value => value === "en" || value === "zh-CN") || "en";
  }
  function setLanguage(value) {
    language = value;
    document.documentElement.lang = language;
    document.title = translate(originalTitle);
    localize(document.body);
    document.getElementById("interface-language").value = language;
    try { localStorage.setItem("lossless-lens-language", language); } catch { /* Optional preference. */ }
  }
  function init() {
    let saved;
    try { saved = localStorage.getItem("lossless-lens-language"); } catch { /* Optional preference. */ }
    originalTitle = document.title;
    setLanguage(resolveLanguage(new URLSearchParams(location.search).get("lang"), saved));
  }
  return {translate, text, attribute, init, setLanguage, resolveLanguage};
})();
if (typeof module !== "undefined") module.exports = LensI18n;
