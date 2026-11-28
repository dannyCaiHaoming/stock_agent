# MVP L1：交易计划生命周期 实施 plan

类型：实现
依据：[designs/position-lifecycle.md](../designs/position-lifecycle.md)（全文已定）；总设计 [docs/design-position-lifecycle-2026-11-28.md](../../docs/design-position-lifecycle-2026-11-28.md) §3–§5。
依据版本：`main` 5ea1d8c，加上本轮未提交的文档改动（共享工作区可直接读）。
执行者／工作区：H1–H3 由 Claude Sonnet 5.5 子 Agent 执行（用户 2026-11-28 指定）；S（两个 Skill）、V（验收）与整合由主会话（Opus 5.5）执行。所有人共用 `/Users/caihaoming/Documents/stock_agent`（`main`，不开分支）。
状态：实现与固定用例完成（含返工 1、2）；剩真实前瞻用例（需用户）
plan 维护者：主会话。执行者不改本文件，结果写到自己的证据文件。

## 0. 当前交接
- **当前 MVP 核心目标**：用户对一笔纸面普通股多头完成“计划 → 公开事件 → 复核 → 结算”，结算可手算复现。
- **本 plan 只完成**：子设计的记录、工具、结算、Skill 与三个固定用例；真实前瞻用例由用户参与，记为验收的最后一步。
- **必须保留**：
  - `decision/v2`、`trade_decisions.jsonl`、`score-decisions.py`、`decision_scoring.py` 行为不变（只允许被 import，不改）；
  - 测试一律在临时目录运行（`STOCK_AGENT_DATA_DIR` 指向 tempdir），不得写入 `.local/data/` 或 `evals/`；
  - 不 commit、不 push、不调用模型、不改分派给自己以外的文件；设计契约需要改变时停下，写进证据文件并返回。
- **测试命令**：`.venv/bin/python -m unittest tests.<模块名> -v`（仓库没有 pytest）。
- **写入归属**（互不重叠）：

| 任务 | 只可写这些文件 |
|---|---|
| H1 结算数学 | `product/deterministic/plan_math.py`（新）、`tests/test_plan_math.py`（新）、`fucxxx-codex-spec/evidence/position-lifecycle-h1.md`（新） |
| H2 计划记录 | `product/mcp/plan_ledger.py`（新）、`tests/test_plan_ledger.py`（新）、`fucxxx-codex-spec/evidence/position-lifecycle-h2.md`（新） |
| H3 接入 | `product/mcp/server.py`（只新增 8 个工具的注册与 import）、`scripts/score-plans.py`（新）、`scripts/dev-research.sh`（只新增 `--plan`、`--review`、`--seed-plans` 与 `STOCK_AGENT_RUN_MODEL` 导出、`run.json` 的 `trade_plans`）、`tests/test_plan_integration.py`（新）、`fucxxx-codex-spec/evidence/position-lifecycle-h3.md`（新） |
| 主会话 | `product/skills/trade-plan/`、`product/skills/plan-review/`（新）、本 plan、子设计、总设计、roadmap、handoff、`evidence/position-lifecycle-acceptance.md` |

- **必读输入**：`AGENTS.md`；子设计全文；本 plan 中自己的任务节；参考实现 `product/mcp/decision_ledger.py`（记录、生成字段、回放时间的写法）与 `product/deterministic/decision_scoring.py`（`entry_index`、`parse_utc`、`NY`）。
- **交付**：证据文件写清实际修改的文件、接口签名、测试命令与输出摘要、未完成或失败项、对设计的回写建议；最后一条消息给出简短结论。

## 1. 工作安排
| 步骤 | 依赖 | 判据 |
|---|---|---|
| H1 结算数学 | 无 | §2 H1 |
| H2 计划记录 | 无 | §2 H2 |
| S 两个 Skill | 子设计接口（已定） | §2 S |
| H3 接入 | H1、H2 | §2 H3 |
| 复核 | H1–H3、S | Codex `gpt-6.2-astra` 只读复核；问题返工 |
| V 验收 | 全部 | 子设计“验收”；结果写 `evidence/position-lifecycle-acceptance.md` |
| 回补 | V | 子设计“验证和实施结论”、总设计、roadmap、handoff |

## 2. 任务

### H1 `product/deterministic/plan_math.py`（纯计算，不联网，不读文件）

```python
COST_BPS_PER_SIDE = 10
CORP_ACTION_TOL = 0.015
MAX_HORIZON_DAYS = 120

class PlanMathError(ValueError): ...   # message 以大写错误码开头，如 "STOP_NOT_BELOW_ENTRY: ..."

def size_position(entry_ref: float, price_invalidation: float, risk_budget: float) -> dict:
    """{"risk_per_share", "shares", "r0"}；shares = floor(risk_budget / (entry_ref - price_invalidation))。
    错误：任一数非有限或 ≤0 → INVALID_NUMBER；price_invalidation >= entry_ref → STOP_NOT_BELOW_ENTRY；
    shares < 1 → RISK_BUDGET_TOO_SMALL。"""

@dataclass
class Bars:
    dates: list[str]                 # 升序 ISO 日期（交易日历）
    open: list[float | None]
    close: list[float | None]
    adj_close: list[float | None]    # 只用于公司行为检查

def settle(plan: dict, revisions: list[dict], reviews: list[dict], bars: Bars, as_of: str,
           cost_bps_per_side: float = COST_BPS_PER_SIDE) -> dict:
```

`plan` 使用的字段：`frozen_at`（ISO UTC）、`entry_band` `[lo, hi]`、`price_invalidation`、`shares_planned`、`r0`、`horizon_cap_days`。`revisions` 每项：`effective_at`（ISO UTC）、`changes`（可能含 `price_invalidation`）。`reviews` 每项：`review_id`、`reviewed_at_effective`（ISO UTC）、`action`（HOLD/REDUCE/EXIT）。

规则（全部用未复权 `open`/`close`；只用 `date <= as_of` 的行）：
1. **成交**：`i = decision_scoring.entry_index(frozen_at, dates)`。`None` → `pending`；`open[i]` 缺失 → `not_fillable`；`open[i]` 不在 `[lo, hi]`（含端点）→ `unfilled`。成交价 = `open[i]`，股数 = `shares_planned`。
2. **cap 日**：`cap_date = frozen_at 的纽约日期 + horizon_cap_days 个日历日`；cap 交易日 = `max(i, 最后一个 date <= cap_date 的下标)`。
3. **照计划线**，从 `d = i` 起逐日：
   - 先执行当天开盘的待执行离场（来自前一日的止损触发或复核；同一开盘多条时 EXIT 优先，只执行一次）；开盘缺失 → 顺延到下一个有开盘价的交易日，记 `delayed_exit`。
   - 复核：`reviewed_at_effective` 对应的 `entry_index` 就是执行开盘；REDUCE 卖出剩余股数的 `floor(一半)`，结果为 0 时卖出全部；EXIT 卖出全部。执行开盘早于或等于成交开盘的复核：EXIT → 状态 `cancelled_before_fill`（无成交），其他忽略。
   - 当天是 cap 交易日且仍持有 → 按当天收盘全部离场（原因 `cap`）；收盘缺失 → 顺延到下一个有收盘价的交易日，记 `delayed_cap`。
   - 否则，当天收盘 ≤ 当时有效的失效价 → 下一交易日开盘全部离场（原因 `stop`）。当时有效 = 初始值，或 `effective_at` 早于当天纽约 16:00 的最后一个修订的值。收盘缺失 → 当天不检查，记 `missing_close`。
   - 到 `as_of` 仍持有 → 状态 `open`，按 `as_of` 前最后一个收盘估值（`unrealized: true`）。
4. **持有对照线**：同一成交，只按 cap 离场（或 `open` 估值）。
5. **简单退出对照线**：同一成交，只用**初始**失效价按第 3 条的止损规则，加 cap；忽略修订与复核。
6. **成本**：每一笔成交 `price × shares × bps / 10000`（买入、卖出各算一次；估值不算卖出成本）。
7. **每条线输出**：`status`（closed/open/unfilled/not_fillable/pending/cancelled_before_fill/not_settleable）、`legs`（`date, side buy|sell, price, shares, reason fill|stop|review|cap|value`）、`gross`、`costs`、`net`、`r = net / r0`、`return_pct = net / (成交价 × 股数) × 100`、`min_close_r = (持有期间最低收盘 − 成交价) × 股数 / r0`、`flags`。
8. **配对差**：`plan_minus_hold`、`plan_minus_simple`（美元与 R），只在两条线都是 closed 或 open 时计算。
9. **公司行为**：成交日到结束日之间 `adj_close/close` 的最大值/最小值 − 1 > `CORP_ACTION_TOL` → 三条线 `status = not_settleable`，flag `corporate_action_suspect`。
10. 返回 `{"fill": {...}, "cap_date", "lines": {"plan", "hold", "simple_exit"}, "pairs": {...}}`，所有金额四舍五入到 0.01，R 到 0.001。

**H1 测试**（用构造的 `Bars`，不联网）至少覆盖：正常持有到 cap；收盘跌破后次日跳空开盘更低导致 R < −1；修订提高失效价后按新价触发；复核 REDUCE 再 EXIT；复核早于成交的 EXIT；开盘不在区间 → unfilled；开盘缺失 → not_fillable；没有后续交易日 → pending；as_of 时仍持有 → open 估值；成本按两边计算；公司行为标记；三条线在“无任何触发”时结果相同（配对差 0）；`size_position` 三种错误。每个数值用例在测试里写出手算过程注释。

### H2 `product/mcp/plan_ledger.py`

记录文件 `settings.data_dir() / "trade_plans.jsonl"`，报告 `settings.data_dir() / "plan-reports" / <YYYY-MM-DD> / <TICKER>-<id>.md`；写法照 `decision_ledger.py`（`os.open(..., O_APPEND)`、目录 0o700、报告 `open("x")`、`sha256` 前 12 位作 id、`_code_version()` 来自 `decision_log`）。可以 import `decision_ledger` 的 `_text`、`_iso_date`、`_decision_times`、`NY`、`DAY_END`、`_only_keys`，以及 `plan_math.size_position`。错误一律抛 `DecisionLogError`，信息以大写错误码开头。

函数（签名即 MCP 工具参数）：
- `size_trade_plan(entry_ref, price_invalidation, risk_budget=1000) -> dict`：调 `size_position`，`PlanMathError` 转为 `DecisionLogError`。
- `save_plan_candidate(ticker, outcome, reason, replay_as_of=None, host=None, model=None) -> dict`：`outcome ∈ (wait, not_formed)`。
- `save_trade_plan(ticker, template, thesis, market_misread, catalyst, abandon_facts, price_invalidation, entry_ref, entry_band, hold_basis, review_dates, horizon_cap_days, report_markdown, risk_budget=1000, replay_as_of=None, host=None, model=None, **extra) -> dict`：校验见子设计“记录”与“规则”；同时写 `candidate(outcome=plan)` 与 `plan` 两行；返回 `plan_id`、`candidate_id`、`frozen_at`、`shares_planned`、`r0`、`report_path`。
- `revise_trade_plan(plan_id, reason, sources, changes, replay_as_of=None) -> dict`：`changes` 只允许四个键，否则 `REVISION_FIELD_NOT_ALLOWED`；计划须进行中；修订后的失效价只须为正数（可以上移到成本之上作为保护利润的移动失效位；R0 不变，所以不会美化 R）；`version` = 已有修订数 + 2。
- `save_plan_review(plan_id, thesis_verdict, evidence, action, action_reason, report_markdown, plan_deviation=False, deviation_reason=None, replay_as_of=None, host=None, model=None) -> dict`：校验见子设计；`plan_deviation=True` 时 `deviation_reason` 必填；返回 `review_id`、`reviewed_at_effective`、`report_path`。
- `record_plan_choice(plan_id, ref_id, choice, note) -> dict`：`choice ∈ (followed, declined, abandoned)`；`abandoned` 只在该计划尚无 `action=EXIT` 复核时允许。
- `get_trade_plan(plan_id) -> dict`：`{"found", "plan", "revisions", "current", "reviews", "choices", "active", "report_markdown"}`；`current` 是把修订按顺序套用后的四个可改字段。
- `list_trade_plans(ticker=None, active_only=True) -> dict`：摘要列表（不含报告全文）与 `active_count`。
- `active_plans(today_ny: date, replay: bool) -> list[dict]`：内部函数，供上限与同股检查使用；回放记录只和回放记录比较，实时只和实时比较。

字段与生成规则严格照子设计；调用方传入生成字段 → `GENERATED_FIELD_NOT_ACCEPTED`；未知字段 → `UNKNOWN_FIELDS`。`model_recorded` 按子设计取 `STOCK_AGENT_RUN_MODEL`。

**H2 测试**（临时目录）至少覆盖：正常保存与返回值；股数与 R0；生成字段被拒；未知字段被拒；`abandon_facts` 空或缺 document/fact 被拒；`entry_band` 与失效价的顺序校验；`horizon_cap_days` 0 与 121 被拒；`template` 非 `catalyst_event` 被拒；第 9 个进行中计划被拒；同股进行中被拒；EXIT 复核后同股可以重开且 `plan_id` 不同；cap 过期后不再进行中；修订不允许的字段被拒、R0 与股数不变、`current` 正确；复核改结论无新证据被拒、有新证据通过；复核证据 `published_at` 晚于有效时间被拒；回放计划的有效时间为该日纽约 23:59:59、回放与实时不混；`model_recorded` 的两种来源；报告缺标题被拒；`abandoned` 在 EXIT 后被拒。

### H3 接入
- `server.py`：注册 8 个工具（`size_trade_plan` 用 `READ_ONLY`，`get_trade_plan`、`list_trade_plans` 用 `READ_ONLY`，其余用 `LOCAL_WRITE`），都加 `@explain_errors`；docstring 写清参数、生成字段与关键规则（参照 `save_trade_decision` 的写法，面向模型）。不加 `@point_in_time`；回放由 `replay_as_of` / 环境变量处理。
- `scripts/score-plans.py`：`--plans`（默认 `.local/data/trade_plans.jsonl`，只读）、`--as-of`（默认同 `score-decisions.py` 的 `default_as_of`）、`--out`。用 `data_tools.get_price_history` 取 SPY 日历与个股行情（参照 `score-decisions.py` 的 `PriceBook`，行情失败要报告，不能当作无数据）；按计划调用 `plan_math.settle`；输出 Markdown：每个计划一节（成交、三条线的 legs 表、gross/costs/net/R、配对差、flags），末尾漏斗表（candidate outcome 与结算状态计数）。
- `scripts/dev-research.sh`：新增 `--plan "想法"`（prompt：`交易计划：股票 ${ticker}。${想法}。按 trade-plan Skill 完成并保存。`；回放时加与 `--decision` 相同的回放说明）、`--review PLAN_ID`（prompt：`计划复核：plan_id ${id}，股票 ${ticker}。按 plan-review Skill 完成并保存。`，回放说明同上）、`--seed-plans FILE`；两种模式 Codex 开 `web_search="live"`；对两个宿主都导出 `STOCK_AGENT_RUN_MODEL="$model"`；`run.json` 增加 `trade_plans` 摘要。保持现有模式行为不变。
- `tests/test_plan_integration.py`：通过 `server` 模块直接调用工具函数完成一条“保存计划 → 复核 EXIT → 同股重开”的链路（临时目录）；用构造行情（mock `data_tools.get_price_history`）跑 `score-plans.py` 的主函数并检查输出含三条线与漏斗；`bash -n scripts/dev-research.sh` 通过。

### S 两个 Skill（主会话）
- `trade-plan`：输入股票与用户想法；取数（`get_market_context`、`list_filings`、`get_news_history` 或联网检索、`classify_decision_event` 只作背景、`get_price_history`）；判断是否属于“催化事件”且计划成立；必答问题；`size_trade_plan`；`save_trade_plan` 或 `save_plan_candidate`；报告标题按子设计。
- `plan-review`：输入 `plan_id`；第一步只读 `get_trade_plan` 与新公开材料，写论点结论（不调价格工具）；第二步才取价格与大盘，给动作；`save_plan_review`；需要改条件时 `revise_trade_plan` 并写理由。

### V 验收（主会话）
- 单元与集成测试全部通过；三个固定用例按子设计用历史回放跑通（Codex `gpt-6.1-terra`），`score-plans.py` 输出可手算；真实前瞻用例与用户一起完成；全部记录写进 `evidence/position-lifecycle-acceptance.md`。
