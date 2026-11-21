# T2 证据：decision/v2 记录与保存工具

执行者：Sonnet 子 session。日期：2026-11-22。未 commit、未 push、未调用模型。

## 改了哪些文件
| 文件 | 内容 |
|---|---|
| `product/mcp/decision_ledger.py`（新） | `save_trade_decision` 与全部校验；`CAUSES`、`DecisionLogError`、`_code_version` 从 `decision_log` 导入，`decision_log.py` 未改 |
| `product/mcp/server.py` | 只加了 `decision_ledger` 的 import 与 `save_trade_decision` 注册（文件末尾 `main()` 之前），docstring 写明工具生成字段 |
| `scripts/decision-record.py`（新） | 追加到 `evals/forward/decision-ledger.jsonl` |
| `tests/test_decision_ledger.py`（新） | 26 个测试 |

## 完整签名
```python
# product/mcp/decision_ledger.py
def save_trade_decision(ticker: str, source: str, position_state: str, group: str, event: dict,
                        benchmark: str, action: str, cash_destination: str, p_outperform: dict,
                        review_triggers: list[str], thesis: str, report_markdown: str,
                        attribution: dict | None = None, hold_type: str | None = None,
                        prior_decision_id: str | None = None, replay_as_of: str | None = None,
                        host: str | None = None, model: str | None = None, **extra) -> dict
```
MCP 注册版本相同但没有 `**extra`。返回：`saved, decision_id, decided_at, decided_at_effective, replay, w0, w1, horizon_days, report_sha256, report_path, decision_log`。

工具生成、传入即拒收（`GENERATED_FIELD_NOT_ACCEPTED`）：`schema, decision_id, decided_at, decided_at_effective, info_cutoff, w0, w1, horizon_days, fill_rule, code_version, report_sha256, report_path, replay`。其他多余参数 → `UNKNOWN_FIELDS`。

记录里除子设计列出的字段外，新增 `decided_at_effective`（始终写：非回放时等于 `decided_at`）与 `replay`（bool）。**T4 取成交基准时间应读 `decided_at_effective`**；`info_cutoff` 在回放时等于 `decided_at_effective`（不是真实运行时间）。

## 对 T2 判据的覆盖（`tests/test_decision_ledger.py`）
| 判据 | 测试 |
|---|---|
| 工具生成字段传入即拒收 | `test_generated_fields_are_refused`（10 个字段）、`test_unknown_field_refused` |
| w0/w1/horizon 按协议 §4 与 group | `test_w_and_horizon_from_action_and_group`（6 个动作含 not_held WAIT/BUY；E0/E1/E2 → 60/20/60） |
| held/not_held × 动作；scan 只能 held | `test_action_must_match_position_state`、`test_scan_must_be_held` |
| HOLD/WAIT 必有 `hold_type`，其他必须为空 | `test_hold_type_rules` |
| `review_triggers` ≥ 2 条且至少一条含数字 | `test_review_triggers` |
| E1/E2 归因必填且用 `CAUSES` | `test_attribution_required_and_valid_for_e1_e2`（遍历全部 10 个 CAUSES）、`test_e0_attribution_optional_but_checked_if_given` |
| `replay_as_of` → 16:00 NY 之后、`replay=true` | `ReplayTests`：冬令 21:00:01Z、夏令 20:00:01Z、事件日晚于回放日拒收、`STOCK_AGENT_REPLAY_AS_OF` 环境变量自动采用并要求一致、非法日期 |
| `prior_decision_id` 须存在 | `test_prior_decision_must_exist_in_same_file` |
| 报告章节（主会话补充契约） | `test_report_sections`：7 个二级标题逐个缺失拒收（`REPORT_SECTIONS_MISSING`，列出缺的标题）、顺序不限、E0 的消息归因可写“不适用” |
| `decision-record.py` 只追加、不重复 | `RecordScriptTests`：重复 id 拒收且账本字节不变；追加第二条时前缀不变；未知 id、报告被改动（sha 不符）拒收且不建账本 |
| 全在临时目录 | `setUp` 设 `STOCK_AGENT_DATA_DIR`；脚本测试用 `--ledger` 临时路径；跑完后 `.local/data` 无 `trade_decisions.jsonl`、`evals/forward` 无改动 |

## 实际命令与输出
```
$ .venv/bin/python -m unittest tests.test_decision_ledger
Ran 26 tests ... OK
$ .venv/bin/python -m unittest tests.test_decision_ledger tests.test_stock_data_tools
Ran 52 tests ... OK
```
另用一个临时数据目录经 `server.server.call_tool("save_trade_decision", …)` 走了一遍 MCP 路径：工具列表含 `save_trade_decision`（共 37 个工具），保存成功。

## 子设计没写、我自行定的细节（请主会话确认或改）
1. **报告章节**（按主会话后补的契约，替换了我原先的 H1／行首检查）：`decision_ledger.py` 顶部 `REQUIRED_SECTIONS = ("结论", "概率与收益", "消息归因", "上次决策", "复核条件", "数据缺口", "来源")`，报告须含对应 `## ` 标题（前缀匹配、忽略空白、顺序不限），缺任何一个拒收并列出缺的标题。不再检查 H1 与 ticker。
2. **E2 的 `event.deviation_z` 必填**（子设计里是可选）：B1 需要偏离方向，T3 对 E2 总会返回它。
3. `benchmark` 允许 `no_sector`（非 E2；E2 + `no_sector` 拒收；`no_sector` 与 `cash_destination = sector_etf` 同用也拒收）。
4. `event.event_date` 不得晚于决策生效日（NY 日期）。
5. 回放生效时间取 16:00:**01** NY（严格晚于收盘，避免 T4 比较时 `<`/`<=` 歧义）。
6. 回放日期来源：参数 `replay_as_of`，未给时取 `STOCK_AGENT_REPLAY_AS_OF`；两者都有且不同则拒收。这样回放会话里模型忘传参数也不会误当成实时记录。
7. `thesis` 必须单行；`p_outperform`、`event`、`attribution` 里出现未知键拒收；`company_cause` 只接受 JSON 布尔或 `"unconfirmed"`。
8. `decision-record.py` 追加的行 = 完整记录 + `kind: "decision"` + `recorded_at`；追加前校验 schema、报告文件存在且 sha256 与记录一致；用 `flock` 防并发重复。**不复制报告到仓库**（`forward-record.py` 会冻结一份副本；本脚本按子设计只记 sha，报告留在 `<data dir>/trade-reports/`）。

## 未完成项与限制
- **MCP 层的“拒收”**：MCP SDK 在参数校验阶段会静默丢弃签名外的参数（实测传 `decision_id="abc"` 被忽略，记录里的 id 是工具生成的），因此经 MCP 调用时这些字段永远进不了记录，但模型看不到“被拒”的报错；Python 层直接调用才会抛 `GENERATED_FIELD_NOT_ACCEPTED`。若要让 MCP 层也报错，需改 SDK 行为或自建参数校验，我没做。
- 未与 T3 的 `classify_decision_event` 联动核对 group / horizon（plan 里属主会话整合步骤）。
- 未对真实 `.local/data` 写任何数据；真实 `decision-record.py` 默认账本路径未被执行。

## 回写建议
- 子设计 T2 表补记：`decided_at_effective` / `replay` 始终写入；E2 的 `deviation_z` 必填；`benchmark` 可为 `no_sector`；报告章节 REQUIRED_SECTIONS。
- T4 的 `fill()` 应读 `decided_at_effective`；T5 的卡片模板包含上述 7 个二级标题。
- 若希望冻结报告副本进仓库，另给 `decision-record.py` 加一步（需要决定是否提交报告）。
