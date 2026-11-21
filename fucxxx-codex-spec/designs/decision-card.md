# MVP P1：日用决策卡

总设计依据：[Decision-First 设计](../../docs/design-decision-first-2026-11-21.md) §3–§4.2；可执行细则以 [决策账本协议 v1](../../evals/forward/decision-protocol-v1.md) 为准。
设计：已定（2026-11-22）。实现：未开始。验收：未开始。
更新时间：2026-11-22（JST）

## 当前核心目标
- **服务总设计的目标**：让“决策工具可用”这一层承诺兑现（总设计 §1）。
- **本 MVP 交付的结果**：用户说“INTU 我持有，该怎么办”，得到一张决策卡。卡上写明：
  - 明确动作；
  - 主窗口（由事件组决定，不由模型选）；
  - 相对板块与绝对收益两栏数字；
  - 消息归因、复核条件、上一卡对照。

  同时生成一条 `decision/v2` 记录，这条记录可以按协议成交、评分。
- **最小验收链路**：`scripts/dev-research.sh codex <T> --decision held|not_held` → decision-card Skill 调用：
  1. `classify_decision_event`（事件组、窗口、基准、B1）；
  2. `get_key_moments`（开盘口径分布）；
  3. E1/E2 时做消息归因；
  4. 写卡；
  5. `save_trade_decision` 生成记录；
  6. `scripts/score-decisions.py` 对已到期的历史记录算出 Δ / B0 / B1 / B2。
- **必须保留**：
  - 旧 `save_decision`、`decisions.jsonl`、旧账本及其评分不变；
  - `key-moments.jsonl` 原 `outcome` 字段（收盘口径）不变，消息面账本的登记评分仍读它；
  - 事实带 `source_id` / `as_of` / `retrieved_at`；
  - 主观判断不进确定性代码。
- **本次不做**：
  - 每日扫描与抽样（P2）、S&P 500 名单与映射快照（P2 开始前）；
  - 自动推送、完整研究改造、新 Agent、组合层；
  - 买入侧的效果检验。

## 现状与直接缺口
- **已有可复用的**：
  - `key_moments.detect` / `summarize`、`get_key_moments`（收盘口径）；
  - `sample-idiosyncratic-moments.py` 的 `deviation`；
  - `build-pead-events-v2.py` 的 `locate` / `holding`（D1 复权开盘口径，已与协议一致）；
  - `forward-select.py` 的 `signal_day` / `earnings_hits`；
  - `data_tools.get_price_history`（有 open / close / adj_close）、`list_filings`（有 8-K items 与受理时间）；
  - `save_moment_review` 的归因枚举 `CAUSES` 与防事后措辞检查；
  - `moment-review` Skill 的归因方法。
- **缺口**：
  1. 关键时刻分布还是收盘入场，与协议不一致；
  2. 没有确定性的事件分组（E0/E1/E2），模型无从知道主窗口；
  3. 没有 `decision/v2` 记录与保存工具：动作枚举缺 WAIT，`decided_at`、w1、horizon 应由工具生成而不是由模型填写；
  4. 没有按协议成交与评分的脚本；
  5. 没有轻量决策流程与决策卡模板；
  6. 实跑脚本没有决策模式。
- **取舍**：
  - 开盘口径用**新增字段**，不改旧字段。理由：消息面账本已登记的评分读旧字段，直接改会让已登记的检验换口径；
  - 决策卡用**新 Skill** `decision-card`，不改造 `investment-decision`。理由：完整研究仍按需保留，两者模板与保存工具不同，混在一份 Skill 里会让两种流程都更难读。

## 设计与接口

### T1 开盘口径分布（`product/deterministic/key_moments.py`、`scripts/build-key-moments.py`、`product/mcp/reference_tools.py` 的 `get_key_moments`）
- 新增 `outcome_open(dates, opens_adj, closes_adj, bench_opens_adj, bench_closes_adj, index)`：
  - 入场 = `dates[index+1]` 的复权开盘（`open × adj_close / close`），第 h 日 = `dates[index+h]` 收盘；
  - 每个 h 输出 `exit_date`、`ret`、`excess`（同窗口 ETF 从同日复权开盘到同日收盘）、`worst`（入场至退出各收盘的最低值 ÷ 入场价 − 1）；
  - 任一必要价格缺失 → 该 h 为 None。
- 建表时为每行同时写 `outcome`（原样）与 `outcome_open`；`baseline_days` 行同样。
- `get_key_moments` 的 `what_followed`、`baseline_any_day`、`same_moments_in_this_ticker` 改读 `outcome_open`，provenance 改写入场口径。
- 重建表后重写 `evals/key-moments/distribution-latest.md`（开盘口径）；旧文件先复制为 `distribution-close-entry-2026-11-11.md`。

### T2 `decision/v2` 记录与保存工具（`product/mcp/decision_ledger.py` 新、`product/mcp/server.py` 注册、`scripts/decision-record.py` 新）
- `save_trade_decision(...)` 写 `<data dir>/trade_decisions.jsonl`，报告全文写 `<data dir>/trade-reports/<date>/<TICKER>-<id>.md`。
- **工具生成、模型不能填**：`schema = "decision/v2"`、`decision_id`、`decided_at`（UTC）、`info_cutoff = decided_at`、`w0`、`w1`、`horizon_days`、`fill_rule = "next_regular_open_after_decided_at"`、`code_version`、`report_sha256`。
- **模型提供、工具校验**：

| 字段 | 校验 |
|---|---|
| `ticker` | 规范为大写，`.` 换成 `-` |
| `source` | `scan` / `on_demand` |
| `position_state` | `held` / `not_held` |
| `group` | `E0` / `E1` / `E2`；horizon 由 group 决定：E1 → 20，其余 → 60 |
| `event` | dict：`event_date`，可选 `moment`、`deviation_z`、`d0`、`accession` |
| `benchmark` | ETF 代码 |
| `action` | held：ADD/HOLD/REDUCE/EXIT；not_held：BUY/WAIT；`scan` 只能 held |
| `cash_destination` | `cash` / `sector_etf` |
| `p_outperform` | {`baseline`, `case`, `basis`}，0–1，允许 0.5 |
| `attribution` | E1/E2 必填：{`primary_cause` ∈ `CAUSES`, `company_cause` ∈ true / false / `unconfirmed`, `explicit_guidance_cut` bool}；E0 可空 |
| `hold_type` | HOLD/WAIT 必填 `no_edge` / `has_view`，其余为 null |
| `review_triggers` | 至少两条，至少一条含数字价格位 |
| `thesis` | 一句 |
| `prior_decision_id` | 可空；非空时须存在于同一文件 |
| `report_markdown` | 必须有决策卡模板的标题 |
| `model`、`host` | — |

- w 映射按协议 §4：EXIT 0、REDUCE 0.5、HOLD 1、ADD 1.5、WAIT 0、BUY 0.5；held 的 w0 = 1，not_held 的 w0 = 0。
- 错误一律 `DecisionLogError("<CODE>: 说明")`，沿用 `decision_log` 的风格。
- `scripts/decision-record.py <decision_id>`：把指定记录与报告 sha 追加到 `evals/forward/decision-ledger.jsonl`（只追加、同一 id 不重复）。

### T3 事件分组（`product/deterministic/decision_events.py` 新、`product/mcp/decision_tools.py` 新增 `classify_decision_event`；`server.py` 注册由主会话整合时做）
- 纯函数（只吃价格与申报数据，不联网）：
  - `deviation_z(stock_closes, bench_closes, dates, i)`：从脚本迁入，阈值 2、窗口 5、波动窗口 120 不变；脚本改为调用它；
  - `pead_d0(accepted_ny, dates)`：P、D0 定位，规则同 `locate`；
  - `classify(...)`：输出 group、主窗口与 overlap 标记。
- MCP 函数 `classify_decision_event(ticker, as_of=None, lookback_sessions=3)` 返回：
  - `group`、`horizon_days`、`event_date`、`benchmark`（`meta.json` 映射，缺失为 `no_sector` 且 group 不能为 E2）；
  - E2 详情：`moment`、`deviation_z`、`direction`；
  - E1 详情：`accession`、`accepted_ny`、`d0`、`reaction_excess`；
  - `overlap`（同时满足 E1、E2）、`late_sessions`（as_of 距事件日的交易日数）；
  - `b1_action`（E2 下偏 → REDUCE，上偏 → HOLD；E1 → REDUCE；E0 → HOLD）、provenance。
- 判定规则：
  - lookback 窗口内同时有 E1 与 E2 → E2（协议 §2）；
  - 多个候选时取最近的事件日；
  - 没有 → E0（horizon 60、event_date = as_of 当日或之前最后一个交易日）。
- E1 只用 D0 收盘前可知的数据：D0 收盘晚于 as_of 时不判 E1。

### T4 评分（`product/deterministic/decision_scoring.py` 新、`scripts/score-decisions.py` 新）
- 纯函数：
  - `fill(decided_at_utc, dates, opens, closes, adj_closes)` → 入场索引与复权开盘，或 `not_fillable`；
  - `window_return(...)`；
  - `delta(w0, w1, r_stock, r_alt, dest)` → (Δ, 成本)，按协议 §4；
  - `baselines(record)` → B0 / B1 / B2 的 w1；
  - `block_bootstrap(events, week_of, L, reps=10000, seed=20261122)` → (lo, hi)，按协议 §6，并在 W < 3L 时返回 None。
- 脚本读 `evals/forward/decision-ledger.jsonl`（或 `--ledger` 指定的文件），逐条取价，输出：
  - 每条：状态（`pending` / `not_fillable` / `unscorable` / `late` / 已评分）；
  - ETF 与现金口径的 Δ、Δ_B1、Δ_B2；
  - 漏斗计数、缺失率；
  - 区间可用时的区间与判定（只对 `source = scan` 的 E2 主样本做判定，按需记录只报告）。
- 单元测试必须复算协议 §8 的三行。

### T5 决策模式 Skill（主会话）
- 新 `product/skills/decision-card/SKILL.md`，流程：
  1. 输入；
  2. `classify_decision_event`；
  3. `get_key_moments` 与 `get_price_history`；
  4. E1/E2 时按 `moment-review` 方法做一次归因（信息截止为当前）；
  5. 读同股上一张卡（`trade_decisions.jsonl`）；
  6. 写卡（设计 §3.5 模板）；
  7. `save_trade_decision`。
- `stock-research` 加入口：用户问“我持有/未持有，该怎么办”时默认走决策卡；要求“完整研究”才走原流程。
- `scripts/dev-research.sh` 加 `--decision held|not_held`。

### T6 冻结案例与验收（主会话 + Codex 实跑）
- 12 个历史案例（`--as-of`），覆盖设计 §4.2 列出的情形，跑 terra，存 `.local/runs/`。
- 结果写进 `fucxxx-codex-spec/evidence/decision-card-acceptance.md`。

## 重要未知与候选
| 问题及其影响 | 候选与代价 | 最小验证 | 去向 |
| --- | --- | --- | --- |
| 历史回放（`--as-of`）时 `decided_at` 是实际运行时间，按它算成交会落到“今天”，历史案例无法评分 | `save_trade_decision` 接受 `replay_as_of`：记录 `decided_at_effective` = as_of 当日 16:00 NY 之后，并标 `replay = true`；回放记录永不进 P2 主样本 | T2 单元测试 + T4 对回放记录评分 | 已定：采用候选，replay 记录只用于 P1 验收 |
| 消息归因在决策卡里是否仍有 terra 原任务的排序能力 | 无法在 P1 验证 | — | P2 前瞻检验本身；P1 不证明 |
| E1 判定需要列出 8-K 申报，按需查询要多一次 SEC 请求 | 可接受（有缓存） | T3 实跑一次 | 如果太慢，再考虑限制 lookback |

## 验收
- **核心成功场景**：held 的 E2 向下偏离案例，卡片写明：
  - 动作与 w1、60 日窗口；
  - 相对与绝对两栏、消息归因、两条复核条件（至少一条价格位）；
  - 记录通过校验，`score-decisions.py` 能算出该记录的 Δ、Δ_B1、Δ_B2。
- **必要反例**（来自总设计 §4.2，12 个冻结案例）：
  - 三组成对：只改成本价；只改资金去向；只改公司消息证据；
  - 池外股票；板块普跌；E1/E2 重叠；缺价；有上一卡。
- **硬性 0 次**：
  - 概率口径混用；
  - 使用 `info_cutoff` 之后的信息；
  - 成交早于决策；
  - 模型填写了工具生成的字段；
  - 把旧建议当成真实持仓。
- **局部验收**：T1–T4 单元测试；重建表的行数与旧表一致，原 `outcome` 字段逐行不变。
- **集成验收**：12 个案例端到端跑通；用户盲读至少 10/12 张、每张 60 秒内答出“做什么、为什么、何时重评”；至少 1 张真实（非回放）卡在可成交前写入 `evals/forward/decision-ledger.jsonl`。
- **本轮不证明**：任何投资优势；terra 在决策卡里的排序能力；S&P 500 扩池的可行性。

## 延后项
| 能力 | 当前为何不需要 | 重新考虑的触发 | 限制 |
| --- | --- | --- | --- |
| 每日扫描、抽样、名单与映射快照 | P1 只证明单卡链路 | P1 验收通过、进入 P2 | 按协议 §7 |
| 卡片里的“减半留现金／换 ETF”历史对比 | 需要按事件组的历史样本；E2 已有表，E1 需另建 | P1 验收时用户认为缺它就看不懂 | 两栏不相乘 |
| 完整研究改为输出 v2 记录 | 完整研究按需保留，不进检验 | 用户要求 | — |

## 验证和实施结论
| 结论 | 基线／条件 | 验证层次与结果 | 证据位置 | 未覆盖或限制 |
| --- | --- | --- | --- | --- |
| （待实施） | | | | |

## 总设计与文档入口同步
- 总设计不变；协议不变。
- roadmap P1 行在实施开始时标“进行中”；handoff 记录活动工作。
