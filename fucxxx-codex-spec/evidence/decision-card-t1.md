# T1 开盘口径分布 —— 证据

执行者：Sonnet 子 session。范围：plan §0 的 T1 行。未 commit、未 push、未调用模型、未写 `.local/data/`。

## 结论
T1 判据全部满足。重建表后行数与旧表相同（90616 行），原 `outcome` 逐行相等；`get_key_moments` 已改读 `outcome_open`。设计契约无需改变。

## 修改的文件
- `product/deterministic/key_moments.py`：新增 `outcome_open`；`outcome` 未动。
- `scripts/build-key-moments.py`：新增 `prices()`（日期、复权收盘、复权开盘）；每行同时写 `outcome` 与 `outcome_open`（含 `baseline_days`）；新增 `--end YYYY-MM-DD`（复现某天的建表，价格响应走缓存）；`--report` 改读 `outcome_open` 并在头部注明口径；meta 增加 `entry_rules`、`price_end`。
- `product/mcp/reference_tools.py`：只改 `get_key_moments`（`stats`、`same_moments_in_this_ticker`、provenance）。`_key_moment_events` 未改（整行加载，新字段自然带入）。
- `evals/key-moments/distribution-close-entry-2026-11-11.md`（新，旧 latest 的原样副本）、`evals/key-moments/distribution-latest.md`（按开盘口径重写，头部注明口径与旧文件位置）。
- `tests/test_key_moments_open.py`（新）。
- `.local/cache/derived/signals/key-moments.jsonl`、`key-moments-meta.json`（重建）；备份：`key-moments-close-entry-2026-11-11.jsonl`、`key-moments-meta-close-entry-2026-11-11.json`（同目录，`key-moments*` 范围内）。

## 新接口
```python
outcome_open(dates: list[str], opens_adj: list[float | None], closes_adj: list[float | None],
             bench_opens_adj: dict[str, float | None], bench_closes_adj: dict[str, float | None],
             index: int) -> dict
# {"entry_date": dates[index+1] | None,
#  "5"/"20"/"60": None | {"exit_date": dates[index+h], "ret", "excess", "worst"}}
```
- 入场 = `opens_adj[index+1]`（调用方给 `open × adj_close / close`）；第 h 日 = `dates[index+h]` 收盘（入场日为第 1 日）。
- `ret` = 退出收盘 ÷ 入场开盘 − 1；`excess` = `ret` − ETF（同日复权开盘 → 退出日收盘）的收益；`worst` = 入场日至退出日各收盘的最低值 ÷ 入场开盘 − 1（若所有收盘都高于开盘可为正）。
- 缺价规则（对设计中“任一必要价格缺失 → None”的具体化，请主会话确认）：
  - 个股入场开盘缺失、退出收盘缺失或窗口超出数据 → 该 h 为 None；不用收盘代替开盘；
  - 只有 ETF 缺价 → 保留个股单元，`excess = None`（与旧 `outcome` 一致，也与协议 §3 “ETF 缺价只影响 ETF 口径”一致，`summarize` 已按此跳过）。
- `prices(ticker, start, end)`（建表脚本内）：日期与复权收盘与旧 `closes()` 完全一致；复权开盘三值（open、close、adj_close）任一缺失则为 None。

## 实际运行与结果
1. 备份旧表与旧 meta，复制旧分布报告。
2. 重建：`.venv/bin/python -I scripts/build-key-moments.py --end 2026-11-11 --report evals/key-moments/distribution-latest.md`
   - 旧表建于 2026-11-11 10:33Z（美东早 5:33，当日尚无收盘），所以用 `--end 2026-11-11` 复现同一价格窗口，价格走缓存命中（秒级完成，0 errors），使“与旧表逐行比对”不受之后分红再调整的影响。
   - 不带 `--end` 的默认重建会下载到今天的数据，行数会多于旧表，且分红再调整可能改变旧 `outcome` 的末位。以后需要延伸表时应另做比对，不能沿用本次“逐行相等”的结论。
3. 比对（旧备份 vs 新表，内存逐行）：
   - 行数 90616 = 90616；
   - `moment/ticker/date/benchmark/detail` 逐行相同；
   - `outcome` 相等 90616 / 90616，`json.dumps` 重新序列化也逐字相同；
   - 字段集合只有 `benchmark, date, detail, moment, outcome, outcome_open, ticker`。
4. `outcome_open` 抽查：AAPL 2012-01-06 `platform_breakout_new_high`：入场 2012-01-09，5/20/60 日退出日为 2012-01-13 / 2012-02-06 / 2012-04-03（旧口径为 01-17 / 02-07 / 04-04，晚一天，符合“入场日为第 1 日”）。
5. 缺价统计：入场日缺失 0；个股单元为 None 的数量 5/20/60 日 = 126 / 553 / 1567（旧口径 133 / 566 / 1574，少是因为退出早一天）；`excess` 为 None 的单元 10812 个，与旧口径相同（ETF 覆盖缺口一致）。
6. `get_key_moments('AAPL', days=60, as_of='2024-06-28')` 实跑：返回 `platform_breakout`、`sharp_reversal_up`，`baseline_any_day.20d` n=60271，provenance 含 “next session open”。
7. 测试：`.venv/bin/python -m unittest tests.test_key_moments_open tests.test_key_moments tests.test_stock_data_tools` → 38 tests OK。新测试覆盖：入场开盘与第 h 日退出（含入场日为第 1 日）、手算 ret/excess/worst、worst 为正、缺入场开盘/缺退出收盘/缺 ETF/窗口越界/最后一日、旧 `outcome` 不变、`get_key_moments` 读 `outcome_open` 且 provenance 注明口径（mock，无网络）。

## 新旧分布差异（概览）
基线 5 日：旧 上涨概率 55% / 期望 +0.4；新 55% / +0.4。各时刻相对板块中位数仍在 ±0.3pp 内；`platform_breakdown_new_low` 5 日中位收益由 +0.1 变 −0.2，`sharp_reversal_up` 跑赢板块概率由 47% 变 44%。结论与旧报告一致：多数时刻与任意日对照无差别，仅作风险基线。
（`baseline_days` 5 日样本 73024 → 73029：最后几行因退出早一天而多出 5 日结果。）

## 未完成项 / 限制
- 其他读 `outcome` 的脚本（`score-moment-reviews.py`、`sample-idiosyncratic-moments.py`、`audit-moment-context.py`、`build-moment-context.py`）按要求未改，行为不变。
- `key-moments-context.jsonl`（旧上下文表，11-11 20:01 生成）未重建、未触碰。
- `product/skills`、方法卡中未发现写明“次日收盘入场”的文字；`docs/design-decision-first-2026-11-21.md:32` 描述的是旧状态，属历史记录，未改。

## 对设计的回写建议
- 子设计 T1 补一句缺价规则：“ETF 缺价只令 `excess` 为 None，个股单元保留”。
- 子设计/plan 注明：旧表可复现的前提是 `--end 2026-11-11`；表延伸时 `outcome` 逐行相等不再必然成立。

## 返工（2026-11-22，Codex Astra 复核后）

### 1. 严格复权价
- 问题：`prices()` 用 `r[5] or r[4]`，adj_close 缺失时会把普通收盘价当复权收盘传给 `outcome_open`。
- 修改：
  - `product/deterministic/key_moments.py` 新增 `price_series(rows) -> (dates, closes, opens_adj, closes_adj)`：`closes` 仍是旧序列（adj_close，缺则 close，供 `detect` 与旧 `outcome`，**不变**）；`closes_adj` 严格取 adj_close，`opens_adj` = open × adj_close / close，任一缺失为 None，不顶替。
  - `scripts/build-key-moments.py` 的 `prices()` 改调 `price_series`，返回四元组；`outcome_open` 的个股与 ETF 收盘都改用严格序列（ETF：`bench_close_adj`）；旧 `outcome` 仍用 `bench_close`（旧序列）。
- 重建：`.venv/bin/python -I scripts/build-key-moments.py --end 2026-11-11 --report evals/key-moments/distribution-latest.md`（走缓存，0 errors）。
- 比对：行数 90616 = 90616；`moment/ticker/date/detail` 逐行相同；原 `outcome` 相等 90616 / 90616。
- 严格口径的影响（对比返工前的 `outcome_open`）：变成 None 的单元 **0** 个，`ret`/`worst` 数值变化 **0** 个，`excess` 变成 None **0** 个。即这批缓存里凡有 close 的日子 adj_close 都在，旧的顶替从未实际触发；`outcome_open` 为 None 的单元共 2246 个（5/20/60 日 = 126 / 553 / 1567），都来自窗口越界或入场开盘缺失，与返工前相同。严格规则对以后出现 adj_close 缺口的数据才起作用。
- 测试（`tests/test_key_moments_open.py` 新增 `PriceLayerIsStrictTest`）：`price_series` 在 adj_close 缺失 / open 缺失 / 无收盘三种行上的输出；**取价层**：加载 `scripts/build-key-moments.py`，mock `data_tools.get_price_history`，断言 `prices()` 的严格序列不顶替、旧序列保留顶替，并流入 `outcome_open`；路径上缺收盘被忽略、退出日缺收盘为 None。

### 2. `get_key_moments` 盘中不用当日行
- 修改（`product/mcp/reference_tools.py`，只在 `get_key_moments` 内加判断，另补 `dtime`/`timedelta` 导入）：纽约 16:00 之前（含 `as_of=None` 的盘中、盘中时间戳的回放）把日期晚于上一完整交易日的行剔除，再用于 `detect` 与 `state`；与 `classify_decision_event` 的 `last_complete` 规则一致。
- 测试：`test_todays_row_is_not_used_before_the_close`：14:00 NY → `state.date` 为前一日；16:30 NY → 当日；盘中时间戳 as_of → 前一日。
- 未改：统计口径里 `exit_date < cutoff`（按日期字符串）保持原样，盘中和收盘后都只算严格早于 cutoff 日的退出，偏保守，不泄露。

### 运行
- `.venv/bin/python -m unittest tests.test_key_moments_open tests.test_key_moments tests.test_stock_data_tools` → 42 tests OK。
- 真实调用：`get_key_moments('AAPL', days=60, as_of='2024-06-28')` 正常；`as_of=None` 的 `state.date` 为最近完整交易日。
