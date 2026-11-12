# Lossless Lens 项目地图

## 本次发布授权（2026-11-13）
- 用户已明确允许PR、push及调整origin禁推地址和pre-push保护，覆盖下文对本次发布的旧禁令。
- 仅发布 `integration/ll-20261112` 到 `origin` 同名分支，推送时显式设置 `LOSSLESS_LENS_ALLOW_PUBLISH=1`；默认仍禁止推送，master不可推送或合并，不部署。其他worktree仍保持各自禁推设置。

本项目采用 W1 PM → W2 模块 → W3 开发/独立审核。保持既有 FastAPI 与原生 JavaScript 结构。

## 管理规范
- 管理目录：`D:/WorkSpace/Agent-Skill/lossless-lens-mgmt-20261112`。
- 先读其 `project/conventions.md`、`project/environment.md` 与自己的契约/owns；恢复按其 README。
- 用户原文及 PA：`project/charter.md`；跨模块决定：`project/decisions/`。
- 主仓库 master 保持 a89d744dd46056c62681b9039478cf3b566af697；开发基线为 `baseline/ll-20261112`。
- 最终停人工终审；禁止 master 合并、push、PR、部署、付费应用 API；不删除已有任务/worktree/分支。

## 环境与检查
- 项目 Python：`C:/Users/UCUNI/anaconda3/envs/flac-forensics/python.exe`。
- 管理脚本 Python：`C:/Users/UCUNI/anaconda3/python.exe`；禁止裸 python/pip。
- 新 worktree 先执行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/configure_worktree.ps1`，仅用于已授权项目 worktree。
- 冒烟：`& 'C:/Users/UCUNI/anaconda3/envs/flac-forensics/python.exe' scripts/project_check.py --smoke`。
- 本地完整检查：同解释器执行 `scripts/project_check.py`；包括语法/差异检查、现有全部 Python/JS 测试与应用装配检查。
- 不依赖 Kandev Copy files；解释器已明确，`.conda-env` 不提交。
- `LOSSLESS_LENS_REAL_AI`、`LOSSLESS_LENS_EXTERNAL_ACTIONS` 默认关闭；检查入口拒绝打开，额度为0。当前无真实AI调用入口；新增外部调用必须先升级PM，不能因设置开关自行执行。

## 路径与单写者
- selection：`web/library-model.js`、`tests/test_library_model.js`。
- analysis-details：`web/analysis-queue.js`、`tests/test_analysis_queue.js`。
- folder-transfer：整理后端及共享 `web/app.js`、`web/index.html`、`web/i18n.js`、CSS；精确清单见charter。
- PM环境文件：本文件、`scripts/`、`.githooks/`；其他角色不得擅改检查和禁推规则。
- 开发上报与审核按environment运行管理目录 `tools/check_owns.py`；越界先升级，不修改契约绕过。
- UI为局部改进：按impeccable局部流程，修改前读craft-floor，保留实际交互与前后截图；不要重设计或引入框架。

## 安全与调度
- 只用临时生成曲库测试；绝不访问用户真实曲库做文件操作。
- 总会话24、workspace同时运行/启动8、开发2、守护预留1；启动/刷新/自动审核合并前经PM集中放行。
- 依赖未满足停待开发，不占开发WIP；每开发任务独立worktree；审核新会话。
- 端口用 `--port 0 --no-browser`，只监听127.0.0.1，记录实际端口与进程；退出清理自建临时资源。
- 时间取系统时钟；先写意图后外部动作；结论只用pass/fail/unverified，部分交付写partial。
