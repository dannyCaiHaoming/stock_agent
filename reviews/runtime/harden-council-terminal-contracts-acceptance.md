# `harden-council-terminal-contracts` 真实 Codex 验收记录

## 验收结论

候选版本 `0.2.1-candidate.1` 已使用 `codex-cli/0.153.4`、显式模型 `gpt-5.6-terra` 和仓库本地 `portfolio-council 2.1.0` 完成六次全新运行。六次 Codex 进程退出状态与独立 Council Release Gate 状态均为 `0`，实际 Eval 均为 `PASSED`。

本轮只验证 fixture Council 的终态契约、Evidence Closure、独立 Agent 上下文、Risk lineage、可诊断 Replay 与 Release Gate；不评价市场收益、Alpha 或预测能力。

## Specialist Evidence ID 修复后补充验收

针对 Specialist 偶发把来源或时间拼接进 `evidence_refs` 的问题，运行时已从当前 Gate 的 `allowed_evidence_ids` 确定性生成 run-scoped enum Schema，并在 Specialist 输入与 Prompt 中单独锁定允许 ID。Evidence Closure Validator 保持严格不变，未增加截断、猜测或其他静默修复。

修复后以三个全新 `run_id` 连续执行冲突 fixture：

| `run_id` | Codex 退出 | Council Gate | 终态 | Eval | Evidence 引用 |
| --- | ---: | --- | --- | --- | --- |
| `rg3-conflict-1-20260907` | 0 | 0，`PASSED / RELEASE_READY` | `SAFE_NO_TRADE` | `PASSED`，9 项 | 全部为 Gate canonical ID |
| `rg3-conflict-2-20260907` | 0 | 0，`PASSED / RELEASE_READY` | `SAFE_NO_TRADE` | `PASSED`，9 项 | 全部为 Gate canonical ID |
| `rg3-conflict-3-20260907` | 0 | 0，`PASSED / RELEASE_READY` | `SAFE_NO_TRADE` | `PASSED`，9 项 | 全部为 Gate canonical ID |

三次均生成 `decision.json`、`report.md`、`decision_trace.json` 和 `eval/result.json`，完成真实双 Agent、CIO、Risk 与 Eval；独立复核未发现悬空引用、Risk 绕过或非法 `NO_TRADE`。三次运行及运行后的产品完整性快照均为 `a82bc4f12dfca43d15a4916ceb76b30dc514b4eb41c1574859261eaf2773f831`。

## 锁定版本与完整性

- Candidate：`0.2.1-candidate.1`
- Runtime profile：`fixture-council/2.1.0`
- Codex runtime：`codex-cli/0.153.4`
- Model：`gpt-5.6-terra`
- Portfolio Council Skill：`2.1.0`
- Canonical decision contract：`council-decision-contract/1.0.0`
- Decision Trace / runtime artifacts：`2.1.0`
- Fixture MCP adapter：`fixture-gate-scoped/2.1.0`
- Risk policy：`risk/reference/1.0.0`
- 六次运行共同的产品完整性快照：`34507367662870db36320d4cac2e69a2cfe10f9809175065103d47ab05c26660`
- 验收后重新计算的产品完整性快照与运行前一致。

本机插件缓存已刷新至 `product@stock-agent-local 0.2.4+codex.20260906091442`。缓存内 `portfolio-council/SKILL.md` 的版本为 `2.1.0`，内容 hash 与仓库文件一致。

## 实际命令

每个场景先使用对应 fixture、唯一 `run_id` 和全新目录执行：

```bash
python3 -m product.runtime.cli prepare \
  --repo /Users/caihaoming/Documents/stock_agent \
  --fixture /Users/caihaoming/Documents/stock_agent/evals/fixtures/codex-native/<fixture>.json \
  --run-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id> \
  --run-id <run_id> \
  --model gpt-5.6-terra \
  --question 基于截至决策截止日的证据，对现有持仓给出仅供研究参考的组合建议；证据不足或冲突无法消解时必须NO_TRADE。
```

随后从 Codex-native Skill 入口运行：

```bash
python3 -m product.runtime.cli smoke-prompt \
  --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id> \
| codex exec \
  -C product \
  --add-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id> \
  --strict-config \
  --json \
  -m gpt-5.6-terra \
  -
```

每次 Codex 运行完成后均再次独立执行：

```bash
python3 -m product.runtime.cli check-run \
  --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir /Users/caihaoming/Documents/stock_agent/evals/runs/harden-council-terminal-contracts/<run_id>
```

## 六次真实运行矩阵

| 场景 | Fixture | `run_id` | Codex 退出 | Council Gate 退出 | 终态 | Agent / Risk | Eval |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| 正常研究 | `normal-research.json` | `harden-normal-02` | 0 | 0 | `SAFE_NO_TRADE` | 3 个 Agent lineage；Risk `APPROVED` | `PASSED`，9 项 |
| 未来/过期 | `future-or-stale.json` | `harden-stale-01` | 0 | 0 | `SAFE_NO_TRADE` | 0 个 Agent；Risk 未运行 | `PASSED`，6 项 |
| Risk veto | `risk-veto.json` | `harden-risk-01` | 0 | 0 | `SAFE_NO_TRADE` | 3 个 Agent lineage；Risk `REJECTED` | `PASSED`，10 项 |
| 证据冲突 1 | `evidence-conflict.json` | `harden-conflict-01` | 0 | 0 | `SAFE_NO_TRADE` | 3 个 Agent lineage；Risk `APPROVED` | `PASSED`，9 项 |
| 证据冲突 2 | `evidence-conflict.json` | `harden-conflict-02` | 0 | 0 | `SAFE_NO_TRADE` | 3 个 Agent lineage；Risk `APPROVED` | `PASSED`，9 项 |
| 证据冲突 3 | `evidence-conflict.json` | `harden-conflict-03` | 0 | 0 | `SAFE_NO_TRADE` | 3 个 Agent lineage；Risk `APPROVED` | `PASSED`，9 项 |

## 关键验收证据

- 正常场景真实加载 `portfolio-council 2.1.0`，Company Analyst 与 Independent Skeptic 在不同 Codex session 中独立运行，主线程担任 CIO。
- 正常场景的 `fixture_math.calculate` 首次调用即成功，使用非空 `calculation_id=calc_debt_to_revenue`；六次最终运行的 MCP error 数均为 0。
- 未来/过期场景在任何专业 Agent 获取上下文前排除了 `ev-future-asof`、`ev-future-retrieval` 与 `ev-stale-update`，Trace 中 `agents=[]`、`risk_lineage=[]`，并保存 `PRE_AGENT_SAFE_TERMINATION`。
- Risk veto 场景保存完整 Risk lineage，确定性 Risk Engine 以 `POSITION_LIMIT`、`LIQUIDITY_LIMIT`、`SECTOR_LIMIT` 返回 `REJECTED`，最终保持 `NO_TRADE: RISK_VETO`。
- 三次冲突场景均保存一项未解决机械冲突；CIO 均显式消费冲突并输出合法 `NO_TRADE`，`target_weight_range` 与 `maximum_notional` 均为 JSON `null`。
- 六次运行均生成 `decision.json`、`report.md`、`decision_trace.json`，均无悬空或跨 Gate Evidence 引用；Gate 内事实均带 `source_id`、`as_of`、`retrieved_at`。
- 六次运行均保存并通过 deterministic artifact replay、artifact matrix、Trace lineage 与实际 Eval。
- 冲突三次运行期间产品完整性快照未改变。

## 非阻断运行噪声

- Codex 对插件图标相对路径发出警告；不影响 Skill、Agent、MCP 或验收产物加载。
- 个别运行出现远端插件目录刷新、遥测发送或 WebSocket 预热警告；实际模型调用、子 Agent、MCP、Eval 与 Release Gate 均完成并通过。

## 不计入最终矩阵的诊断运行

在最终六次验收前曾执行并删除两个正常场景诊断目录：一次发现本机插件缓存仍为 Skill 2.0.0，另一次发现计算工具说明不足导致 LLM 参数重试。随后按本地插件更新流程刷新缓存，并将计算工具的完整参数、operation 枚举及禁止参数写入 MCP 描述、Company Analyst 指令和 Smoke 提示。最终矩阵中的运行全部发生在修复、全量测试和重新生成运行包之后。
