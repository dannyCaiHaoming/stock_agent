# 当前开发交接

更新时间：2026-11-28（JST）
主会话／协调负责人：Claude Code（Opus）；Claude 额度不足时由 Codex CLI（`gpt-6.2-astra`）接任，接任前先核对本文件与实际 git 状态。
项目根与主工作区：`/Users/caihaoming/Documents/stock_agent`，分支 `main`（不开分支）。
本文件由主会话维护；子会话返回本区结果和状态，不更新此处。

## 当前焦点
- 当前路线：**交易计划生命周期**（2026-11-28 起），总设计 [docs/design-position-lifecycle-2026-11-28.md](../docs/design-position-lifecycle-2026-11-28.md)，已确认（§8 用户已答）。
- 当前 MVP：L1 可用性，子设计 [designs/position-lifecycle.md](designs/position-lifecycle.md)，plan [plans/position-lifecycle-impl.md](plans/position-lifecycle-impl.md)（返工 [rework1](plans/position-lifecycle-rework1.md)、[rework2](plans/position-lifecycle-rework2.md)）。
- 状态：实现完成（Sonnet 5.5，返工 2 次）；319 个离线测试通过；三个固定用例 A/B/C 通过（Codex terra 回放，4 次模型调用）；**真实前瞻用例：NVDA，12-04（10-Q 截止）后用修订后的 trade-plan 重跑**（11-28 两次实时尝试 NVDA not_formed、PL wait；与 astra 讨论后修订 Skill）。验收记录 [evidence/position-lifecycle-acceptance.md](evidence/position-lifecycle-acceptance.md)。
- 前一路线 Decision-First：P0 完成并推送（021199f）；P1 代码完成并提交（0cb36e7、5ea1d8c），第二版盲读材料在 [evidence/decision-card-blindread.md](evidence/decision-card-blindread.md)，**用户结论待记录**；P2 协议 v1 保留、暂不开跑（用户：先做完 P1）。
- 代码基线：`main` 5ea1d8c；本轮改动全部未提交（见下）。
- Skill 包根与阶段能力入口：Claude Code `~/.claude/skills/`，Codex `~/.codex/skills/`；design 能力 2026-11-28 实际读取。
- 模型分工（用户 2026-11-28 重申）：计划与复核 Opus 5.5；实现 Sonnet 5.5（一度误派 Haiku，已取消，未写入文件）；独立复核 Codex `gpt-6.2-astra`。

## 本轮未提交改动
- 新增：`product/deterministic/plan_math.py`、`product/mcp/plan_ledger.py`、`scripts/score-plans.py`、`product/skills/trade-plan/`、`product/skills/plan-review/`、`tests/test_plan_math.py`、`tests/test_plan_ledger.py`、`tests/test_plan_integration.py`、`docs/design-position-lifecycle-2026-11-28.md`、`fucxxx-codex-spec/designs/position-lifecycle.md`、`plans/position-lifecycle-*.md`、`evidence/position-lifecycle-*.md`。
- 修改：`product/mcp/server.py`（8 个计划工具）、`product/mcp/data_tools.py`（拆股还原只算响应获取日之前的拆股）、`scripts/dev-research.sh`（`--plan`/`--review`/`--seed-plans`、模式互斥、`STOCK_AGENT_RUN_MODEL`）、`tests/test_stock_data_tools.py`、`AGENTS.md`（Skill 列表）、`docs/roadmap.md`、`docs/design-decision-first-2026-11-21.md`（状态行）、本文件。

## 本轮讨论记录（均在 `.local/runs/`，不入库）
- `brainstorm-20261128/`：三模型对 P2 开跑缺口的头脑风暴与汇总。
- `direction-research-20261128/`：三模型联网方向研究（学术证据、市场方案与仓库诊断、优秀交易者）与汇总；用户否决了其中“纯规则因子”式的第一轮求证。
- `lifecycle-design-20261128/`：主会话草案 `proposal.md` 与 astra 审计 `astra-audit.md`、代码复核与复查。
- `nvda-dialog-20261128/`：Opus × astra 两轮 NVDA 事件讨论与汇总（wait；12-03 听证、12-04 10-Q 截止）。

## 活动工作
| 工作 | 执行上下文 | 工作区 | 依据 | 当前状态 | 交付／证据 |
| --- | --- | --- | --- | --- | --- |
| L1 H1–H3 + 返工 1、2 | Sonnet 5.5 子 Agent | 共享 main | plans/position-lifecycle-*.md | 完成，主会话复核测试通过 | evidence/position-lifecycle-h1/h2/h3.md |
| L1 Skills | 主会话 | 共享 main | 子设计 | 完成 | product/skills/trade-plan、plan-review |
| L1 代码复核 | Codex astra（两轮） | 只读 | — | 完成；返工 2 未再独立复查 | .local/runs/lifecycle-design-20261128/astra-code-review.md、astra-recheck.md |
| L1 验收 | 主会话 | `.local/runs/*L1-*`、`l1-acceptance-20261128/` | 子设计“验收” | A/B/C 通过；真实前瞻待用户 | evidence/position-lifecycle-acceptance.md |

## 待处理
- 12-04 之后：对 NVDA 重跑 `scripts/dev-research.sh codex NVDA --tag L1-live-plan --plan "…"`，先查 Q3 10-Q 是否已交（NT 10-Q 则 12-09）；形成计划后请用户复述失效条件。
- 等待用户：P1 第二版盲读结论。
- 等待用户：在 Codex App 中停用 automation `stock-agent-2`。
- 已核实的事实（2026-11-28）：
  - SEC“缓存陈旧”是显示问题：UNH submissions 的 `.checked` 为 2026-11-21T16:05Z，内容未变所以 `retrieved_at` 停在 11-13；`list_filings` 未输出 `checked_at`。
  - 唯一真实账本记录 UNH 的 `model` 为模型自报的 `gpt-6`，`code_version.dirty=true`。
  - `score-decisions.py` 读 `tier` 与 `selection`，但 `decision_ledger.py` / `decision-record.py` 都不写。
  - 每日预期快照缺 11-02～11-06 与 11-20 至今。
  - 协议 §6 要求 W ≥ 3L，P2 最早约 48 周后才有判定，roadmap 原“约 32 周”不成立。
- 以上 P2 相关项只在 P2 开跑前需要处理。

## 下一步
- 12-04 之后 NVDA 重跑：`trade-plan` 出计划→ 用户复述失效条件 → 下一次公开事件后 `plan-review` → `score-plans.py` 结算 → 回填验收记录，L1 收口。
- L1 收口后：用户决定 L2（20 个候选或 8 週）与 P2 是否开跑。
- 当前授权：实现与验收到 L1；commit 需用户同意。
