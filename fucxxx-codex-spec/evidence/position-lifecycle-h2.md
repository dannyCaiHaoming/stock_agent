# H2 计划记录：实现证据

任务：`fucxxx-codex-spec/plans/position-lifecycle-impl.md` §2 H2。执行者：Sonnet 5.5 子 Agent。日期：2026-11-28。

## 修改的文件
- `product/mcp/plan_ledger.py`（新）
- `tests/test_plan_ledger.py`（新）
- `fucxxx-codex-spec/evidence/position-lifecycle-h2.md`（本文件，新）

未改其他文件；未 commit、未 push、未调用模型。只 import 了 `decision_ledger`（`_text`、`_iso_date`、`_decision_times`、`_opt_text`、`_only_keys`、`NY`、`DAY_END`）、`decision_log`（`DecisionLogError`、`_code_version`）、`provenance.iso_utc`；`plan_math` 在 `size_trade_plan` 内延迟 import。

## 接口签名
```python
size_trade_plan(entry_ref, price_invalidation, risk_budget=1000) -> {"risk_per_share","shares","r0"}
save_plan_candidate(ticker, outcome, reason, replay_as_of=None, host=None, model=None) -> dict
save_trade_plan(ticker, template, thesis, market_misread, catalyst, abandon_facts, price_invalidation, entry_ref,
                entry_band, hold_basis, review_dates, horizon_cap_days, report_markdown, risk_budget=1000,
                replay_as_of=None, host=None, model=None, **extra) -> dict   # plan_id, candidate_id, frozen_at, shares_planned, r0, report_path, ...
revise_trade_plan(plan_id, reason, sources, changes, replay_as_of=None) -> dict
save_plan_review(plan_id, thesis_verdict, evidence, action, action_reason, report_markdown, plan_deviation=False,
                 deviation_reason=None, replay_as_of=None, host=None, model=None) -> dict   # review_id, reviewed_at_effective, report_path, ...
record_plan_choice(plan_id, ref_id, choice, note) -> dict
get_trade_plan(plan_id) -> {"found","plan","revisions","current","reviews","choices","active","report_markdown", + "active_reason","cap_date","plan_id"}
list_trade_plans(ticker=None, active_only=True) -> {"plans","count","active_count","active_max"}
active_plans(today_ny: date, replay: bool, as_of: datetime | None = None) -> list[dict]   # 内部；as_of 为新增可选参数
```
记录文件 `settings.data_dir()/trade_plans.jsonl`；报告 `plan-reports/<YYYY-MM-DD>/<TICKER>-<id>.md`（计划与复核各一份）。`save_trade_plan` 的 candidate(outcome=plan) 与 plan 两行用一次 `os.write` 追加。所有错误为 `DecisionLogError`，信息以大写错误码开头。

## 测试
命令：`.venv/bin/python -m unittest tests.test_plan_ledger -v`
结果：`Ran 59 tests ... OK`（约 2.7 秒）。全部测试把 `STOCK_AGENT_DATA_DIR` 指向临时目录。
`plan_math` 已存在时用真实模块；不存在时 `setUpModule` 注入同行为替身（最初几轮在 H1 完成前用替身跑过；最终一轮用 H1 的真实 `plan_math` 跑，全部通过）。

覆盖：正常保存与返回值；股数/R0 手算（100 股、1000；312 股、998.4）；生成字段与未知字段被拒；`abandon_facts` 各种缺失；`entry_band`/失效价顺序；`horizon_cap_days` 0、121 等；`template`；第 9 个进行中计划；同股进行中；EXIT 后同股重开且 `plan_id` 不同、互不串线；cap 过期（含 cap 当日仍进行中、次日结束）；放弃释放同股；修订不允许字段、R0/股数不变、`current`、版本号 2、3、上移失效价；复核改结论无新证据被拒/有新证据通过/与上一次复核比较；证据晚于有效时间被拒；回放有效时间（EST、EDT）；回放与实时互不混；`model_recorded` 两种来源；两种报告缺标题被拒；`abandoned` 在 EXIT 后被拒；候选记录；`size_trade_plan` 三种错误码转换；追加只增不改；账本损坏报 `LEDGER_CORRUPT`；拒绝时不写任何行。

## 实现时对设计空白的保守处理（需主会话确认）
1. **日期型 `published_at`** 视为该纽约日 00:00。因此“与计划同日的公告”不算新证据（计划冻结在当日 23:59:59）；次日起的才算。带时间但无时区的时间戳按纽约时间。
2. **复核至少 1 条 evidence**；`thesis_verdict` 与上一次相比改变（含改为 `insufficient`）一律要求新证据，字面执行设计。
3. **复核与修订的有效时间**须晚于计划冻结时间，并晚于上一条同类记录（`EFFECTIVE_NOT_AFTER_FROZEN`、`EFFECTIVE_NOT_AFTER_PREVIOUS`），保证结算按时间顺序读取；回放与否须与计划一致（`PLAN_REPLAY_MISMATCH`）。
4. **复核与修订都要求计划“进行中”**（`PLAN_NOT_ACTIVE`），包括 cap 已过、已 EXIT、已放弃。
5. **进行中判定**：cap 当日（决定日 + `horizon_cap_days`，纽约日期）仍算进行中，次日起结束。放弃记录不看时间，一律生效；EXIT 复核只看有效时间不晚于“当时”。
6. **回放计划的“今天”**：回放会话（`STOCK_AGENT_REPLAY_AS_OF`）内用会话日期；无会话时用该计划最近一条记录的有效日期（所以不会因真实日期推移自动过期）。
7. **`list_trade_plans`**：回放会话只列回放计划，否则只列实时计划；`active_count` 统计同类的全部进行中计划，不受 ticker 过滤影响。
8. **`plan_deviation=False` 时传 `deviation_reason` 被拒**（`DEVIATION_REASON_NOT_ALLOWED`），避免两者矛盾。
9. **`record_plan_choice`**：`ref_id` 必须是本计划的 `plan_id` 或其某个 `review_id`；`declined`/`abandoned` 要求非空 `note`（`followed` 可空）；`abandoned` 不能重复。选择记录的 `replay` 沿用计划，`recorded_at` 为真实时间。
10. **`revise_trade_plan`**：`sources` 为非空列表（文本或含非空 `source` 的字典）；`review_dates` 须晚于修订当日；`changes` 为空被拒。
11. `active_plans` 增加可选参数 `as_of`（默认当天纽约 23:59:59），保存新计划时用于“只看新计划有效时间之前的事件”；与设计要求的签名兼容。
12. 候选行与复核行额外记录 `host`、`model`、`model_recorded`、`code_version`；候选行与计划行有 `created_at_effective` / `frozen_at` 区分真实时间和有效时间。
13. 并发：同一时刻两个会话写入没有文件锁，上限与同股检查可能被竞态绕过。L1 单会话使用，不处理。

## 未完成项
- 无设计要求的功能缺口。未做：`server.py` 注册与 `explain_errors`（H3）；文件锁。

## 对设计的回写建议
- 在子设计“规则”里明确：日期型 `published_at` 的读法、`insufficient` 是否也要新证据（现为是；若要允许“资料不足”无新证据，应作为例外写明）、复核/修订须晚于上一条记录且计划进行中、`list_trade_plans` 的回放/实时分离、cap 当日仍进行中。
- 子设计未规定 `note` 与 `plan_deviation` 的语义：建议写明 `plan_deviation=true` 的含义（动作偏离冻结时写下的持有依据或失效价）。
- `get_trade_plan` 返回比设计多三个键（`plan_id`、`active_reason`、`cap_date`），建议写入设计的工具说明，供 H3 的 docstring 引用。
- H3 需注意：回放复核必须传 `replay_as_of`（或设环境变量），否则 `PLAN_REPLAY_MISMATCH`；同一回放日的复核不能与计划同日。

## 返工 1（R-A 账本，2026-11-28）

依据 `position-lifecycle-rework1.md` R-A 与 astra 复核第 2、4、8、9、10 条。写入文件：`product/mcp/plan_ledger.py`、`product/mcp/server.py`（仅 `record_plan_choice`、`save_plan_review`、`get_trade_plan`、`list_trade_plans` 的签名/docstring）、`tests/test_plan_ledger.py`、本文件。未碰 plan_math、score-plans、dev-research.sh、test_plan_math、test_plan_integration。

### 改了什么
1. **回放可见性（#2）**
   - 新增 `_session()`（实时 = 现在；回放 = `STOCK_AGENT_REPLAY_AS_OF` 当日纽约 23:59:59）与 `_check_session()`：`get_trade_plan`、`record_plan_choice`、`revise_trade_plan`、`save_plan_review` 在计划与会话模式不符时抛 `PLAN_REPLAY_MISMATCH`（未知 id 仍先报 `PLAN_NOT_FOUND` / `found:false`）。`list_trade_plans` 沿用“只列同类”。
   - `choice` 记录新增 `effective_at`（`record_plan_choice` 走 `_effective_for(bundle, None)`：实时 = 现在，回放 = 会话日 23:59:59，须晚于计划冻结），返回值也带 `effective_at`。旧记录没有该字段时回落到 `recorded_at`。
   - `_cut(bundle, cutoff)`：按截止点丢弃之后生效的 revision/review/choice，计划冻结晚于截止点则整体不存在（`get_trade_plan` 返回 `found:false`，列表不含、不计入 `active_count`）。`get_trade_plan`、`list_trade_plans`、`active_plans` 先切再推导 current、active、摘要。`_status` 里 abandoned、EXIT 只计截止点之前生效的。`record_plan_choice` 的 `ref_id` 只认截止点已生效的复核。
   - 写入时的顺序检查（上一条复核/修订、版本号、`ABANDON_AFTER_EXIT`、`ALREADY_ABANDONED`）仍看完整记录，避免版本号重复。
   - 去掉旧的 `_today()`（回放计划无会话时取“自身最近日期”）：回放读写现在必须有会话（`STOCK_AGENT_REPLAY_AS_OF`）。
2. **裸日期证据（#4）**：`_evidence_bounds` 把 YYYY-MM-DD 读成 [当日 00:00, 当日 23:59:59] 纽约。下界 > 有效时间 → `EVIDENCE_AFTER_REVIEW`；上界 > 有效时间 → `EVIDENCE_TIME_AMBIGUOUS`（要求精确时间）；日期早于复核纽约日期自然通过；回放复核可引用同一回放日（上界 = 有效时间）。“晚于上次复核”用下界。带时间的不变。
3. **改判须有非价格新证据（#10）**：结论改变时需至少一条 `kind != price` 且下界晚于上次的证据，否则 `NEW_EVIDENCE_REQUIRED`，信息写明价格变化不改变论点结论、价格在动作里处理。结论不变时价格证据照常可用。
4. **论点视图（#10）**：`get_trade_plan(plan_id, view="full"|"thesis")`，其他值 `VIEW_INVALID`。`thesis` 只含 plan 的 thesis、market_misread、catalyst、abandon_facts、hold_basis、review_dates、frozen_at，当前版本的 version/hold_basis/review_dates/abandon_facts，`cap_date`，各复核的 `review_id`、`thesis_verdict`、`reviewed_at_effective` 与非价格证据；不含报告全文、entry/price_invalidation/r0/shares/risk_budget/report_path、动作与 action_reason、active_reason（EXIT 会从中泄露）。`full` 键集只多一个 `report_integrity`。
5. **报告完整性（#9）**：`_read_report` 从 `settings.data_dir()/plan-reports/*/<TICKER>-<id>.md` 按 id 定位，不用记录里的 `report_path`；解析后不在该目录下（如符号链接指向外部）视为缺失；`report_sha256` 缺失或不符为 `mismatch` 且不返回全文。`get_trade_plan(view=full)` 返回 `report_integrity: ok|missing|mismatch`。（只读取计划报告；复核报告本轮仍不读取。）
6. **并发（#8）**：新增 `_ledger_lock()`（`fcntl.flock` 独占，锁文件 `trade_plans.jsonl.lock`，不嵌套）。`save_trade_plan`（决定时间起的全部检查与追加）、`revise_trade_plan`、`save_plan_review`、`record_plan_choice` 在锁内重读账本、检查、写报告、追加。`save_plan_candidate` 是单行原子追加，未加锁。
7. **server.py**：`get_trade_plan` 增加 `view` 参数与说明；`record_plan_choice` docstring 写明有效时间、会话匹配、`ref_id` 须已生效；`save_plan_review` docstring 改为新的裸日期与非价格证据规则（原“裸日期 = 00:00”已不成立）；`list_trade_plans` docstring 补一句截止点。其他工具与注册不变。

### 测试
- `.venv/bin/python -m unittest tests.test_plan_ledger -v`：`Ran 85 tests ... OK`（3 次连跑稳定，约 5.7 秒，全部用临时目录）。
- `.venv/bin/python -m unittest tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration -v`：`Ran 160 tests ... OK`；`bash -n scripts/dev-research.sh` 通过。（另一位实现者已把 test_plan_integration 里对回放计划的读取放进回放会话，本轮没有因我的改动失败。）
- 原 59 个用例中，读取或记录选择回放计划的用例改为通过 `LedgerCase.get/choose/refuse_choice` 在回放会话里调用（行为变化的预期结果）。新增 26 个用例：
  - `ReplayVisibilityTests`：修订/EXIT/选择在截止点之后不可见（get、list、thesis 视图）；冻结前 `found:false`；会话模式不符（get、thesis、choice，两个方向）；回放会话不能放弃实时计划且名额不释放；choice 有效时间；之后的放弃/EXIT 不改变更早日期的 active 与同股新建（`ACTIVE_PLAN_EXISTS`）；`ref_id` 不能指向未生效复核。
  - `EvidenceTimeTests`：实时复核同日裸日期 `EVIDENCE_TIME_AMBIGUOUS`、次日 `EVIDENCE_AFTER_REVIEW`、前一日与已过的精确时间通过；回放复核可引用当日；新旧证据按下界判断。
  - `PriceEvidenceTests`、`ThesisViewTests`（递归检查无价格键与价格数字）、`ReportIntegrityTests`（ok/mismatch/missing、存储路径被篡改、符号链接外指、缺哈希）。
  - `ConcurrencyTests`：两线程各自读到同一份旧账本后在屏障处汇合；有锁时 7 个已有计划只成功 1 个新计划（共 8 个，无孤立 candidate 行）、同股只成功 1 个、两个修订得到版本 2 和 3；自检用例关闭锁后同一竞赛产生第 9 个计划，证明测试有效。

### 未完成项与建议
- 无 R-A 范围内的未完成项。线程测试证明同进程互斥；跨进程互斥由 `flock` 保证，未另写多进程用例。
- 回放写入的 `choice` 不再接受“无会话 + 回放计划”；`plan-review`、`trade-plan` 两个 SKILL.md（不在 R-A 写入范围）需要同步：复核第一步先 `get_trade_plan(view="thesis")`，价格与动作阶段再读 `view="full"`；回放里读/记选择必须有 `STOCK_AGENT_REPLAY_AS_OF`；证据同日需给精确时间。`dev-research.sh` 的回放任务要确认设置了该环境变量。
- 回写设计建议：把“记录何时可被读取”（`effective_at`，选择行也有）、裸日期区间读法、改判须有非价格新证据写进子设计的规则。
- 只读取了计划报告的完整性；若复核报告也要给模型读，应复用 `_read_report(record, review_id)`。
