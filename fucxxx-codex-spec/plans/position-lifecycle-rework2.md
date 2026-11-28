# L1 返工 2（依据 astra 复查，2026-11-28）

复查全文：`.local/runs/lifecycle-design-20261128/astra-recheck.md`。一位实现者顺序完成。必须跑：
`.venv/bin/python -m unittest tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration tests.test_decision_ledger tests.test_decision_scoring tests.test_decision_events tests.test_stock_data_tools -v` 与 `bash -n scripts/dev-research.sh`。不 commit、不调用模型、不启动子 Agent。结果追加到 `fucxxx-codex-spec/evidence/position-lifecycle-h3.md` 末尾“返工 2”一节。

可写：`product/mcp/data_tools.py`（只改拆股还原相关函数）、`product/mcp/plan_ledger.py`、`product/deterministic/plan_math.py`、`scripts/score-plans.py`、`scripts/dev-research.sh`（只改 --plan / --review 的提示文字）、`tests/test_plan_math.py`、`tests/test_plan_ledger.py`、`tests/test_plan_integration.py`、`tests/test_stock_data_tools.py`（只新增拆股缓存的测试）、证据文件。

1. **拆股重复还原（#1，高）**：`data_tools.get_price_history` 带 `as_of` 时，只还原“截止日之后、且在该行情响应实际获取时间（缓存记录的 retrieved_at）之前或当天”发生的拆股；获取时间之后才发生的拆股，响应里的价格本来就是拆股前口径，不能再乘。先读清缓存与 `_later_split_factor` 的实际结构再改；改动必须保持其他调用方在“响应获取时间晚于全部拆股”的常见情形下结果逐字节不变（加回归测试）。测试：拆股前缓存的开盘 100、截止后 2:1 拆股 → 带 as_of 返回 100，不是 200；拆股后获取的响应 → 返回还原后的值。`score-plans.py`：拆股比例无法解析且结算依赖它时，相关计划三线记 `not_settleable`（flag `split_ratio_unparsed`），不得用未还原价格继续算。
2. **历史写入泄露未来（#2）**：回放会话写入（修订、复核、选择）时，如果该计划在截止点之后已有任何记录，一律返回 `HISTORY_WRITE_CONFLICT: this plan has records after the replay cutoff`，信息里不得透露未来记录的种类或动作；`ABANDON_AFTER_EXIT` 等判断只基于截止点之前的记录。
3. **日期格式（#4）**：`published_at` 只接受 `YYYY-MM-DD`（按区间处理）或带时区的完整 ISO 日期时间；`20260303`、无时区的日期时间等一律 `PUBLISHED_AT_INVALID`。
4. **到期判断（#6）**：当 `as_of >= cap_date`，且日历中 cap_date 之前（含）没有冻结后的可成交开盘时，即报 `expired_unfilled`，不等日历出现下一个交易日。
5. **同时刻选择（新问题）**：`record_plan_choice` 允许有效时间等于所引用记录（计划或复核）的有效时间，仍拒绝引用截止点之后的记录。回放当天对新计划记 `followed` 要能通过。
6. **回放提示（#12）**：`dev-research.sh` 的 `--plan`、`--review` 回放提示改为：“带 as_of 参数的数据工具都传 as_of={日期}；计划工具由会话回放设置自动限定。”其他模式不变。
