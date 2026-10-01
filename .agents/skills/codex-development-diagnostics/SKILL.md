---
name: codex-development-diagnostics
description: 解释本仓库 Codex 环境、加载、运行或研究数据交接为什么失败，按现有证据定位首处分歧；不用于普通编辑、交接设计、验收收尾或产品投资研究。
---

# Codex 开发诊断

本 Skill 属于开发控制面。它只整理确定性证据和首处分歧，不进入 `product/` Agent Package，不生成投资观点，也不替代 `portfolio-council`。

## 输入

按任务读取 repo_root 或用户指定的历史 run_dir；普通代码检查不要求先准备运行、权限探针或新证据目录。只有执行获授权的确定性测试时才设置可写临时目录；只读复核不创建运行。缺少具体证据时报告该项缺口，不阻塞无关检查。

## 诊断顺序

先选分支：路径、权限、加载或启动问题使用下面的环境顺序及[开发环境](../../../docs/development/environment.md)对应章节；研究草稿、引用、收据、报告交接问题才读[研究交接诊断](references/research-handoff-diagnostics.md)。不强制两路全读，也不要求先调用其他Skill。

1. 在当前 Codex 环境读取代码、配置和现有产物；获授权时使用 `scripts/council-dev.py self-check check-run` 或 `self-check trace-check`。不得自动调用 codex sandbox、doctor、preflight 网络检查或完整 Council。
2. 按需读取当前授权运行及声明依赖中的必要材料：如 `run_manifest.json`、`invocation/prompt.txt`、`invocation/environment-manifest.json`、事件、stderr、`invocation/process-result.json`、`decision_trace.json` 和既有 execution-proof。先取相关片段，不默认全读；缺失文件记录为缺口，不补造。
3. 将资源状态明确区分为 `DISCOVERED`、`CONFIG_VALIDATED`、`LOAD_VERIFIED`。文件存在只能证明发现；只有实际 Prompt 输入、Hook 或 MCP/命令事件及匹配 hash 才能证明加载。
4. 找出有证据支持的第一个分歧，输出 `FIRST_DIVERGENCE`、`ROOT_CAUSE`或尚缺的证明、实际存在的`failure_code`及证据位置。身份或内容一致性相关时才核对并记录所属契约的完整hash；没有根因证明时不要把第一条异常直接认作根因。
5. 环境错误与产品断言失败分别报告；prepare-only 不得描述为成功运行。

## 严格边界

- 不遍历全局用户消息、私人历史会话、SQLite内容或无关任务产物。允许读取当前授权运行及声明依赖的必要事件/错误片段，不笼统禁止诊断所需的日志，也不全量转储。
- 不复制、打印或持久化 `auth.json`、令牌、cookie、密钥和用户数据库；诊断记录只保留必要非敏感依据，避免原始工具参数或日志中的凭据外泄。
- 不自动修改源码、配置、Skill、Agent 或生产版本指针。
- 不自动重跑 LLM、Replay、Regression、Calibration、Ablation 或 Release Gate。Smoke/Execution Replay 缺口交回当前执行流程，核对已有范围、权限和预算后由宿主统一入口执行；缺少授权时才请求，不重复索取已有授权。
- 全进程源码强制只读仍为 UNVERIFIED，不作为本Skill保证；保留原生权限与业务安全，源码hash未变化不等于隔离证明。独立复核不创建新沙箱。
- 不自动提权、关闭沙箱、开放整个 `~/.codex`，也不因诊断失败而安装依赖。
- 不自动归档、提交或推送 Git。

仅诊断请求以结论和最小建议结束，不实施修复。若诊断是已授权实现/修复的一部分，将结论交回原实施流程继续范围、权限和预算内工作；本Skill不新增权限，也不撤销已有授权。真实越界、关键选择缺失或项目既有最终批准要求才暂停相关动作，不因阶段汇报反复等待“继续”。
