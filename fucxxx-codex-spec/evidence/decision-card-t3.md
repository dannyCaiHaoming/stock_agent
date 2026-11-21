# T3 事件分组：实施证据

执行者：Sonnet 子 session。依据：plan §0/§1/§2、子设计 T3 节、协议 v1 §2–§5。未 commit、未 push、未调用模型、未写 `.local/data/`、未改 `server.py`。

## 1. 改动的文件
| 文件 | 内容 |
|---|---|
| `product/deterministic/decision_events.py`（新） | `deviation_z`、`pead_d0`、`classify` 与常量 |
| `product/mcp/decision_tools.py`（新） | `classify_decision_event` |
| `scripts/sample-idiosyncratic-moments.py` | 只改 `deviation`（调用 `de.deviation_z`）；`WINDOW`/`THRESHOLD` 改为引用模块常量（值不变）；去掉不再使用的 `import statistics` |
| `tests/test_decision_events.py`（新） | 26 个测试 |
| `.local/runs/t3-verify-20261122/`（未入库） | 三个一次性核对脚本 `verify_equal.py`、`run_real.py`、`run_real2.py` |

## 2. 接口
```python
# product/deterministic/decision_events.py
deviation_z(stock_closes: Mapping[str,float], bench_closes: Mapping[str,float], dates: Sequence[str], i: int) -> float | None
pead_d0(accepted_ny: str, dates: Sequence[str]) -> tuple[int,int] | str   # (P 下标, D0 下标)；或 no_time / outside_price_calendar / insufficient_history
classify(dates, closes, bench_closes | None, moments, earnings, lookback_sessions=3) -> dict
# product/mcp/decision_tools.py
classify_decision_event(ticker: str, as_of: str | None = None, lookback_sessions: int = 3) -> dict
```
- `deviation_z`：窗口 5、波动窗口 120、阈值 2（常量 `THRESHOLD`，由调用方比较）、`i < 121` 返回 None，逻辑逐行同原函数；`closes` 为按日期索引的复权收盘字典。
- `pead_d0`：规则同 `locate`；D0 下标可以等于 `len(dates)`（尚未观察到），由 `classify` 判为非 E1。
- `classify`：`dates` 截到 as_of 当日收盘（含）；`earnings` 为 `{accession, accepted_ny}`（已筛 Item 2.02）；`moments` 为 `key_moments.detect` 的输出；`bench_closes=None` 表示无板块映射。

返回示例（AAOI，as_of=2023-02-24，实跑；`provenance.notes` 略）：
```json
{"ticker":"AAOI","as_of":"2023-02-24","benchmark":"XLK","lookback_sessions":3,"history_sessions":758,"e2_available":true,
 "group":"E1","horizon_days":20,"event_date":"2023-02-24","overlap":false,"late_sessions":0,"b1_action":"REDUCE",
 "e2":null,
 "e1":{"accession":"0001683168-23-001106","accepted_ny":"2023-02-23T16:10","d0":"2023-02-24","p_date":"2023-02-23","reaction_excess":-0.123622},
 "provenance":{"source_id":"decision-events-v1","as_of":"2023-02-24","retrieved_at":"…Z",
   "inputs":[{"source_id":"yahoo-chart:AAOI",…},{"source_id":"yahoo-chart:XLK",…},{"source_id":"sec-submissions-0001158114",…}],"notes":"…"}}
```
E2 时 `e2 = {moment, date, deviation_z, direction: down|up}`，`e1` 在重叠时同样给出。

## 3. 判定规则的具体取值（设计未写死的部分，请主会话确认）
1. **窗口**：最近 `lookback_sessions` 个交易日（含 as_of 当日），即 `late_sessions ∈ {0..lookback−1}`，默认 0–2。理由：as_of 收盘后决策、次日开盘成交，成交日距事件日 = late+1 ≤ 3，恰与协议“迟到 > 3”一致。
2. **`late_sessions`** = (as_of 所在交易日下标) − (事件日下标)；E0 的事件日取 as_of 当日或之前最后一个已收盘交易日，故为 0。
3. **as_of 的“已收盘”**：16:00 NY 之前的 as_of（含 as_of=None 的盘中）不使用当日行，`as_of` 回显为最后一个已收盘交易日；日期型 as_of 视为当日收盘后。
4. **无板块映射**（`meta.json` 无该股）：`benchmark = "no_sector"`，E2 与 E1 都不判（两者都以板块为参照），group 为 E0。协议只写了“不进 E2”，对 E1 我取保守处理；如要对 no_sector 的 E1 用 SPY 兜底，需主会话决定（会与协议“D0 板块超额”字面不一致）。
5. **历史不足 260 个交易日**：不抛错，`e2_available = false`，仍可判 E1/E0（`key_moments.detect` 需要约 260 日）。新上市股票因此不会无法出卡。
6. **返回结构**：E2/E1 详情嵌套在 `e2`/`e1`，未平铺到顶层；`group/horizon_days/event_date/overlap/late_sessions/b1_action/benchmark` 在顶层。
7. 同日多个关键时刻取 `detect` 输出顺序第一个（协议 §2）；E1 同一 D0 的 8-K/A 取最早受理；多个候选取最近事件日；E1 用复权收盘，与 `events-pead-v2` 同口径。

## 4. 验证
### 单元测试
```
.venv/bin/python -m unittest tests.test_decision_events
Ran 26 tests ... OK
```
覆盖 T3 判据：
- `deviation_z` 与原函数在随机序列的全部下标上相等（含 `i<121`、波动为 0、基准缺日返回 None）；
- `pead_d0`：09:30 前、盘中（09:30 / 15:59）、16:00 之后、周六周日非交易日、no_time / 越界 / 历史不足、D0 超出末日；
- `classify`：E2 下偏（REDUCE）、E2 上偏（HOLD）、小偏离不算 E2、E1（20 日、REDUCE）、小幅财报反应不是 E1、重叠归 E2（`overlap=True`）、E0、无映射不进 E2/E1、D0 收盘之后的价格被污染结果不变、财报在末日收盘后受理（D0 未观察）不判 E1、窗口与 `late_sessions`、最近候选与同日取第一个、8-K/A 重复取最早；
- `classify_decision_event`（mock 价格与 8-K 列表，无网络）：E1、盘中 as_of 丢弃当日行、no_sector、短历史、非 2.02 的 8-K 忽略、provenance。

### 迁移后的 `deviation_z` 与原函数在真实事件上逐个相等
`.local/runs/t3-verify-20261122/verify_equal.py`：从 `key-moments.jsonl`（2019 年起、非 baseline）随机取 60 个真实事件，用同一份实盘价格比较三者——原函数逐字副本、`de.deviation_z`、改后脚本的 `deviation`：
```
META uptrend_break 2023-10-26 -0.5362878038582019 -0.5362878038582019 -0.5362878038582019
…
events=60 non_none=60 mismatches=0 (exact ==)
```
（`==` 精确相等，不是近似。）

### `classify_decision_event` 真实历史 as_of 实跑
`run_real.py`、`run_real2.py`（`SEC_USER_AGENT` 取自 `.mcp.json`，数据只读，走缓存/Yahoo/SEC）：
- **AAOI**、as_of 2023-02-24：E1，20 日，REDUCE，D0=2023-02-24，受理 2023-02-23 16:10 NY，超额 −12.36%（与事件表一致，示例见上）。
- **BMY**、as_of 2023-10-26：E1，受理 07:44 NY（D0 当日），超额 −5.44%，板块 XLV。
- **对 E1 事件表（`events-pead-v2`，2023–2025，反应 < −5%，236 个）随机 20 个**，以 as_of = D0 实跑：`accession`、`d0`、超额（1e-5 内）与事件表 **20/20 一致**；19 个为 E1，1 个（TGT 2024-11-20，超额 −20.9%）同时有关键时刻 `platform_breakdown`（z = −4.65）→ E2、`overlap=True`、E1 详情保留。
- **E2**：LITE 的 `uptrend_break` 2025-01-27（z = −2.29）：as_of=D+0 → E2 60 日 REDUCE、late 0；D+2 → E2、late 2；D+5 → E0 60 日 HOLD（超出窗口）。INTU 的 `failed_breakout` 2024-11-22（z = −2.47）：D+0/D+2 → E2 且 `overlap=True`（同日有财报 E1），D+5 → E0。
- **无映射**：F、as_of 2025-06-30 → `benchmark=no_sector`、E0、60 日。
- 同日多个时刻按 `detect` 顺序取第一个（LITE 同日 `platform_breakdown` 排在 `uptrend_break` 之前）。

## 5. 未完成 / 未覆盖
- 未注册到 `server.py`（按分工由主会话做）；未在 MCP 进程里列工具。
- 真实实跑只有 E1、E2、E0（含重叠、no_sector）各数例，没有抽样统计两组在全体事件上的命中率；协议 §2 中“terra 低概率档 11 个是否同时满足 E1”的核对（P1 待办）不属 T3。
- 8-K 列表取最近 40 条（`FILINGS_LIMIT`）；3 日窗口内足够，若把 `lookback_sessions` 调到很大（上限 20）仍够用，更长需要加大。
- 真实 8-K 路径依赖 SEC 缓存/网络；单元测试用 mock，不依赖网络。

## 6. 回写建议
- 子设计 T3 节补两句：窗口取最近 `lookback_sessions` 个交易日含 as_of 日（默认 3，即 late_sessions 0–2）；无映射时 E1 也不判；历史不足 260 日时 `e2_available=false`。
- 整合时 `save_trade_decision` 调 `classify_decision_event` 核对 group/horizon：需用返回的顶层 `group`、`horizon_days`；`e2`/`e1` 是嵌套对象。
- 协议 §7 的映射快照生成后，`_benchmark()` 的读取位置（`derived/signals/meta.json`）可能要改，改动只在 `decision_tools._benchmark` 一处。

## 7. 返工（Astra 复核第 2 条，2026-11-22）
问题：`classify` 把不同交易日的 E1、E2 合并为重叠（E2 在 02-24、E1 的 D0 在 02-25 时返回 `event_date=02-24, overlap=true`）。
修正（主会话已定规则，`product/deterministic/decision_events.py` 的 `classify`）：
- 窗口内先取 E1、E2 各自最近的候选，再取**最近的事件日**；
- 该日同时有 E2 时刻与 E1 的 D0（同一交易日）→ E2、`overlap=true`、`e1` 详情保留；
- 该日只有 E1 → E1，`e2 = null`；只有 E2 → E2，`e1 = null`、`overlap=false`，即使窗口内更早有另一组事件。
- 顶层 `event_date`、`late_sessions`、`horizon_days`、`b1_action` 均按这一天的组计算。

新增测试（`tests/test_decision_events.py`）：E2 先 E1 后（→ E1，无重叠，`e2=null`）、E1 先 E2 后（→ E2，无重叠，`e1=null`）、同日重叠（→ E2，`overlap=true`，E1/E2 详情齐全）。原有重叠测试仍通过。
```
.venv/bin/python -m unittest tests.test_decision_events
Ran 29 tests ... OK
```
第 3 节第 1、7 条中“多个候选取最近事件日”现按上述规则理解；§4 的真实实跑结果是返工前取得的，TGT / INTU 的重叠案例均为同日（E1 的 D0 与关键时刻同一交易日），规则变更不影响它们，但未重跑。
