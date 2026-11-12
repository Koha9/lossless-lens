# CI 与 Windows 发布

## 触发时机

- 指向 `master` 的 PR：创建、更新提交或重新打开时运行 `CI`。
- `master` 推送：包括 PR 合并产生的提交，运行 `CI`。
- 手动运行 `CI`：验证所选分支；工作流合入默认分支后可从 Actions 页面启动。
- 推送 `v*` 标签：运行 `Release (Windows)`，复用同一套 CI 后发布 ZIP。
- 手动运行 `Release (Windows)`：只检查和打包，不创建或更新 Release。

CI 不设置路径过滤，文档或工作流修改也会产生检查结果。开发分支普通推送不重复运行；其开放 PR 的更新会触发检查。PR 新提交取消该 PR 的过期运行，master 与标签运行不会被 PR 取消。

## 检查组成

1. Windows 与 Ubuntu，Python 3.12、Node.js 24：显式安装并检查 FFmpeg/ffprobe，避免真实编解码测试因工具缺失被跳过；安装 `requirements-dev.txt`，运行未裁剪的 `scripts/project_check.py`。覆盖语法、差异、全部 Python/JavaScript 测试，以及临时 FLAC 的扫描、分析、静态资源和生命周期冒烟。
2. 两个平台检查都通过后，在 Windows 构建 ZIP。`build_onedir.ps1 -Zip` 已包含打包后 `LosslessLens.exe --help` 的真实启动检查。冻结解释器启用 UTF-8，中文帮助输出到管道时不依赖 runner 的默认 ANSI 编码。
3. 保存 `LosslessLens-windows-x64` artifact 14 天，PR 也可下载试用。缺少 ZIP 会令任务失败。
4. 只有标签推送的 Release 发布任务拥有 `contents: write`；它下载本次已验证产物，不重复构建。普通 CI 和手动发布检查只有读权限，不会自动合并 PR。

测试和打包使用 pip 缓存，缓存键包含全部 requirements 文件。CI 明确关闭真实 AI/外部业务调用，并在临时检出中设置禁推地址和仓库钩子，使现有检查器的安全约束原样生效；不依赖本机 Conda、真实曲库或持久凭据。

## 排查没有运行或失败

- 本项目旧工作流只响应 `v*` 标签，不能验证 PR 或合入 master。本配置合并后才适用于后续 master 提交，不会补发过去缺失的事件。
- PR 必须以 `master` 为目标；存在合并冲突时先解决冲突。`[skip ci]` 等 GitHub 跳过标记也会阻止运行。
- 测试必须安装 `requirements-dev.txt`，不能仅安装 Web 运行依赖。当前 Starlette 的 TestClient 需要 `httpx2`，开发依赖同时保留旧版本使用的 `httpx`。
- 在 PR 的 Checks 或 Actions 查看 `Checks (ubuntu-latest)`、`Checks (windows-latest)`、`Windows package`。检查失败会阻止打包，打包失败会阻止标签发布。
- CI 通过不等于配置了强制合并门禁。是否将上述检查设为分支保护的必需检查，是仓库策略；此变更不修改保护规则或启用自动合并。
