# MVP L1：交易计划生命周期——可用性

总设计依据：[docs/design-position-lifecycle-2026-11-28.md](../../docs/design-position-lifecycle-2026-11-28.md) §3–§5
设计：已定（§8 已由用户回答，2026-11-28；返工 1 规则已并入）；实现：完成（返工 2 次），319 个离线测试通过；验收：三个固定用例通过，真实前瞻用例待用户
更新时间：2026-11-28（JST）

## 当前核心目标
- 服务总设计的目标：Agent 帮用户在进场前写下可核实的理由、放弃理由的事实和预算亏损；新公开事实出现时回到原文复核；结束后能手算净损益和 R。
- 本 MVP 要交付的一个明确结果：用户能用一张“催化事件”模板，对一笔纸面普通股多头完成“计划 → 下一次公开事件 → 复核 → 结算”，并能复述失效条件。
- 最小验收链路：用户提出机会 → `trade-plan` Skill 写计划并冻结（`save_trade_plan`）→ 下一常规开盘纸面成交 → 新事实出现时 `plan-review` Skill 两步复核（`save_plan_review`）→ `scripts/score-plans.py` 输出三线结算，可手算复现。
- 必须保留的职责、正确性和边界：
  - 计划冻结早于模拟成交；R0 冻结后不变；版本只追加；
  - 所有提交的机会都有记录（含 WAIT、计划不成立、未成交、放弃、仍持有）；
  - 复核论点结论改变时必须有新的公开证据；
  - 同股重开取得新 `plan_id`，读取一律按 `plan_id`；
  - 纸面、只读；不接 Tiger；私人账户数据不进上下文。
- 本次不做：真实账户、加仓与多次建仓、每日事实提示脚本、skeptic 子 Agent、双跑稳定性、复权与分红处理、第二张模板、P2 扫描。

## 用户决定（2026-11-28）
| 问题 | 回答 | 本 MVP 的落地 |
|---|---|---|
| 持有期与持仓数 | 120 天之内，最多 8 只 | `horizon_cap_days` 必填，1–120 个日历日；同时进行中的计划最多 8 个 |
| 纸面优先、暂缓 Tiger | 接受 | 只做纸面 |
| L1 交付与预算 | 同意 | 约 2 个工程日；≤ 12 次模型调用 |
| P2 开跑 | 先做完 P1 | P2 不开跑；P1 第二版盲读收口后、L1 完成后再定 |
| 实施方式 | 按 fucxxx-codex-spec：design → plan → 执行 → 回补；计划 Opus 5.5，实现 Sonnet 5.5 | 代码由 Sonnet 子 Agent 实现；两个 Skill 由主会话写（判断规则属于设计契约） |

**Agent 建议的默认值**（用户未指定，可改）：
- 模板：L1 只用“催化事件”模板（财报、指引、重大公告之后的机会）。理由：仓库唯一通过检验的能力是读公司消息，复核也由公开事件触发。
- 纸面资金 100,000 美元，每笔风险预算默认 1,000 美元（1%），8 只同时最多承担 8%。
- 价格失效以**收盘**判定：某日收盘 ≤ 失效价，下一常规交易日开盘离场（不假设盘中按阈值价成交；跳空会超出预算）。
- 成本：每边按成交额 10 个基点。
- 价格用未复权开盘与收盘；分红不计；窗口内疑似拆股或大额分红时标记为“不可结算”。

## 现状与直接缺口
- 已有：`decision_ledger.py`（只追加记录、工具生成机械字段、回放时间口径）、`decision_scoring.py`（下一开盘成交 `entry_index`）、`data_tools.get_price_history`、`classify_decision_event`、`list_filings`、`get_market_context`、`get_news_history`、`dev-research.sh` 的 `--decision` 与 `--seed-decisions` 模式。
- 缺：计划记录与工具、风险算术、三线结算、计划与复核两个 Skill、宿主调试入口。
- 取舍：新建独立的 `trade_plans.jsonl`，不扩展 `decision/v2`。`decision/v2` 的固定窗口、`w0/w1` 和协议 v1 评分口径与整笔损益不同，合并会改变 P2 的检验对象（总设计 §4）。

## 设计与接口

### 记录：`<data_dir>/trade_plans.jsonl`（只追加）与 `<data_dir>/plan-reports/<YYYY-MM-DD>/`
`data_dir` 由 `settings.data_dir()` 决定（默认 `.local/data`，调试运行为运行目录）。每行有 `kind`：

| kind | 何时写 | 关键字段（工具生成的字段标 *） |
|---|---|---|
| `candidate` | 每个用户提交的机会；`save_trade_plan` 自动写一条 `outcome=plan` | `candidate_id`*、`ticker`、`created_at`*、`outcome`（plan / wait / not_formed）、`reason`、`plan_id`（outcome=plan 时）、`replay`* |
| `plan` | 计划冻结 | 见下 |
| `revision` | 新事实改变之后的条件 | `plan_id`、`version`*（从 2 起）、`effective_at`*、`reason`、`sources`、`changes`（只允许 `price_invalidation`、`hold_basis`、`review_dates`、`abandon_facts`） |
| `review` | 每次复核 | `review_id`*、`plan_id`、`reviewed_at`*、`thesis_verdict`、`evidence`、`action`、`action_reason`、`plan_deviation`、`report_path`*、`report_sha256`* |
| `choice` | 用户对计划或复核的选择 | `plan_id`、`ref_id`（plan_id 或 review_id）、`choice`（followed / declined / abandoned）、`note`、`recorded_at`* |

`plan` 字段：
- 调用方提供：`ticker`、`template`（L1 只接受 `catalyst_event`）、`thesis`（一行）、`market_misread`、`catalyst`、`abandon_facts`（≥ 1 条，每条 `{document, fact}`，两项都非空）、`price_invalidation`（正数）、`entry_ref`、`entry_band`（`[lo, hi]`，`lo ≤ entry_ref ≤ hi`，`price_invalidation < lo`）、`risk_budget`（正数，默认 1000）、`hold_basis`、`review_dates`（≥ 1 个 YYYY-MM-DD，晚于决定日）、`horizon_cap_days`（1–120 的整数）、`report_markdown`、可选 `replay_as_of`、`host`、`model`。
- 工具生成（调用方传入即拒绝）：`schema="plan/v1"`、`plan_id`、`candidate_id`、`decided_at`、`frozen_at`（= 决定的有效时间）、`replay`、`shares_planned`、`r0`、`fill_rule="next_regular_open_after_frozen_at"`、`stop_rule="close_at_or_below_then_next_open"`、`cost_bps_per_side=10`、`code_version`、`model_recorded`（见下）、`report_path`、`report_sha256`。
- `shares_planned = floor(risk_budget / (entry_ref − price_invalidation))`，必须 ≥ 1；`r0 = (entry_ref − price_invalidation) × shares_planned`。
- `model_recorded`：环境变量 `STOCK_AGENT_RUN_MODEL` 有值时记 `{"value": 它, "source": "run_env"}`，否则记 `{"value": 调用方 model, "source": "self_reported"}`。

报告必含 `## ` 标题：`论点`、`催化剂`、`放弃理由的事实`、`价格失效位与预算亏损`、`持有依据与复核日`、`数据缺口`、`来源`。

复核报告必含：`论点复核`、`价格与动作`、`数据缺口`、`来源`。

### 规则（工具强制）
- **进行中**：计划已冻结、没有 `choice=abandoned`、没有 `action=EXIT` 的复核，且决定日 + `horizon_cap_days` 未过（按纽约日期）。这只看记录，不看价格。
- 同时进行中的计划 > 8 → `ACTIVE_PLAN_LIMIT`；同一 ticker 已有进行中的计划 → `ACTIVE_PLAN_EXISTS`（先复核离场或放弃）。
- `revise_trade_plan`：只能改上表四个字段；`r0`、`shares_planned`、`entry_*`、`thesis` 永不改变；新版本的 `price_invalidation` 可高可低，结算同时报告版本链。
- `save_plan_review`：
  - `thesis_verdict` ∈ strengthened / unchanged / weakened / broken / insufficient；`action` ∈ HOLD / REDUCE / EXIT；
  - `evidence` 每项 `{kind: filing|news|price|other, source, published_at (ISO 日期或时间), claim, original_condition}`；`published_at` 不得晚于复核的有效时间；
  - 与上一次复核（没有则与计划时视为 `unchanged`）相比 `thesis_verdict` 改变时，至少一项 evidence 的 `published_at` 晚于上一次复核（或计划冻结）的有效时间，否则拒绝 `NEW_EVIDENCE_REQUIRED`；
  - 复核有效时间必须晚于计划冻结时间，回放与否必须与计划一致；
  - REDUCE = 卖出剩余股数的一半（向下取整，≥ 1 股；只剩 1 股时 REDUCE 视同 EXIT）。
- 回放：与 `decision_ledger` 相同——`replay_as_of`（或 `STOCK_AGENT_REPLAY_AS_OF`）把有效时间钉在该日纽约 23:59:59，须是已结束的日期。
- `get_trade_plan(plan_id)`：返回冻结计划、版本链、当前有效版本、全部复核与选择、报告全文。`list_trade_plans(ticker=None, active_only=True)`：返回摘要，不返回报告全文。

### 三线结算（`product/deterministic/plan_math.py`，纯计算）
- 成交：`frozen_at` 之后第一个常规交易日开盘（复用 `decision_scoring.entry_index`）。开盘价缺失 → `not_fillable`；开盘价不在 `entry_band` → `unfilled`；没有之后的交易日 → `pending`。
- 照计划：从成交日起逐日检查，依次执行：
  1. 当日收盘 ≤ 当时有效版本的 `price_invalidation` → 下一交易日开盘全部离场（原因 `stop`）；
  2. 复核 `action` 为 REDUCE / EXIT → 复核有效时间之后第一个开盘执行（原因 `review`）；
  3. 决定日 + `horizon_cap_days` 之前（含）最后一个交易日收盘仍持有 → 按收盘离场（原因 `cap`）；
  4. 截至评分日仍未到上述任一离场 → `open`，按评分日收盘估值（标“未实现”）。
- 持有对照：同一成交，持有到 `cap` 收盘（或评分日估值）。
- 简单退出对照：同一成交，只按**初始** `price_invalidation` 的收盘规则离场，否则到 `cap`。
- 每条线输出：每笔成交（日期、价格、股数、原因）、毛损益、成本（每边成交额 × 10bp）、净损益、`R = 净损益 / r0`、入场名义金额的收益率、途中最低收盘相对入场的 R。配对差：照计划 − 持有，照计划 − 简单退出（美元与 R）。
- `adj_close / close` 在窗口内变化超过 1.5% → 标 `corporate_action_suspect`，三条线都标“不可结算”。
- 漏斗：按 candidate 的 outcome 与 plan 的结算状态计数（wait、not_formed、abandoned、unfilled、not_fillable、pending、open、closed）。

### 返工 1 定下的规则（Codex `gpt-6.2-astra` 代码复核，2026-11-28）
- **三个时刻**：记录的有效时间（计划冻结、修订、复核、选择都有）、行情是否已完成、回放能读到什么。回放会话与评分只看截止点（实时为现在；回放与评分为该日纽约 23:59:59）之前生效的记录；之后的修订、复核、选择完全不可见，也不影响“进行中”的判断。按 id 读写时会话模式必须与计划一致（`PLAN_REPLAY_MISMATCH`）。
- **裸日期证据**：`published_at` 只有日期时按当日全天处理：用上界判断“复核时已公开”（同一天的材料须给精确时间，`EVIDENCE_TIME_AMBIGUOUS`），用下界判断“晚于上次复核”。
- **改判须有非价格新证据**：价格变化不改变论点结论，价格在动作里处理。
- **论点视图**：`get_trade_plan(plan_id, view="thesis")` 不含价格字段、动作、报告全文，复核第一步只用它。
- **报告完整性**：报告按 id 从 `plan-reports/` 定位并校验 SHA-256，返回 `report_integrity`。
- **并发**：检查与追加在同一把文件锁内。
- **结算**：评分取价传 `as_of`，冻结到结束之间有拆股 → `not_settleable`（`split_in_window`）；未完成交易日不用；冻结后首个开盘晚于 cap 日 → `expired_unfilled`；失效价修订生效于纽约 13:00–16:00 时标 `revision_same_day_check`（提前收市日人工核对，L1 不实现交易所日历）。

### 返工 3：纸面成交改为限价挂单（历史走查发现，2026-11-28）
- 依据：TER、GS、MRVL 三份历史计划全部 unfilled（区间 ±1–2%，只看冻结后第一个开盘）。
- 新增 `entry_valid_sessions`（1–10，默认 5）；逐日：开盘在区间内按开盘成交；高开且最低价 ≤ hi 按 hi 成交；开盘 < lo 当日不买；成交前收盘 ≤ 初始失效价 → `cancelled_stop_before_fill`；有效期内未成交 → `unfilled`。`fill_rule = limit_band_within_entry_valid_sessions`。
- R0 不随成交价改变；旧记录（无此字段）按原规则结算，结果逐字不变。
- Skill：区间上下至少留出近 20 日平均隔夜跳空的两倍。

### MCP 工具（`product/mcp/server.py`，一名实现者负责注册）
`size_trade_plan(entry_ref, price_invalidation, risk_budget=1000)`（只读）、`save_plan_candidate(ticker, outcome, reason, replay_as_of?)`（outcome 只能 wait / not_formed）、`save_trade_plan(...)`、`revise_trade_plan(plan_id, reason, sources, changes, replay_as_of?)`、`save_plan_review(...)`、`record_plan_choice(plan_id, ref_id, choice, note)`、`get_trade_plan(plan_id)`、`list_trade_plans(ticker?, active_only?)`。错误沿用 `DecisionLogError` 与 `explain_errors`。

### 调试入口（`scripts/dev-research.sh`）
- `--plan "想法"`：`trade-plan` Skill；`--review PLAN_ID`：`plan-review` Skill；`--seed-plans FILE`：开始前把 FILE 复制为运行目录的 `trade_plans.jsonl`。两种模式 Codex 都开联网检索；脚本导出 `STOCK_AGENT_RUN_MODEL=<实际 -m 参数>`。
- `run.json` 增加 `trade_plans`（plan_id、kind、action 摘要）。

### 结算脚本 `scripts/score-plans.py`
`--plans FILE`（默认 `.local/data/trade_plans.jsonl`）、`--as-of YYYY-MM-DD`、`--out FILE.md`。逐计划输出三条线、配对差、成交明细（足以手算）与标记；末尾输出漏斗。只读，不调用模型。

### Skills（主会话写）
- `product/skills/trade-plan/SKILL.md`：催化事件模板，必答问题，用 `size_trade_plan` 算股数，计划不成立就 `save_plan_candidate`。
- `product/skills/plan-review/SKILL.md`：两步复核，先论点后价格；结论改变必须引用新证据。

## 重要未知与候选
| 问题及影响 | 候选与代价 | 最小验证 | 去向 |
|---|---|---|---|
| 单个会话里“先论点后价格”能否真的不被价格牵着走 | Skill 规定顺序 + 工具强制“改结论须有新证据”；两次独立调用代价翻倍 | L1 只做规则与抽查；双跑留到 L2 | L2 双跑实测 |
| 10 个交易日内是否有合适的真实事件 | 用户选一只临近财报或有已排期事件的股票 | 计划时检查下次财报日 | 无事件则报告“待验” |

## 验收
- 核心成功场景（真实前瞻）：用户选一个真实机会 → 计划卡 → 用户复述失效条件 → 下一次公开事件后复核 → 结算可手算。
- 三个固定用例（历史回放，Codex `gpt-6.1-terra`）：
  - A 跳空超出预算：计划后出现一次收盘跌破失效价且次日开盘更低的跳空，结算 R < −1，走到结算；
  - B 同股重开：同一 ticker 计划 → 复核 EXIT → 新计划；两个 `plan_id` 不串线，第二次计划时第一份不再“进行中”；
  - C 未成交或缺数据：下一开盘价在 `entry_band` 之外，记 `unfilled`，进入漏斗。
- 单元测试（离线、临时目录）：风险算术；冻结字段被拒；修订限制；R0 不变；8 个上限；同股进行中被拒；改结论无新证据被拒；回放时间；`model_recorded` 来源；三线结算的成交、止损跳空、复核离场、REDUCE、cap、未成交、缺开盘、估值、成本、公司行为标记。
- 预算：≤ 12 次模型调用（三个用例约 6 次 + 真实前瞻 2 次 + 返工余量）。
- 本轮不证明：方向能力、收益优势、复核稳定性、用户长期负担。

## 延后项
| 能力 | 为何现在不需要 | 触发条件 | 限制 |
|---|---|---|---|
| 每日事实提示脚本 | L1 人工发起复核 | L2 开始 | 只输出事实，不调模型 |
| 加仓、多次建仓 | 先把一次建仓做对 | L2 通过 | 原 R0 保留，新增风险另列 |
| 复权、分红 | L1 用例可避开 | 出现疑似公司行为的真实计划 | 结算须可手算 |
| 其他模板 | 用户只需一类先验证 | L1 通过且用户要求 | 一张计划只用一张模板 |

## 验证和实施结论
| 结论 | 基线／条件 | 验证层次与结果 | 证据位置 | 未覆盖或限制 |
| --- | --- | --- | --- | --- |
| 记录、工具、三线结算可用，结算可手算 | main 5ea1d8c + 本轮未提交改动 | 离线测试 319 通过；A 手算与脚本、astra 独立手算一致 | evidence/position-lifecycle-acceptance.md | 只是流程与算术，不证明效果 |
| 复核两步法在实跑中成立 | Codex terra 回放 A | 收盘跌破失效位时论点判 unchanged、动作 EXIT（价格不改论点） | `.local/runs/*L1-A-review*` | 单例；双跑稳定性留到 L2 |
| 计划不成立时如实记录 | Codex terra 回放 B | 指引超预期但说不出市场错在哪 → not_formed 入漏斗 | `.local/runs/*L1-B-reopen*` | 重开链路由工具直接调用验证 |
| 区间外不成交 | Codex terra 回放 C | 开盘 34.50 > 上限 33.90 → unfilled | `.local/runs/*L1-C-plan*` | — |
| 真实前瞻用例 | 待用户选股 | 未开始 | — | L1 最后一项 |

## 总设计与文档入口同步
- 总设计 §8 已回答并同步；返工规则已并入本文“返工 1 定下的规则”，返工 2 见验收记录。
- 文档入口：roadmap 当前路线 L1 行；handoff 活动工作表。
