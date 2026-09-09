---
name: codex-development-diagnostics
description: 诊断本仓库 Codex 开发、测试或复核环境中的路径、权限、配置加载和启动失败；只在用户要求排查环境或运行入口时使用，不用于股票研究或产品 CIO 决策。
---

# Codex 开发环境诊断

本 Skill 属于开发控制面。它只整理确定性证据和首处分歧，不进入 `product/` Agent Package，不生成投资观点，也不替代 `portfolio-council`。

## 输入

按任务读取 repo_root 或用户指定的历史 run_dir；普通代码检查不要求先准备运行、权限探针或新证据目录。只有执行获授权的确定性测试时才设置可写临时目录；只读复核不创建运行。缺少具体证据时报告该项缺口，不阻塞无关检查。

## 诊断顺序

1. 在当前 Codex 环境读取代码、配置和现有产物；获授权时使用 `scripts/council-dev.py self-check check-run` 或 `self-check trace-check`。不得自动调用 codex sandbox、doctor、preflight 网络检查或完整 Council。
2. 只读取当前运行目录中的 `run_manifest.json`、`invocation/prompt.txt`、`invocation/environment-manifest.json`、`invocation/codex-events.jsonl`、`invocation/codex-stderr.log`、`invocation/process-result.json`、`decision_trace.json` 和既有 execution-proof。
3. 将资源状态明确区分为 `DISCOVERED`、`CONFIG_VALIDATED`、`LOAD_VERIFIED`。文件存在只能证明发现；只有实际 Prompt 输入、Hook 或 MCP/命令事件及匹配 hash 才能证明加载。
4. 找出事件流中第一个与预期不同的位置，输出 `FIRST_DIVERGENCE`、`ROOT_CAUSE`、`failure_code`、证据路径和完整 hash。
5. 环境错误与产品断言失败分别报告；prepare-only 不得描述为成功运行。

## 严格边界

- 不读取或导出全局用户消息、历史会话、SQLite 内容、日志正文或其他任务产物。
- 不复制、打印或持久化 `auth.json`、令牌、cookie、密钥和用户数据库；只允许记录白名单状态、路径和 hash。
- 不自动修改源码、配置、Skill、Agent 或生产版本指针。
- 不自动重跑 LLM、Replay、Regression、Calibration、Ablation 或 Release Gate。Smoke/Execution Replay 补跑只报告缺口，由宿主 Terminal 统一入口在另行授权后执行。
- 全进程源码强制只读为 UNVERIFIED，排除在本 Change 完成保证之外；保留原生权限与业务安全，源码 hash 未变化不等于隔离证明。独立复核不创建新沙箱。
- 不自动提权、关闭沙箱、开放整个 `~/.codex`，也不因诊断失败而安装依赖。
- 不自动归档、提交或推送 Git。

完成后仅给出可审计诊断结论和下一项最小动作，由用户决定是否授权修复或补测。
