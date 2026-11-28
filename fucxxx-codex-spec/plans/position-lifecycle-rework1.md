# L1 返工 1（依据 astra 复核，2026-11-28）

复核全文：`.local/runs/lifecycle-design-20261128/astra-code-review.md`（编号 1–12 指其中条目）。两位实现者并行，文件互不重叠；都要跑：
`.venv/bin/python -m unittest tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration -v` 与 `bash -n scripts/dev-research.sh`。不 commit、不调用模型、不启动子 Agent。结果追加到各自证据文件末尾“返工 1”一节。

## R-A（账本）：只可写 `product/mcp/plan_ledger.py`、`product/mcp/server.py`（只改 8 个计划工具的注册与 docstring）、`tests/test_plan_ledger.py`、`fucxxx-codex-spec/evidence/position-lifecycle-h2.md`
1. **回放可见性（#2）**：所有按 id 的读写先校验会话模式（回放会话只能读写回放记录，实时只能实时），不符 → `PLAN_REPLAY_MISMATCH`。`choice` 记录新增工具生成的 `effective_at`（与复核相同的有效时间规则）。`get_trade_plan`、`list_trade_plans`、`active_plans` 先按截止点（实时 = 现在；回放 = 回放日纽约 23:59:59）过滤 candidate/plan/revision/review/choice，再推导 current、active 与摘要；之后生效的记录完全不可见。active 判断里的 abandoned/EXIT 只计截止点之前生效的。
2. **裸日期证据（#4）**：`published_at` 为 YYYY-MM-DD 时视为区间 [当日 00:00, 当日 23:59:59] 纽约时间：“已公开”用上界判断（上界 > 复核有效时间 → `EVIDENCE_TIME_AMBIGUOUS: 给出精确发布时间`，除非日期早于复核纽约日期）；“晚于上次”用下界判断（下界 > 上次有效时间才算新）。带时间的照旧。
3. **改判须有非价格新证据（#10）**：论点结论改变时，至少一项 `kind != price` 的证据为新证据，否则 `NEW_EVIDENCE_REQUIRED`（信息说明价格变化不改变论点结论，价格在动作里处理）。
4. **论点视图（#10）**：`get_trade_plan(plan_id, view="full")` 新增 `view`：`thesis` 只返回 plan 的 thesis、market_misread、catalyst、abandon_facts、hold_basis、review_dates、frozen_at、当前有效版本中的这些字段、以往复核的 `thesis_verdict`、`reviewed_at_effective` 与 `kind != price` 的证据；不含任何报告全文、价格字段（entry、price_invalidation、r0、shares）、动作与 action_reason。`full` 保持现状（但受第 1、5 条约束）。
5. **报告完整性（#9）**：读取报告时从 `settings.data_dir()/plan-reports/` 下按记录 id 定位（不信任任意绝对路径，路径不在该目录下视为缺失），校验 `report_sha256`；返回 `report_integrity: ok|missing|mismatch`，mismatch 时不返回全文。
6. **并发（#8）**：检查（上限、同股、版本号、进行中）与追加放在同一把 `fcntl.flock` 文件锁内（锁文件 `trade_plans.jsonl.lock`），锁内重读账本。测试用两个线程或进程在检查点同步，证明不会出现 9 个或两个 v2。
7. server.py：`get_trade_plan` 增加 `view` 参数与说明；`record_plan_choice` 的 docstring 写明有效时间；不改其他工具。

## R-B（结算与脚本）：只可写 `product/deterministic/plan_math.py`、`scripts/score-plans.py`、`scripts/dev-research.sh`（只改模式互斥）、`tests/test_plan_math.py`、`tests/test_plan_integration.py`、`fucxxx-codex-spec/evidence/position-lifecycle-h1.md`、`-h3.md`
1. **拆股（#1）**：`score-plans.py` 调 `get_price_history` 时传 `as_of=评分日`（还原评分日之后的拆股），并读返回的 `splits`；`settle` 新增参数 `splits: list[[date, ratio]]`，成交日（或冻结日，取较早者）到结束日之间有拆股 → 三条线 `not_settleable`，flag `split_in_window`；拆股发生在结束之后不影响。测试：成交后评分日前拆股、评分日后拆股（经 as_of 还原，不影响）、持仓结束后拆股。
2. **按截止点截断（#3）**：`score-plans.py` 先按评分日纽约 23:59:59 过滤全部记录（与 R-A 第 1 条同一规则，可以自己实现，不 import 未完成的函数），漏斗与报告只含截止前的记录；`settle` 内部忽略 `effective_at` / `reviewed_at_effective` 晚于 as_of 当日收盘（16:00 纽约）的修订与复核，`stop_versions` 输出也截断。回归测试断言整份报告与漏斗不含未来记录。
3. **未完成交易日（#5）**：评分只用已完成的交易日：当 as_of 是今天且纽约时间未到 16:00，或 `get_price_history` 返回 `last_row_incomplete_session=true`，丢弃该日行（报告注明实际截止）。
4. **到期前无可成交开盘（#6）**：冻结后第一个开盘日晚于 cap_date → 状态 `expired_unfilled`，三条线无成交、无成本；覆盖周末与休市日测试。同步删除“cap 交易日 = max(i, …)”的托高。
5. **提前收市（#7）**：L1 不实现，修订若生效于某日 13:00–16:00 纽约之间，在 flags 中加 `revision_same_day_check`，报告提示人工核对提前收市日。
6. **模式冲突（#12）**：`dev-research.sh` 中 `--decision`、`--plan`、`--review`、`--group`、`--moment` 任两个同时给 → usage 退出 2。
