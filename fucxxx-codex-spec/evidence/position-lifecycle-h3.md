# H3 接入：证据

任务：`fucxxx-codex-spec/plans/position-lifecycle-impl.md` §2 H3。执行者：Sonnet 5.5 子 Agent。日期：2026-11-28。

## 修改的文件
- `product/mcp/server.py`：只改 import 行（加 `plan_ledger`）并在 `get_prior_trade_decision` 与 `main` 之间新增 8 个工具；现有工具未动。
- `scripts/score-plans.py`（新）
- `scripts/dev-research.sh`：只新增 `--plan`、`--review`、`--seed-plans`、`STOCK_AGENT_RUN_MODEL`、`run.json` 的 `trade_plans`，以及相应的 usage 行数（`sed -n '2,18p'` 改为 `'2,23p'`，因为头部注释多了 5 行）。
- `tests/test_plan_integration.py`（新）
- `fucxxx-codex-spec/evidence/position-lifecycle-h3.md`（本文件，新）

未 commit、未 push、未调用模型、未实跑 `dev-research.sh`（只跑了 `bash -n`、`--plan` 与 `--review` 互斥的 usage 退出、以及单独抽出 run.json 那段 Python 的测试）。测试全部在临时目录，未写 `.local/data/` 或 `evals/`。

## 接口
### MCP 工具（`server.py`）
| 工具 | 注解 | 备注 |
|---|---|---|
| `size_trade_plan(entry_ref, price_invalidation, risk_budget=1000)` | READ_ONLY | |
| `save_plan_candidate(ticker, outcome, reason, replay_as_of=None, host=None, model=None)` | LOCAL_WRITE | |
| `save_trade_plan(ticker, template, thesis, market_misread, catalyst, abandon_facts, price_invalidation, entry_ref, entry_band, hold_basis, review_dates, horizon_cap_days, report_markdown, risk_budget=1000, replay_as_of=None, host=None, model=None)` | LOCAL_WRITE | 无 `**extra`：MCP 层传入生成字段会被参数校验拒绝（`unexpected keyword argument`），账本层的 `GENERATED_FIELD_NOT_ACCEPTED` 仍由 H2 测试覆盖 |
| `revise_trade_plan(plan_id, reason, sources: list[str\|dict], changes: dict, replay_as_of=None)` | LOCAL_WRITE | |
| `save_plan_review(plan_id, thesis_verdict, evidence, action, action_reason, report_markdown, plan_deviation=False, deviation_reason=None, replay_as_of=None, host=None, model=None)` | LOCAL_WRITE | |
| `record_plan_choice(plan_id, ref_id, choice, note)` | LOCAL_WRITE | |
| `get_trade_plan(plan_id)` | READ_ONLY | |
| `list_trade_plans(ticker=None, active_only=True)` | READ_ONLY | |

全部加 `@explain_errors`，未加 `@point_in_time`。带 `replay_as_of` 的四个写工具在参数缺省时取 `settings.replay_as_of()`（与 `save_trade_decision` 一致；账本层本来也会取，这里显式写出）。docstring 面向模型：生成字段清单、股数与 R0 公式、成交与止损口径、8 个上限与同股限制、复核的新证据规则、`plan_deviation` 的必填关系、回放时间、报告必含标题。

### `scripts/score-plans.py`
`.venv/bin/python -I scripts/score-plans.py [--plans FILE] [--as-of YYYY-MM-DD] [--out FILE.md]`；`main(argv=None) -> int`（0 正常；1 有取价或结算失败；2 取不到 SPY 日历，拒绝评分）。
- 取价：`data_tools.get_price_history`（不传 `as_of`，未复权开盘/收盘），日历 = SPY 交易日，个股用 `decision_scoring.align_prices` 对齐，缺行留在日历内；`PriceBook` 记录失败原因，个股失败 → 该计划 `price_error`、警告段与漏斗单列，退出码 1；盘中数据（`last_row_incomplete_session`）单独警告。
- 每个计划一节：冻结时间、entry_band、股数、R0、失效价版本链、cap_date 与“已到期（cap 交易日）/未到期，open 估值”、复核与用户选择、成交状态、三线汇总表（毛、成本、净、R、收益率、途中最低收盘 R、结束日、flags）、每条线的成交明细表（日期、方向、价格、股数、成交额、成本、原因、说明，止损说明含触发日、触发收盘与失效价）、配对差。
- 末尾漏斗：candidate outcome（plan/wait/not_formed）、计划结算状态（unfilled/not_fillable/pending/cancelled_before_fill/open/closed/not_settleable/price_error/settle_error）、用户选择（followed/declined/abandoned），均分“实时/回放”两列。

### `scripts/dev-research.sh`
- `--plan "想法"`、`--review PLAN_ID`、`--seed-plans FILE`；二者互斥，同时给则 usage 退出 2（在建运行目录前）。`--plan`/`--review` 不再追加默认的“我目前未持有。”。回放说明与 `--decision` 同款（信息截止为当日纽约 23:59，所有工具带 `as_of`，不得用对之后事件的记忆）。
- 两种模式 Codex 开 `web_search="live"`。
- `export STOCK_AGENT_RUN_MODEL="$model"`；另外显式写入 Claude 的运行目录 `mcp.json` 的 `env` 与 Codex 的 `-c mcp_servers.stock_data.env.STOCK_AGENT_RUN_MODEL=...`，因为 MCP 子进程是否继承 shell 环境取决于宿主，`STOCK_AGENT_DATA_DIR` 也是同样的显式传法。其他模式的行为不受影响（只有 `plan_ledger` 读这个变量）。
- `run.json` 新增 `trade_plans`：每行 `kind`、`plan_id`、`ticker`，加上该行有的 `outcome/shares_planned/r0/version/thesis_verdict/action/review_id/choice/replay` 与 `report_path`。

## 测试
```
.venv/bin/python -m unittest tests.test_plan_integration tests.test_plan_ledger tests.test_plan_math tests.test_decision_integration -v
Ran 112 tests in 3.7s ... OK        （integration 11 + ledger 59 + math 35 + decision_integration 7）
bash -n scripts/dev-research.sh      OK
```
`tests/test_plan_integration.py` 的 11 个用例：
- 8 个工具注册，3 个只读、5 个写入，docstring 含生成字段说明。
- 通过 `server` 函数走“保存计划 → 同股再存被拒（`ACTIVE_PLAN_EXISTS`）→ 复核 EXIT → 同股重开”，两个 `plan_id` 不串线，旧计划 `exit_review`、新计划进行中；回放计划在实时会话中不被列出。
- 回放会话（环境变量）下参数缺省取回放日，`STOCK_AGENT_RUN_MODEL` 记为 `run_env`，`list_trade_plans` 只列回放计划；同日修订被拒。
- 错误码以 `ToolError` 传回模型；MCP 层不接受生成字段；未知计划 `get_trade_plan` 返回 `found: false`。
- `score-plans.py` 主函数（mock `get_price_history`）：三线、成交明细、止损触发说明、配对差、cap 已到期/未到期、漏斗计数；全部数字在测试注释里手算（plan 净 +379.60、R +0.380；简单退出净 −1,618.40、R −1.618，跳空超预算；持有净 +579.40、R +0.579，途中最低 R −1.500；配对差 −199.80 / +1,998.00）；第二个计划开盘 110 在区间外 → `unfilled`。
- 未到期时按 as_of 估值并标“未实现”；个股取价失败 → `price_error`、警告段、退出码 1；SPY 失败 → 拒绝评分、退出码 2；空账本。
- `dev-research.sh`：`bash -n`；`--plan` 与 `--review` 互斥且 usage 含新选项；抽出 run.json 的 Python 段，在临时运行目录里执行，确认 `trade_plans` 摘要且原有键不变。

## 未完成项与限制
- 未实跑 `dev-research.sh --plan/--review/--seed-plans`（任务禁止调用模型）。首次实跑要确认：Codex 的 MCP 工具审批——`.codex/config.toml` 只给 `save_decision` 写了 `approval_mode = "approve"`，`save_trade_decision` 现有模式能用说明 `exec` 下写工具可行，但 8 个新工具尚未在 Codex 实测；若被拒，需主会话在 `.codex/config.toml` 加审批项（不在本任务可写范围）。
- `--seed-plans` 只复制 `trade_plans.jsonl`；计划与复核的报告全文在记录里以绝对 `report_path` 指向原运行目录。若种子来自别的运行目录，`get_trade_plan` 的 `report_markdown` 读取原路径，源目录被删则为 `null`（记录本身不受影响，`plan-review` 的第一步要读报告时会缺）。验收时要用 `--seed-plans` 复制回放计划，建议同时保留原运行目录，或之后让 `--seed-plans` 支持复制 `plan-reports/`（需要改设计）。
- `score-plans.py` 对 `price_error` 和 `settle_error` 的计划不给任何金额；用户的 `abandoned`/`declined` 选择不改变结算，只进漏斗（见下条建议）。
- 价格取数不带 `as_of`，沿用 `score-decisions.py`（Yahoo 的开盘/收盘是拆股后调整的口径，分红不调整）；窗口内大额分红会被公司行为检查标成 `not_settleable`。

## 对设计的回写建议
1. 子设计“结算脚本”补：退出码（0/1/2）、行情失败写警告并记 `price_error`/`settle_error`、选择行不影响结算只进漏斗、漏斗分实时/回放两列。
2. 子设计“调试入口”补：`--plan` 与 `--review` 互斥；`STOCK_AGENT_RUN_MODEL` 同时显式写入两个宿主的 MCP 环境；`run.json` 的 `trade_plans` 字段清单；`--seed-plans` 不复制报告文件的限制。
3. 子设计“MCP 工具”补：`save_trade_plan` 在 MCP 层没有 `**extra`，生成字段由 MCP 参数校验拒绝，账本层的 `GENERATED_FIELD_NOT_ACCEPTED` 只在直接调用 Python 函数时出现；验收用例不要期待 MCP 返回该错误码。
4. H1、H2 证据里的建议仍有效，尤其是：cap 日以 `as_of >= cap_date` 为到达条件（评分时 as_of 取 cap_date 之后，否则只给 `open` 估值——脚本已在每个计划里写明“已到期/未到期”）；回放复核必须传 `replay_as_of` 且不能与计划同日（脚本的回放 prompt 已写“所有工具带 as_of”，Skill 需要同样要求 `replay_as_of`）。
5. Skill（主会话写）里应提示：回放时 `save_trade_plan`、`save_plan_review`、`revise_trade_plan`、`save_plan_candidate` 的 `replay_as_of` 可省略（取会话变量），实时复核不得传。

## 返工 1（R-B：结算脚本与调试脚本，依据 astra 复核 #1 #3 #5 #6 #12）

改动：
1. **拆股（#1，`scripts/score-plans.py`）**：`get_price_history` 调用带 `as_of=min(评分日, 今天)`（工具还原评分日之后的拆股并只返回不晚于评分日的 `splits`）；脚本再按每个 `[ex_date, "N:M"]` 把更早行的 open/high/low/close/adj_close 乘 N/M、volume 除以 N/M，还原到当时每股口径（否则评分日前、持仓结束后的拆股会让 Yahoo 的历史开盘变成 50 而被判 `unfilled`）；`splits` 传给 `plan_math.settle`，窗口内拆股 → `not_settleable`，报告写警告。比例无法解析的拆股进警告，不静默。
2. **按截止点截断（#3）**：新增 `cut_rows(rows, as_of)`（自己实现，不依赖账本模块）：纽约 as_of 23:59:59 之前生效才保留——candidate 用 `created_at_effective`（回退 `created_at`）、plan 用 `frozen_at`、revision 用 `effective_at`、review 用 `reviewed_at_effective`、choice 用 `effective_at`（旧记录回退 `recorded_at`）；无可判定时间的行排除并计数。漏斗与逐计划部分只含截止前记录；报告头写“已排除 N 条在实际截止之后才生效的记录”。`settle` 另有内部截断（见 h1）。
3. **未完成交易日（#5）**：实际截止 = min(as_of, 最后一个已完成交易日)（今天美东 16:00 前取昨天）；取价返回 `last_row_incomplete_session` 时丢弃最后一行，并把该股（及 SPY 日历）的评分截止缩到前一天；报告头写“实际截止”与“尚未收盘，当日行情未用”，警告写被丢弃的日期。注意：带 as_of 时工具自己的 `last_row_incomplete_session` 恒为 False，所以脚本另按时钟判断。`score()` 新增 `now` 参数供测试注入。
4. **到期未成交（#6）**：漏斗新增 `expired_unfilled` 一行；报告头注明规则；逐计划沿用“计划未成交，无 cap 交易日”。
5. **提前收市（#7）**：计划线含 `revision_same_day_check` 时在“警告”段提示人工核对提前收市日。
6. **模式冲突（#12，`scripts/dev-research.sh`）**：`--decision`、`--plan`、`--review`、`--group`、`--moment` 任两个以上同时给 → 打印 usage 并以 2 退出（在建运行目录前）；usage 范围扩到第 24 行并加一行说明。其余逻辑未动。

测试（`tests/test_plan_integration.py`）：
- 命令：`.venv/bin/python -m unittest tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration -v` → `Ran 134 tests ... OK`（math 47 + integration 21 + 其余账本/决策测试，其中账本测试为另一位实现者当时的版本）；`bash -n scripts/dev-research.sh` OK；`tests.test_decision_scoring` OK。
- `get_price_history` 的 mock 现在忠实模拟 Yahoo：拆股使更早行变为拆后口径，带 as_of 时撤销之后的拆股且不返回；记录每次调用的 `as_of` 与 `end`；可标记 `last_row_incomplete_session`。
- 新增用例（手算在注释里，计划 P：成交 100、cap 日收盘 103，净 +279.70、R +0.280）：无拆股基线；窗口内拆股 → 持有对照 not_settleable + 警告 + 漏斗；持仓结束后、评分日前拆股 → 还原后与基线一致；评分日后拆股 → 与基线一致且调用都带 as_of；3 月 3 日评分时报告与漏斗不含 3 月 4 日修订、3 月 6 日 EXIT、3 月 12 日新计划、3 月 9 日机会（“已排除：5 条”），4 月 10 日评分则全部出现；`cut_rows` 按种类与 choice 回退；美东 11:00 评分时不用当日行情（持有对照 open +490.00，R +0.490；16:00 后 cap 日收盘 89 → closed −1,118.90，R −1.119）；工具标记不完整行时丢弃并写警告；周五冻结、horizon 1 → `expired_unfilled`；`dev-research.sh` 五种模式两两组合共 10 对全部退出 2。
- 因另一位实现者的账本改动（回放计划在实时会话读取 → `PLAN_REPLAY_MISMATCH`），原 `test_save_review_exit_reopen_chain` 改为在回放会话环境变量（2026-03-12）下读取，并加一条实时读取被拒的断言。

未完成项与限制：
- 未实跑 `dev-research.sh` 的任何任务模式（禁止调用模型）；互斥只验证到 usage 退出码。
- 拆股还原与不完整行情只用 mock 验证，未对真实 Yahoo 实测；对真实数据首跑时应核对一只近期拆股的股票。
- 评分日是周末/休市日时，“已完成交易日”仍按日期判断，行情自然只到最近交易日；as_of 为将来日期时只用到最后一个已完成交易日。
- choice 记录的 `effective_at` 由另一位实现者添加；在此之前旧记录按 `recorded_at` 截断。

## 返工 2（依据 astra 复查：拆股重复还原、历史写入泄露、日期格式、到期判断、同时刻选择、回放提示）

逐条改动：
1. **拆股重复还原（#1，高）**
   - 先读清结构：缓存记录的 `retrieved_at` 是“该字节内容第一次被获取的时间”，同内容再次核验只更新 `checked_at`，行情响应本身不会因 `checked_at` 改变；因此只有 `retrieved_at` 能说明响应里已含哪些拆股调整。窗口已结束的行情会无限期复用缓存（`get_price_history` 原有逻辑，未动）。
   - `product/mcp/data_tools.py`：`_later_split_factor(ticker, after_day, through_day=None)` 新增可选参数，只乘 `after_day < 拆股日 <= through_day` 的拆股；`get_price_history` 带 `as_of` 时传 `through_day = retrieved_at 的纽约日期`（缓存命中用记录里的首次获取时间，新下载用当前时间）。获取当天发生的拆股按“已调整”处理（计划原文“之前或当天”）。`through_day=None` 保持旧行为。
   - 常见情形（响应获取时间晚于全部拆股）过滤不排除任何拆股，结果与改前一致；新下载路径的 `retrieved_at` 就是现在，同样不受影响。没有改缓存模块、拆股事件缓存键或其他调用方。
   - `scripts/score-plans.py` + `product/deterministic/plan_math.py`：拆股比例无法解析时，改前只警告并继续用未还原价格。现在 `settle(..., unparsed_splits=[拆股日期])` 新参数：任一无法解析的拆股日期晚于冻结日，则三线均记 `not_settleable`、flag `split_ratio_unparsed`（早于或等于冻结日的不影响所用行情，不拦；与窗口内拆股同时出现则两个 flag 都有，顺序 `split_in_window`、`split_ratio_unparsed`）。脚本传入 `[d for d, ratio in splits if split_factor(ratio) is None]`，警告段写明原因，漏斗计入 `not_settleable`。
2. **历史写入泄露未来（#2）**：`plan_ledger._effective_for` 在回放写入（修订、复核、选择都经过它）时，若该计划已有任何生效时间晚于本次有效时间的修订、复核或选择，一律返回 `HISTORY_WRITE_CONFLICT: this plan has records after the replay cutoff`，整句固定，不含记录种类或动作；该检查先于 `PLAN_NOT_ACTIVE`、`REF_ID_NOT_FOUND`、`ABANDON_AFTER_EXIT`。`record_plan_choice` 里 `ABANDON_AFTER_EXIT` / `ALREADY_ABANDONED` 另外只统计有效时间不晚于本次的记录。注意：计划本身晚于截点才冻结的情形仍按原样返回 `EFFECTIVE_NOT_AFTER_FROZEN`（不属于“已有记录”，且改它会无谓改动既有错误码）。
3. **日期格式（#4）**：`_evidence_bounds` 只接受 `YYYY-MM-DD`（区间）或带时区（`Z` 或 `±hh:mm`）的完整 ISO 日期时间；`20260303`、无时区日期时间、`2026-03-03T10:00`、`20260303T100000Z` 等返回 `EVIDENCE_PUBLISHED_AT_INVALID: PUBLISHED_AT_INVALID: ...`（错误码保留旧前缀，因此既有断言与以 `PUBLISHED_AT_INVALID` 匹配的断言都成立）。既有用例里的无时区日期时间已改为带时区。
4. **到期判断（#6，`plan_math.settle`）**：没有冻结后的可成交开盘（日历里还没有下一个交易日）时，若 `as_of >= cap_date` 且日历非空并已覆盖冻结日，直接 `expired_unfilled`，不再等待下一个交易日出现；日历缺失或未覆盖冻结日仍保持 `pending`（交易日历缺失的单独处理）；`as_of < cap_date` 仍为 `pending`。
5. **同时刻选择（新问题）**：`_effective_for(..., same_time_ok=True)` 只给 `record_plan_choice` 用：允许选择有效时间等于计划冻结时间（回放当天对新计划记 `followed`）；引用复核仍须该复核的有效时间不晚于选择；修订与复核仍要求严格晚于冻结。引用截止点之后的记录：因为计划已有晚于本次的记录，统一落入第 2 条的 `HISTORY_WRITE_CONFLICT`。
6. **回放提示（#12，`scripts/dev-research.sh`）**：`--plan`、`--review` 的回放提示中“所有工具带 as_of=…”改为“带 as_of 参数的数据工具都传 as_of=…；计划工具由会话回放设置自动限定。”；`--decision` 与其他模式不变。

新增与调整的测试（均在临时目录、行情 mock，无网络、不调模型）：
- `tests/test_stock_data_tools.py`（`SplitRestoreTests`，4 项，只新增）：拆股前缓存的开盘 100、截止后 2:1 拆股（获取后才发生）→ 带 `as_of` 返回 100，新下载与缓存命中两路径都测；拆股发生在获取之前 → 200、成交量 50；获取当天拆股按已调整 → 200；`through_day=None` 与有值时的因子对比（回归：旧行为不变）。
- `tests/test_plan_math.py`（+2）：周五冻结、周六到期、日历只到周五，`as_of` 周六/周日 → `expired_unfilled`；到期前一日、日历缺失、日历未到冻结日仍 `pending`。`unparsed_splits`：冻结日之后 → 三线 `not_settleable` + `split_ratio_unparsed`；冻结日及之前不影响（`unparsed_splits=["2026-02-20"]` 与不传结果完全相同）；与窗口内拆股并存时两个 flag。
- `tests/test_plan_ledger.py`（新增 `ReworkTwoTests` 5 项，另调整 3 处既有断言）：历史写入（修订、复核、三种选择）报同一句固定信息且不含 EXIT/ABANDON 等字样、不写账本；未来 abandoned 选择会挡住更早的写入；尾部写入与 `ABANDON_AFTER_EXIT` 正常；`published_at` 八种坏格式全拒、`Z` 带时区放行；选择可与冻结时间、复核有效时间同刻，复核在冻结同刻仍拒。调整：无时区日期时间改带时区；“引用未生效复核”原期望 `REF_ID_NOT_FOUND`，现为 `HISTORY_WRITE_CONFLICT`，并补一条未知 ref 仍 `REF_ID_NOT_FOUND`；`EFFECTIVE_NOT_AFTER_FROZEN` 的选择用例挪到该计划第一条选择之前。
- `tests/test_plan_integration.py`（+3）：拆股比例 `N/A` 且在冻结日之后 → 三线 `not_settleable`、含 `split_ratio_unparsed`、漏斗计入；比例 `N/A` 但早于冻结日 → 正常结算并保留“拆股比例无法解析”警告；两条回放提示文字断言（plan/review 改了，decision-card 不变）。fake 行情现在对无法解析的比例不报错。
- 命令：`.venv/bin/python -m unittest tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration tests.test_decision_ledger tests.test_decision_scoring tests.test_decision_events tests.test_stock_data_tools -v` → `Ran 319 tests ... OK`；`bash -n scripts/dev-research.sh` → OK。（该命令里某个既有测试会往 `.local/runs/tmp*/report.md` 写文件，为既有行为，未处理。）

未完成项与限制：
- 拆股重复还原只用 mock 与内存缓存验证，未对真实 Yahoo 与真实 `.local/cache` 实测；首次对真实数据评分时仍应核对一只近期拆股的股票。获取当天发生的拆股按“已调整”处理是约定，Yahoo 在拆股日当天可能尚未调整，边界日有一天的偏差风险。
- `HISTORY_WRITE_CONFLICT` 对“计划自身晚于截点冻结”的情形不适用（沿用 `EFFECTIVE_NOT_AFTER_FROZEN`，会让调用者知道该 plan_id 存在）；若要彻底不透露，需在 `_effective_for` 里把该情形也并入，会改既有错误码与 5 条用例，留给主会话决定。
- Skill 文字（`plan-review/SKILL.md:23` 的“同日会被拒收”应限定盘中；`published_at` 只接受 `YYYY-MM-DD` 或带时区的完整时间；冻结时把经营持有依据与价格条件分开保存，复查 #10）不在本轮可写范围内，未改。
- 未实跑 `dev-research.sh` 的任何任务模式。
