# H1 结算数学：证据

任务：`fucxxx-codex-spec/plans/position-lifecycle-impl.md` §2 H1。执行者：Sonnet 5.5 子 Agent。日期：2026-11-28。

## 修改的文件
- `product/deterministic/plan_math.py`（新）
- `tests/test_plan_math.py`（新）
- `fucxxx-codex-spec/evidence/position-lifecycle-h1.md`（本文件，新）

只 import `product.deterministic.decision_scoring` 的 `NY`、`entry_index`、`parse_utc`、`num`，未修改它。不联网、不读文件、未 commit。

## 接口
```python
COST_BPS_PER_SIDE = 10; CORP_ACTION_TOL = 0.015; MAX_HORIZON_DAYS = 120
class PlanMathError(ValueError)          # message 以大写错误码开头

def size_position(entry_ref, price_invalidation, risk_budget) -> {"risk_per_share", "shares", "r0"}
@dataclass Bars: dates, open, close, adj_close
def settle(plan, revisions, reviews, bars, as_of, cost_bps_per_side=10) -> dict
```
错误码：`INVALID_NUMBER`、`STOP_NOT_BELOW_ENTRY`、`RISK_BUDGET_TOO_SMALL`（sizing）；`INVALID_AS_OF`、`INVALID_BARS`、`INVALID_PLAN`、`INVALID_REVISION`、`INVALID_REVIEW`、`INVALID_NUMBER`（settle）。

`settle` 返回：
```
{"as_of", "cap_date", "cap_trading_day" (未到 cap 为 None), "cost_bps_per_side",
 "stop_versions": [{"version", "effective_at", "price_invalidation"}],      # 版本 1 = 初始；修订版本 = 修订顺序 + 2
 "fill": {"status": filled|pending|not_fillable|unfilled, "index", "date", "open", "shares", "entry_band"},
 "lines": {"plan"|"hold"|"simple_exit": {"status", "legs", "gross", "costs", "net", "r", "return_pct",
                                         "min_close_r", "unrealized", "end_date", "flags"}},
 "pairs": {"plan_minus_hold": {"usd","r"}|None, "plan_minus_simple": {...}|None}}
```
leg：`date, side, price, shares, reason(fill|stop|review|cap|value)`；stop 的 leg 额外带 `trigger_date`、`trigger_close`、`stop`（当时有效失效价）；review 的 leg 带 `review_id`。金额四舍五入 0.01，R 与 `min_close_r` 0.001，`return_pct` 0.01。

## 测试
命令：`.venv/bin/python -m unittest tests.test_plan_math -v`
输出摘要：`Ran 35 tests ... OK`。覆盖：size_position 数值与三类错误（含 Decimal 精度）；成交（pending、unfilled、区间端点、not_fillable、cap_date 用纽约日期）；正常持有到 cap 且三线相同、配对差 0；跳空 R=-2.038；修订提高失效价、修订恰在 16:00 次日生效、非失效价修订不重置；REDUCE 后 EXIT；1 股 REDUCE 全卖；复核早于成交的 EXIT 取消、REDUCE 忽略；同开盘止损与 EXIT/REDUCE 只执行一次；as_of 估值（不算卖出成本）、as_of 当天触发止损而次日开盘未到；as_of 之后的行情不影响结果；cap 日需 as_of >= cap_date、周末 cap、horizon=1；cap 日优先于止损；开盘缺失顺延、收盘缺失顺延 cap、收盘缺失不检查止损；成本两边与参数；公司行为（拆股、2%、1%、成交日前变化）；输入校验。数值用例的手算过程写在测试注释里。附带确认 `tests.test_decision_scoring` 仍通过。

## 实现中的取舍（设计未写清，按保守理解）
1. **cap 何时算到达**：只有 `as_of >= cap_date`（日历日）才确定 cap 交易日并离场；否则按 `open` 估值。as_of 恰为 cap 前最后交易日而 cap_date 落在周末时，结果是 `open`（估值），不是 `closed`；数字相同，只差卖出成本。建议评分时 as_of 取在 cap_date 之后。
2. **修订链**：当时有效失效价 = effective_at 早于当日纽约 16:00 的**最后一个含 `price_invalidation` 的修订**；只改 `hold_basis` 等其他字段的修订不会把止损重置回初始值。
3. **同一开盘多条离场**：任何 EXIT 或止损 → 全部卖出一次，同时有 EXIT 与止损时 reason 记 `review`（EXIT 优先）；只有多条 REDUCE → 只执行一次并标 `multiple_reduce_same_open`；止损与 REDUCE 同时 → 止损（全部卖出）。
4. **cap 与止损同日**：cap 日收盘直接离场（原因 cap），不再检查止损；cap 日收盘缺失则顺延，顺延期间不检查止损。
5. **失败状态下的金额**：`unfilled`、`not_fillable`、`pending`、`cancelled_before_fill`、`not_settleable` 的 gross/costs/net/r/return_pct/min_close_r 一律为 `None`（不声称结果为 0），只靠 status 进漏斗。
6. **公司行为窗口**：从成交日到三条线中最晚的结束日（已平仓取最后一笔，持有中取 as_of 前最后一根）；比值最大/最小 − 1 > 1.5% → 三条线 `not_settleable`、金额置 None。`cancelled_before_fill` 的计划线无成交，保留该状态，仅加 flag。
7. **取消复核的范围**：执行开盘 ≤ 成交开盘的 EXIT 只取消**计划线**；持有对照与简单退出仍成交并结算，配对差为 None。
8. **持有中无任何收盘价可估值**：三线 `not_settleable`，flag `no_close_to_value`。as_of 当天无收盘但更早有收盘时按更早收盘估值并标 `stale_valuation`。
9. **舍入**：金额、R 与配对差均由未舍入数值一次舍入；手算时按 legs 算到分、再舍入，结果一致到舍入误差。`size_position` 的 `risk_per_share` 与 `r0` 不舍入（Decimal 精确转 float），股数用 Decimal 以避免 `floor(1000/0.1)` 之类的浮点误差。
10. **未到的复核**：执行开盘不在 as_of 之前日历内的复核不影响结果，计划线 flag `review_pending_execution`；持有时 as_of 仍有未执行的止损/复核离场，flag `exit_pending_at_as_of`。
11. 额外输出（设计未要求）：`stop_versions`（版本链）、`cap_trading_day`、`end_date`、stop leg 的触发信息，用于手算与版本链报告。

## 未完成项
无。H1 范围内的规则均已实现并有测试。`score-plans.py` 的取数与 Markdown 由 H3 完成；漏斗计数不在本模块。

## 对设计的回写建议
- “三线结算”一节的执行顺序（止损 → 复核 → cap）与 plan 规则 3 的顺序（开盘离场 → cap 收盘 → 止损）不一致；实现按 plan 规则 3，建议设计回写为：每日先执行当日开盘的待执行离场，再按收盘判断 cap，最后判断止损。
- 补一句：cap 日以 `as_of >= cap_date` 为到达条件；`score-plans.py` 应在计划到期后用 as_of >= cap_date 评分，否则只给 `open` 估值。
- 补一句：修订链只取含 `price_invalidation` 的修订；`not_settleable`/`unfilled` 等状态金额为空而非 0，漏斗只计数。
- “简单退出对照”忽略修订与复核已按设计实现；因此本线只回答“初始失效价 + cap”。若用户想比较“移动失效位是否有价值”，这条线正是对照基准。

## 返工 1（R-B：结算，依据 astra 复核 #1 #3 #6 #7）

改动（`product/deterministic/plan_math.py`，`tests/test_plan_math.py`）：
1. **拆股（#1）**：`settle(..., splits=[[ex_date, ratio], ...])`。从冻结日（纽约日期，不晚于成交日）到三条线中最晚结束日之间有拆股 → 三条线 `not_settleable`、金额置 None、flag `split_in_window`（`cancelled_before_fill` 保留状态，只加 flag）；拆股晚于结束日不影响。冻结日到成交日之间有拆股时（区间与成交开盘口径不同）整体 `not_settleable`，`fill.status = not_settleable`。`splits` 日期格式非法 → `INVALID_SPLITS`。比例只供展示，数学层只看日期；还原价格口径由 `score-plans.py` 负责（见 h3）。
2. **按截止点截断（#3）**：`settle` 内部忽略 `effective_at` / `reviewed_at_effective` 晚于 as_of 当日 16:00 纽约的修订与复核（恰为 16:00 保留）；`stop_versions` 同步截断；未来复核不再产生 `review_pending_execution`。
3. **到期前无可成交开盘（#6）**：成交日（冻结后第一个开盘）晚于 cap_date → `expired_unfilled`（`fill.status` 同名），三条线无成交、无成本、金额 None，配对差 None；删除“cap 交易日 = max(i, …)”的托高，cap 交易日取日历中不晚于 cap_date 的最后一天（必然 >= 成交日）。该判断先于缺开盘/区间判断。
4. **提前收市（#7）**：L1 不建模；含 `price_invalidation` 的修订生效于纽约 13:00–16:00（含 13:00，不含 16:00）→ 计划线 flag `revision_same_day_check`。只对改失效价的修订打标（其他字段的修订不影响结算）。
5. `Bars` 约定改述为“未复权（当时每股口径）”：调用方负责把上游已按拆股调整的价格还原。

测试：`.venv/bin/python -m unittest tests.test_plan_math -v` → `Ran 47 tests ... OK`（原 35 + 新增 12：成交后评分日前拆股；持仓结束后拆股；评分日后拆股（窗口外）；冻结与成交之间拆股；冻结日当天/前一天的边界；`INVALID_SPLITS`；未来修订与复核被忽略且与“账本里从未有过”的结果完全相等；16:00 整点保留、16:00:01 排除；周末到期、休市日到期、cap 日 = 成交日仍成交；13:00–16:00 修订标记及 12:59:59 与 16:00 边界）。联跑 `tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration`：134 tests OK（含另一位实现者当时的账本测试）。`tests.test_decision_scoring` 仍通过。

未完成项：
- 提前收市日不建模，仅标记待人工核对（按返工文件第 5 条）。
- 数学层只认拆股日期；比例解析与价格还原在脚本层。拆股当日复核/修订的细粒度（盘前/盘后）不区分，窗口按日期闭区间保守判断。
- 真实行情的拆股还原只用 mock 验证，未对真实 Yahoo 数据实测。
