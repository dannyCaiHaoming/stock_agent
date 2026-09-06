# Codex-native Fixture Council 运行时就绪审计

## 审计结论

`activate-codex-native-fixture-council` 的 fixture-only、只读、仅供建议运行时达到验收要求。正常研究、未来或过期证据、来源冲突和 Risk veto 四类场景均生成可验证产物；不存在真实下单能力。

本结论只适用于 `0.2.0-candidate.1` 的合成 fixture 运行时，不代表真实市场数据链路、预测能力、Alpha 或投资收益已经得到验证。

## PASS/FAIL 矩阵

| 检查项 | 结果 | 实际证据 |
| --- | --- | --- |
| 固定纵向链路 | PASS | 正常、冲突和 Risk 场景均完成 Evidence Gate → Company Analyst → Independent Skeptic → CIO → Risk Engine → Decision Trace → Report；未来/过期场景按设计在 Gate 后安全终止。 |
| Agent 是否真实调用 LLM | PASS | Codex execution proof 保存父会话、两个不同子会话、`gpt-5.6-terra`、`codex-cli/0.153.4`、Agent role 和输出哈希；不是 Python callback。 |
| Skill 是否参与推理协议 | PASS | Invocation Manifest、已加载 Agent 指令、Skill 版本/hash、Skill 专属结构化输出和关联 MCP 事件形成闭环。该证明不声称可观察模型隐藏思维链或注意力。 |
| 并行与 Skeptic 独立性 | PASS | 两次专业 Agent 派发均早于第一次等待；子会话不同且 `fork_turns=none`，Skeptic 第一轮输入不含 Analyst/CIO 输出。 |
| 只读 MCP 与工具边界 | PASS | Company Analyst 调用 `fixture_evidence.query`、`fixture_math.calculate`；Skeptic 调用 `fixture_evidence.query`；无 Web、外部 Provider、券商、账户或订单工具。 |
| Risk Engine 确定性否决 | PASS | `smoke-01534-risk-01` 对 `POSITION_LIMIT`、`LIQUIDITY_LIMIT`、`SECTOR_LIMIT` 返回 `REJECTED`，最终强制 `NO_TRADE / RISK_VETO`；boundary fixture 重复运行结果一致。 |
| Evidence 时间与来源字段 | PASS | 所有允许事实均包含 `evidence_id`、`source_id`、`as_of`、`retrieved_at`；未来/过期场景精确记录 `FUTURE_AS_OF`、`FUTURE_RETRIEVAL` 和 `STALE`。 |
| 引用闭包 | PASS | Agent、CIO 和最终决策只引用本次 Gate 允许 Evidence ID；未知、被过滤、跨 run 或悬空引用的负向测试失败关闭。 |
| Trace 血缘 | PASS | Trace 关联 Agent/Skill 版本与 hash、task prompt hash、instruction bundle hash、模型、Codex runtime、Invocation、输入输出 hash、数据快照、Schema、MCP adapter、Risk policy 和 Risk 结果。 |
| Placeholder、mock-only、硬编码投资结论 | PASS | 5 项架构门禁通过；产品 Python 不导入模型 SDK、不模拟多角色、不包含固定 thesis/action/confidence。Fake adapter 仅存在于测试路径，不能通过生产真实性门禁。 |
| 同一次运行 Artifact replay | PASS | 四个版本化运行包均重新执行 Replay 并通过报告渲染、Risk、专业报告和 Trace 哈希检查。 |
| Eval 是否真实执行 | PASS | 四个运行包均保存由实际产物驱动的 `eval/result.json`；删除实际产物、伪造 Agent/Skill/MCP 证据或缺少冲突消费时测试会失败。 |
| `NO_TRADE` 语义 | PASS | 正常场景因关键证据不足、冲突场景因未解决来源冲突、Risk 场景因硬风控否决而分别形成结构化 `NO_TRADE`，未用系统错误冒充投资判断。 |
| 禁止真实交易 | PASS | 所有终态均为 `advisory_only=true`，无下单、订单路由、账户写入或凭据能力。 |

## 四场景结果

| 场景 | `run_id` | CLI 退出/终态 | Risk | Eval | Replay |
| --- | --- | --- | --- | --- | --- |
| 正常研究 | `smoke-01534-normal-04` | rollout `task_complete` 无错误；`SAFE_NO_TRADE` | `APPROVED` | PASS：9 项 | PASS |
| 未来或过期 | `smoke-01534-stale-01` | 预 Agent 确定性 `SAFE_NO_TRADE` | 不适用 | PASS：6 项 | PASS |
| Evidence 冲突 | `smoke-01534-conflict-01` | CLI `0`；`SAFE_NO_TRADE` | `APPROVED` | PASS：9 项 | PASS |
| Risk veto | `smoke-01534-risk-01` | CLI `0`；`SAFE_NO_TRADE` | `REJECTED / RISK_VETO` | PASS：10 项 | PASS |

## 实际命令

正常、冲突和 Risk 场景均使用以下 Codex-native 入口，替换对应 `run_dir`：

```bash
python3 -m product.runtime.cli smoke-prompt \
  --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir <run_dir> > /private/tmp/council-prompt.txt

codex exec -C product --add-dir <run_dir> --strict-config --json \
  -m gpt-5.6-terra - < /private/tmp/council-prompt.txt
```

确定性门禁命令：

```bash
python3 -m unittest discover -s tests -v
openspec validate activate-codex-native-fixture-council --strict
git diff --check
python3 -m product.runtime.cli replay --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir <versioned_acceptance_run> --output <new_replay_output>
```

## 输入与输出位置

- 版本化 fixture：`evals/fixtures/codex-native/`
- 版本化真实验收包：`evals/runs/activate-codex-native-fixture-council/`
- 每个完整 Council 包含：`run_manifest.json`、`evidence/gate.json`、`inputs/`、`invocations/`、`agents/`、`cio/`、`risk/`、`events/codex/`、`events/mcp/`、`decision.json`、`report.md`、`decision_trace.json`、`eval/result.json` 和 `replay.json`。
- 不保存完整原始 Codex rollout，只保存经过最小化的执行证明。

## 仍需人工确认的边界

- 个别 LLM 自然语言字段使用英文；不影响 Schema、证据闭包或风控，但后续 Change 应将面向用户的报告语言明确锁定为中文优先。
- 当前只使用合成 fixture MCP；真实行情、SEC/FRED、期权、多市场、动态路由、Reflection Agent 和自动交易均不在本 Change 范围内。
- 自我优化仍只能生成 Improvement Proposal，不能修改生产资源或版本指针。
