# T4 评分 — 证据

状态：完成（T4 判据全部满足）。未 commit、未 push、未调用模型、未写 `.local/data/`。
依据：协议 v1 §3–§8、子设计 T4、plan §1 T4 判据。

## 改了哪些文件（均在 plan §0 T4 行内）
- `product/deterministic/decision_scoring.py`（新）
- `scripts/score-decisions.py`（新）
- `tests/test_decision_scoring.py`（新）
- `fucxxx-codex-spec/evidence/decision-card-t4.md`（本文件）

## 函数签名（`decision_scoring.py`，只做数学，不联网）
单位：收益、Δ、成本一律百分点/标准仓位（=100）；价格是对齐到同一交易日历的列表，缺价为 None/NaN；价格接受数值字符串（`get_price_history` 返回字符串）。

| 函数 | 说明 |
|---|---|
| `fill(decided_at_utc, dates, opens, closes, adj_closes) -> dict` | `status` = `ok`（`index`、`date`、`adj_open`）／`not_fillable`（当日 open、close、adj_close 任一缺失，不用收盘价代替）／`pending`（日历里还没有之后的交易日）。NY 时间 < 09:30 取当日，否则取下一交易日；周末、夏令时已测 |
| `window_return(opens, closes, adj_closes, entry_index, h) -> float \| None` | 入场日复权开盘 → 第 h 日（= `entry_index + h − 1`）复权收盘；窗口越界或缺价 → None |
| `path_min(...)` | 1..h 日复权收盘最低值相对入场价，百分点（次要报告用） |
| `delta(w0, w1, r_stock, r_alt, dest) -> (Δ, cost)` | `dest` = `sector_etf`（2 腿）/ `cash`（1 腿，R_alt = 0）；成本 = 0.2 × \|w1−w0\| × 腿数 |
| `baselines(record) -> {"B0","B1","B2"}` | 返回各基线的 w1；E2：`deviation_z ≤ −2` → 0.5×w0，否则 w0；E1：恒减半；E0：持有；B2 读 `attribution.explicit_guidance_cut`；E2 缺 `deviation_z` → B1 为 None |
| `score_record(record, calendar, stock: Prices \| None, bench: Prices \| None) -> dict` | （返工后签名）单条：状态按序 `pending / price_error / not_fillable / unscorable / etf_unscorable / late / scored`，`r_stock`、`r_etf`，`delta{,_b1,_b2}_{etf,cash}`，`late_sessions`，`path_min`；回放记录用 `decided_at_effective`（`fill_time`）。E2 记录带 `event.accession` 或 `event.d0` 时另存 `aux20_{etf,cash}` |
| `align_prices(calendar, rows) -> Prices \| None` | （返工后）把一条序列放到独立日历上；日历日缺整行 = 该日缺价，日历外的行忽略；`rows=None` → None |
| `entry_index(decided_at, dates)` / `matured(decided_at, dates, h)` | 只看日历的入场索引与到期判断，与价格是否可用无关 |
| `block_bootstrap(events, week_of, L, reps=10000, seed=20261122, level=0.90) -> (lo, hi) \| None` | `events` 为每事件的值，`week_of` 为平行的成交周编号（`week_index(fill_date)`，周一起、跨年连续）；W = 首到末成交周（含空周）；每次抽 ⌈W/L⌉ 个起点、各取连续 L 周（循环回绕）；`W < 3L` → None；`numpy.default_rng(20261122)`；分位数用 numpy 默认线性插值 |
| `verdict(ci_delta, ci_diff, mue=0.20, interim=False)` | `not_worth` → `supported` → `insufficient`，按序取第一个；中期只可能返回 `stop_not_worth` / `continue` |
| `is_final(n, as_of)` / `cap_sample(scored, cap=255)` / `summarize(rows, key, L, key_b1)` / `interim_snapshot(scored, L)` | 最终条件（255 个或到 2028-06-30）；按成交日取前 255，第 255 个所在成交日全部纳入；均值与区间（含配对差）；一次性的中期快照（见返工 3） |
| `build_events(rows)` / `funnel(events, group="E2")` | 把账本行按 (ticker, event_date) 连成事件（扫描事件一个键；回放、按需各自独立）；漏斗各层计数与排除数（含 `price_error`、`no_selection`）、缺失率与是否 >10% |

## 实际命令与输出摘要
```
.venv/bin/python -m unittest tests.test_decision_scoring
Ran 45 tests — OK（首轮；返工后为 56 个，见“返工”）
```
覆盖（plan T4 判据逐条）：
- **协议 §8 三行**：`Protocol8`——例 1 −3.7／−6.1、例 2 +2.3／−1.6、例 3 +1.8／+2.9（ETF／现金），HOLD 为 (0, 0)；另有从手造价格序列经 `score_record` 端到端复算同样三行，以及 B1 同为 REDUCE 时配对差 = 0。
- **fill**：09:29 / 09:30 / 收盘后、夏令时、周五晚／周六／周日、缺开盘（`not_fillable`，且不出现 `adj_open`）、缺 close 或 adj_close、之后无交易日 → `pending`、复权开盘公式。
- **缺价口径**：个股结算缺价 → `unscorable`（Δ 的任何口径都不存在）；ETF 结算缺价、ETF 入场缺开盘、没有 ETF → `etf_unscorable` 且现金 Δ 照算（−6.1）。
- **迟到**：fill 距事件日 3 个交易日仍正常，4 个交易日 → `late`（仍算出 Δ，只是不进主样本）。
- **自助法**：固定种子重复一致；W = 35 / 36（L=12）与 W = 11 / 12（L=4）的边界；与朴素循环实现用同一组抽样逐点相等；两个统计量共用同一组抽样（平移 5 后区间平移 5）；空周计入 W。
- **判定**：互斥与顺序（“上限 < MUE”优先于“支持”）、MUE 边界（上限 = 0.20 不算不值得）、下限必须严格 > 0、区间不可用 → 证据不足、中期只能停不能“支持”。
- **漏斗与缺失率**：手造 17 个候选（不含回放、按需、E1），逐层 17 → 14 → 11 → 10 → 9 → 7 → 6，缺失率 = (失败已到期 1 + 无记录已到期 1 + not_fillable 1 + unscorable 2) ÷ (无决策已到期 2 + 决策已到期 10) = 5/12；未到期的不进分子分母；恰 10% 不标“偏高”，超过才标。
- **脚本**：`ScriptSmoke` 打补丁取价，对临时账本跑 `main()`，检查漏斗、主检验、次要报告、逐条、回放各节，回放记录不出现在主样本段，§8 例 1 的 −3.70 出现在输出里。

对构造的小账本跑真实价格（Yahoo 缓存，首轮用的临时账本（已清理，返工后改在 `.local/runs/t4-rework-20261122/`），6 行：E2 扫描、E1 扫描、回放、按需 BUY、未抽中、失败）：
```
.venv/bin/python -I scripts/score-decisions.py --ledger <临时账本> --out <报告.md>
```
输出 Markdown 含漏斗、主检验、次要报告、逐条、回放各节。独立复算 AAPL（E2，2026-06-10 入场、60 日）：R_stock = +12.985%，R_XLK = +4.508%，Δ = −0.5×(12.985−4.508)−0.2 = −4.44，与脚本一致。另用 130 条合成账本（`mock` 价格）检验区间可用路径：W = 52 周、阶段“中期查看”、判定只可能是 `stop_not_worth`/`continue`。

## 对协议和上游接口的理解与假设（请主会话核对）
1. **账本行类型**：总设计 §3.6 列出 `selection / decision / failure / not_fillable`，但 T2 只产生 `decision`（`decision-record.py` 追加时写 `kind="decision"`）。`selection` 与 `failure` 行的字段没有定义，我按最小假设读取：`{kind, ticker, group, event_date, selected(bool，selection 用)}`，可选 `decided_at`/`selected_at`（用于估算“无决策事件”的窗口是否已到期，缺则用事件日 16:00 NY）。`not_fillable` 行忽略，因为是否可成交由价格推出。P2 写这两类行时需按此字段，或回写本文件再改。
2. **无决策事件的“已到期”**：失败／有 selection 但无决策的事件没有成交日，我用 SPY 日历、假设的成交日与 h 估计其窗口是否已结束；已结束的计入缺失率的分子和分母，没结束的不计（协议 §6 “未到期不计”）。“选中但没有 decision 也没有 failure”记为“无记录”，到期后同样算缺失，避免漏记事件绕过缺失率。
3. **主样本事件的键**：扫描事件以 (ticker, event_date) 为一个事件；回放与按需记录各自独立，不与扫描事件合并；同一扫描事件重复决策时保留最早一条。
4. **“按层（原池／新增）”**：`decision/v2` 没有层字段，脚本读记录里可选的 `tier`，缺则显示“未记录”。P2 要出这一栏需在记录或 selection 行里写 `tier`。
5. **路径最低分位**：协议只说“途中最低收盘（相对入场）的 10% 分位，建议仓位与 B0 分别计算”；我按股票腿 `w × 路径最低` 计算（不含资金去向腿）。含义有歧义，仅是次要报告。
6. **时间上限**：到 2028-06-30 时“只用当日前已到期的事件”按 `exit_date < 2028-06-30` 实现。
7. **中期查看**：脚本只能看到快照，无法知道“第一次达到 100 个”是否已过；它在 n≥100 且 W≥3L 且未到最终条件时显示“中期查看”，只给出“停止／继续”。是否真正动作由主会话把握。
8. 评分日默认取美东当日（16:00 前取前一日），价格只取到该日，避免用盘中价；`--as-of` 可固定。
9. 取价失败的记录标 `price_error`，不进任何漏斗层，并在“警告”节列出，不静默当成缺价。

## 未完成项／已知限制
- `selection`、`failure`、`tier` 的字段契约未由上游定义（见上 1、4）。
- 每条评分都要实时取价，100+ 事件时会多次请求 Yahoo（有缓存）；P2 规模如嫌慢可再做批量，但 T4 不需要。
- 交易日历取自 SPY 行情；若 SPY 自己缺某个交易日，该日会从日历消失（数据源限制）。
- 没有对真实 `trade_decisions.jsonl` 里的 T2 记录做联调（T2 还在写）；字段读取与 T2 当前代码核对过（`kind`、`decided_at_effective`、`replay`、`w0`、`w1`、`horizon_days`、`event.event_date`、`event.deviation_z`、`attribution.explicit_guidance_cut`、`p_outperform.case`、`benchmark`）。

## 回写建议
- plan §3：T4 完成，以上假设 1、4 需要主会话决定：是否在 `decision-record.py`/P2 扫描里约定 `selection`、`failure` 行字段与 `tier`。
- 子设计 T4：把“漏斗分母、`late` 与 `etf_unscorable` 的先后顺序（先可评分、后迟到）”写进去，与协议 §6 一致即可，不改判据。
- 无需改协议；本次没有遇到需要 v2 的矛盾。

## 返工（2026-11-22，Codex Astra 复核第 6、7、8 条）
命令：`.venv/bin/python -m unittest tests.test_decision_scoring` → Ran 56 tests — OK（第一次返工后；第二次返工后为 61 个，见下；原 45 个，新增日历、到期、`price_error`、`no_selection`、中期快照测试，改写了断言旧行为的 3 个）。临时产物只放在 `.local/runs/t4-rework-20261122/`（构造账本与真实价格的报告；单测的临时目录也建在 `.local/runs/` 下并自动删除）；`/tmp` 里的上次产物已清理。

1. **漏斗与缺失率**
   - (a) 到期只看日历：`score_record` 先用 `entry_index` 判断入场与第 h 日是否都已在日历内，未到期一律 `pending`，与能否成交无关；之后才判 `price_error` / `not_fillable` / `unscorable`。测试：入场日缺开盘的 60 日记录在日历不足时为 `pending`，漏斗里分子分母都是 0；同样的缺价在窗口已到期时为 `not_fillable`。无决策事件也用同一个 `matured`（SPY 日历）。
   - (b) 个股取价失败：`score_record(..., stock=None)`，到期后状态 `price_error`，漏斗新增“取到行情”一层，`price_error` 单列并计入缺失率分子（未到期则 `pending`）。脚本不再把这类候选从漏斗删除，警告节也列出原因。无法取得 SPY 日历时脚本直接拒绝运行（无法判定任何到期）。
   - (c) 缺 `selection` 行的扫描事件（含只有 `decision` 或只有 `failure` 的）不再视为抽中：`selected = None`，漏斗“无 selection 记录”单列，不进主样本、不进缺失率，并在漏斗下方与警告节列出 ticker、事件日、id。原断言“自动视为抽中”的测试已改为断言 `selected is None`。
2. **独立交易日历**：脚本取 SPY 行情日期为唯一日历（`no_sector` 也用它）；个股与 ETF 按日历对齐，日历日缺整行 = 缺价，不会消失或顺延。测试：个股缺入场日整行 → `not_fillable` 且成交日仍为日历上的那一日；ETF 缺入场整行 → `etf_unscorable`；个股与 ETF 同日在窗口内缺行 → 结算日不变；`no_sector` 个股窗口内缺行 → 结算日不变；结算日整行缺失 → `unscorable`，不会改在下一行结算；日历外的行被忽略。迟到天数现在也按日历计。局限：若 SPY 自己缺某个交易日，该日仍会从日历消失（数据源限制，已在“限制”里记录）。
3. **中期查看只一次**：`interim_snapshot(main_sample, L)` 按成交日排序、逐个成交日累加，第一次同时满足“已到期 ≥ 100 且 W ≥ 3L”的前缀就是快照样本，只在该样本上算一次区间并给出 `stop_not_worth` / `continue`（永不输出“支持”）。若 100 个早已到齐、W 才是限制条件，则推迟到 W 达到 3L 的成交周，并把该周全部事件纳入（我对协议“推迟到 W ≥ 3L 的那一周”的解释）；达到 100 个当日的事件全部纳入。脚本每次运行都重算这个快照，结果只由前缀决定，后续更多样本不会改变它。`analysis_stage` 已删除，改为 `is_final`；主检验只在最终条件下给判定，其余阶段区间仅作描述。测试：99 个或 W<3L 不触发；100 个且 W 够 → 当日截止并含同日全部；W 受限 → 36 周整周；首个 100 个 `continue`，加到 120 个（后 20 个拖低均值）快照完全相同且不出现新的停止；首个 100 个为停止则 `stop_not_worth`；即使显著为正也只是 `continue`。

对真实价格重跑构造账本（`.local/runs/t4-rework-20261122/ledger.jsonl`）：AAPL E2 仍为 Δ(ETF) −4.44；漏斗显示未抽中 1、无 selection 记录 1（INTU，列入警告）、决策失败 1（已到期，计入缺失率 1/2）。

仍待主会话决定的点：`selection`/`failure` 行字段与 `tier`（见前文假设 1、4）、中期“整周纳入”的解释（上文 3）。

### 第二次返工（Codex Astra 定向复核第 8 条：中期快照随到期事件漂移）
命令：`.venv/bin/python -m unittest tests.test_decision_scoring` → Ran 61 tests — OK。上一节第 3 条中“按成交日累加、W 受限时再补整周”的做法已被取代，规则改为主会话已定的**整周快照**：
- **触发周**：按成交周累加主样本（已到期事件），第一个同时满足“累计 ≥ 100 且 W ≥ 3L”的成交周（W = 首个主样本成交周到该周，含空周）。
- **快照** = 成交周 ≤ 触发周的全部主样本事件。
- **待定**：`interim_snapshot(scored, L, pending)` 新增 `pending` 参数（漏斗返回的 `fn["pending"]`，即决策成功但窗口未到期、已知成交日的记录；`score_record` 现在在入场日已知时就写 `fill_date`，只是没有 `exit_date`）。成交周 ≤ 触发周的 pending 只要还有，就返回 `state = "pending"`（只给触发周、样本数、待到期数，不给区间和判定），脚本显示“中期查看待定（触发周事件未全部到期）”。更晚成交周的 pending 不阻塞。
- **输出一次**：触发周的全部事件到期后第一次返回 `state = "ready"`，带区间与判定（`stop_not_worth` / `continue`，永不“支持”）。之后的运行样本只取 ≤ 触发周的事件，快照和判定逐字相同。
- **测试**（`InterimSnapshot`）：复现复核场景——每周 4 条，141 条已到期、3 条 pending → 待定且无判定；144 条全部到期 → 快照 n = 144、截止最后一条成交日，触发周起点为该周周一；之后 160、200 条（含更晚周的 pending）的快照与 144 条那次完全相等（含判定）；更早周有 pending 也会推迟；更晚周的 pending 不阻塞；无成交日的 pending 被忽略；`score_record` 对未到期记录保留 `fill_date`、没有 `exit_date`；漏斗 `fn["pending"]` 列出未到期记录。
- 脚本级冒烟：150 个合成扫描事件，在两个不同评分日（中间到期事件增多）运行，两次输出的中期行逐字相同（触发周 2026-10-12、n = 100、stop_not_worth）。
- 对协议的理解：“触发周”按“已到期事件数”首次达到 100 判断，“第一次输出判定”要等该周及更早周的事件全部到期（主会话已定）；该规则比协议原文多了一层等待，但不改变阈值、区间或判定顺序。
