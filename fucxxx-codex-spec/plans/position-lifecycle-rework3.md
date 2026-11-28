# L1 返工 3：纸面成交改为限价挂单（2026-11-28）

**依据**：历史走查（TER 2025-07-30、GS 2026-07-14、MRVL 2026-03-06，Codex terra）三份计划全部 unfilled：模型把区间定在参考价 ±1–2%，而成交规则只看冻结后第一个开盘（TER 开 108.50 > 上限 108；GS 1148.42 > 1142；MRVL 87.93 < 下限 88）。隔夜 1–2% 的偏离很常见，这样计划多数会落空，工具不可用。

**新规则（主会话决定，写入子设计）**：
- 计划新增字段 `entry_valid_sessions`（调用方提供，整数 1–10，默认 5）：挂单从冻结后第一个常规交易日起，最多有效这么多个交易日。
- 逐日（只看已完成交易日）：
  1. 若当日开盘在 `[lo, hi]` 内 → 按开盘价成交；
  2. 否则若开盘 > hi 且当日最低价 ≤ hi → 按 hi 成交（限价买单在上限成交）；
  3. 否则若开盘 < lo → 当日不成交（价格跌出区间下方，不追低），继续看下一日；
  4. 否则（开盘 > hi 且最低价 > hi）→ 当日不成交，继续。
  - 成交前任一日收盘 ≤ 初始失效价 → 挂单取消，状态 `cancelled_stop_before_fill`（无成交、无成本）。
  - 有效期内都没成交 → `unfilled`；首个交易日缺开盘 → 该日跳过并记 flag `missing_open`（不再整体 not_fillable，除非有效期内全部缺价）。
  - 第一个可成交日晚于 cap_date → `expired_unfilled`（不变）。
- 成交后的止损、复核、cap 规则不变；止损检查从成交日收盘开始。
- R0 仍为 (entry_ref − price_invalidation) × shares_planned，不随实际成交价改变；实际成交价进入损益。
- 三条线（照计划 / 持有 / 简单退出）共用同一成交。
- 复核若在成交前给出 EXIT → `cancelled_before_fill`（不变）。

**实现者（Sonnet）可写**：`product/deterministic/plan_math.py`（需要 high 价格：`Bars` 新增 `low` 列，可选，缺失时规则 2 不适用）、`scripts/score-plans.py`（传入 low；报告写明挂单有效期与成交方式“开盘/限价上限”）、`product/mcp/plan_ledger.py`（新增 `entry_valid_sessions` 字段与校验，旧记录缺省按 1 处理以保持旧结算不变）、`product/mcp/server.py`（只改 `save_trade_plan` 的参数与 docstring）、`tests/test_plan_math.py`、`tests/test_plan_ledger.py`、`tests/test_plan_integration.py`、`fucxxx-codex-spec/evidence/position-lifecycle-h3.md`（追加“返工 3”）。

**测试**：四种日内情形各一例；有效期内第 3 天成交；成交前收盘跌破失效位取消；全部缺价；旧记录（无字段）结算结果与现在逐字一致；A 用例（MU）结算不变。跑：
`.venv/bin/python -m unittest tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration tests.test_decision_ledger tests.test_decision_scoring tests.test_decision_events tests.test_stock_data_tools -v`。不 commit、不调用模型、不启动子 Agent。
