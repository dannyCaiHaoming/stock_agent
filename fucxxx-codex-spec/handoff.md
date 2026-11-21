# 当前开发交接

更新时间：2026-11-22（JST）
主会话／协调负责人：Claude Code（Opus）；Claude 额度不足时由 Codex CLI（`gpt-6.2-astra`）接任，接任前先核对本文件与实际 git 状态。
项目根与主工作区：`/Users/caihaoming/Documents/stock_agent`，分支 `main`（不开分支）。
本文件由主会话维护；子会话返回本区结果和状态，不更新此处。

## 当前焦点
- 当前 MVP／任务：Decision-First 路线 P0（冻结协议与清理）；P1 子设计尚未建立（计划位置 `fucxxx-codex-spec/designs/decision-card.md`）。
- 核心目标：给定股票、时点、持仓，每次给出明确动作与同口径的概率、收益、风险、复核条件；新账本用真实前瞻结果检验持仓保护是否优于维持现状和简单规则。
- 当前环节：设计已定稿，等待用户决定后进入 P0。
- 最新有效设计与活动 plan：总设计 [docs/design-decision-first-2026-11-21.md](../docs/design-decision-first-2026-11-21.md)；路线 [docs/roadmap.md](../docs/roadmap.md) “当前路线”一节；活动 plan：无。
- 最近已核对的代码基线与相关未提交改动：`main` 2d43930；本文件、AGENTS.md 协作段、`.codex/agents/dev_implementer.toml` 为本轮新增，未提交。
- 项目文档入口：`docs/roadmap.md`。
- 项目有效指令与 Skill 主入口：`AGENTS.md`（CLAUDE.md 引入它）；Skill 见 AGENTS.md “开发协作”一节。
- Skill 包根与已核实的阶段能力入口：Claude Code `~/.claude/skills/`，Codex `~/.codex/skills/`；init／design／plan 均为同包根，2026-11-22 两处均实际读取到 `fucxxx-codex-spec/SKILL.md`。

## 活动工作
| 工作 | 执行上下文／真实 ID | 工作区 | 活动 plan／任务依据 | 当前状态 | 交付／证据位置 |
| --- | --- | --- | --- | --- | --- |
| （无） | | | | | |

## 待处理
- 等待用户决定：设计文档 §7 的 5 项——首版承诺范围；减仓后资金去向（现金／板块 ETF）；扫描是否扩到 S&P 500；是否暂停 `forward-run.sh` 与 `forward-groups.sh` 定时运行；下行保护愿意牺牲多少收益。
- 实际阻塞：P0 依赖上述决定；其余无。
- 讨论记录：`.local/runs/design-dialog-20261121/`（Codex Astra 两轮，本地忽略目录）。

## 下一步
- 下一项具体动作及前提：用户回答 §7 后，主会话写 P0 协议登记（纸面数量、资金去向、成本、三个时间、期限映射、基线、最小有用增益）并做设计文档 §6 的清理；随后写 P1 子设计与实施 plan，把 T1（开盘口径）、T2（`decision/v2` 记录与工具）、T3（事件分组）分派给实现者并行。
- 谁负责：主会话（设计、plan、复核、回写）；实现者见 AGENTS.md “开发协作”。
- 当前授权允许继续到哪里：P0 完成后停下，交用户确认再进入 P1。

## 收口状态
- commit／push：设计文档与路线已提交（e99f743、2d43930），未推送；本轮协作配置未提交。
