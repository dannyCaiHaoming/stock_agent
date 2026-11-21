# 当前开发交接

更新时间：2026-11-22（JST）
主会话／协调负责人：Claude Code（Opus）；Claude 额度不足时由 Codex CLI（`gpt-6.2-astra`）接任，接任前先核对本文件与实际 git 状态。
项目根与主工作区：`/Users/caihaoming/Documents/stock_agent`，分支 `main`（不开分支）。
本文件由主会话维护；子会话返回本区结果和状态，不更新此处。

## 当前焦点
- 当前 MVP／任务：P0（冻结协议与清理）已完成，下一步是 P1 日用决策卡。P1 子设计尚未建立，计划位置 `fucxxx-codex-spec/designs/decision-card.md`。
- 核心目标：给定股票、时点、持仓，每次给出明确动作与同口径的概率、收益、风险、复核条件；新账本用真实前瞻结果检验持仓保护是否优于维持现状和简单规则。
- 当前环节：P0 收口，等待用户确认后进入 P1。
- 最新有效设计与活动 plan：
  - 总设计：[docs/design-decision-first-2026-11-21.md](../docs/design-decision-first-2026-11-21.md)（已确认）；
  - 协议：[evals/forward/decision-protocol-v1.md](../evals/forward/decision-protocol-v1.md)（P0 冻结，细则以它为准）；
  - 路线：[docs/roadmap.md](../docs/roadmap.md)；
  - 活动 plan：无。
- 最近已核对的代码基线：`main` 00b2825；P0 改动见“收口状态”。
- 项目文档入口：`docs/roadmap.md`。
- 项目有效指令与 Skill 主入口：`AGENTS.md`“开发协作”一节。
- Skill 包根与已核实的阶段能力入口：Claude Code `~/.claude/skills/`，Codex `~/.codex/skills/`；init／design／plan 均同包根（2026-11-22 实际读取）。

## 活动工作
| 工作 | 执行上下文／真实 ID | 工作区 | 活动 plan／任务依据 | 当前状态 | 交付／证据位置 |
| --- | --- | --- | --- | --- | --- |
| （无） | | | | | |

## 待处理
- 等待用户：在 Codex App 中停用 automation `stock-agent-2`（每周六 06:30 北京时间运行 `forward-run.sh`）。脚本内已有暂停开关，不停用也不会跑模型，但仍会唤醒一次 Codex。
- P1 要先核对的待验证项（来自协议与复核）：
  - terra 低档 11 例与 E1 定义的实际重合数（只作描述）；
  - 生成 S&P 500 成员快照与板块 ETF 映射快照；
  - 旧账本到期评分实跑（`score-forecasts.py` 的 `no_lean` 只做过静态与函数级核对）。
- 复核记录：`.local/runs/p0-review-20261122/`（Codex Astra 两轮：answer.md、answer2.md）。

## 下一步
- 下一项具体动作：用户确认后写 P1 子设计 `designs/decision-card.md` 与实施 plan `plans/decision-card-impl.md`，然后分派任务：
  - T1 开盘口径重算 key_moments；
  - T2 `decision/v2` 记录与保存工具（负责 `server.py` 的全部注册）；
  - T3 事件分组判定；
  - T1–T3 分别交 Sonnet 子 session 并行；
  - T4 `score-decisions.py`（依赖 T1、T2）；
  - T5 决策模式 Skill（主会话写）；
  - T6 12 个冻结案例与盲读验收。
- 谁负责：主会话（设计、plan、复核、回写）；实现者见 AGENTS.md“开发协作”。
- 当前授权允许继续到哪里：P0 已收口；P1 需要用户说开始。

## 收口状态
- 总设计已回写：§7 标为已确认；E1/E2 重叠规则改为 E2 优先，并指向协议。
- 路线已回写：P0 标完成，暂停方式写明。
- P0 改动（未提交）：
  - 协议 `evals/forward/decision-protocol-v1.md`（新）；
  - `investment-decision` SKILL：去掉默认 BUY 与 > 0.5 强制，说明所选方向概率；
  - `decision_log.py`、`server.py`、`stock-research` SKILL：允许 0.5，拒收 < 0.5；
  - `score-forecasts.py`：二元目标 0.5 不计命中；
  - `tests/test_stock_data_tools.py`：新增测试，在临时目录中运行；
  - `forward-run.sh` 暂停开关；`evals/forward/README.md` 暂停说明；
  - AGENTS.md / CLAUDE.md 的 learnings 标为已确认。
- 验证：`tests.test_stock_data_tools` 26 个测试通过；`forward-run.sh` 实跑输出 FORWARD_PAUSED，退出码 0；§8 手算例由主会话与 Codex 分别复算一致。
- 清理：测试曾向 `.local/data/` 误写一条 AAA 记录，已删除（文件与目录都是本次新建的），测试已改为在临时目录中运行。
- commit／push：P0 改动未提交。
