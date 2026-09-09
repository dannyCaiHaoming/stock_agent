## 结论：FAIL

当前 Change **不能通过独立 Release Gate，也不能进入人工批准**。

需要区分两件事：

- 最新 Promotion Gate 返回带 reasons 的 `FAIL`，**本身不阻断 Change 的实现验收**。Task 11.8 和 Design 明确允许候选真实得到 FAIL；本次 Gate 正确识别了旧 Execution Replay/Ablation 与当前候选锁不一致及 baseline assurance 缺失。
- 但只读核验发现了独立于该预期 FAIL 的契约缺口：Promotion 第六类负向案例不是“断言失败”、`valid-action-contract` 没有经过 Risk、future-leakage 的真实 Runtime 没有被注入泄漏、最终验收报告缺失。因此总体仍为 FAIL。

## PASS/FAIL 矩阵

| 检查项 | 结果 | 底层结论 |
|---|---:|---|
| OpenSpec strict validate | PASS | `Change 'runtime-replay-and-eval-hardening' is valid` |
| 最新 6 个真实 Run / Trace | PASS | 全部 Trace 重算通过，模型均为 `gpt-5.6-terra`，版本均声明 `0.3.0-candidate.1` |
| 最新 6 个 Runtime Eval | PASS | 全部 Eval、Trace、grader execution proof 重验通过 |
| Regression 12 案例唯一 `run_id` | PASS | 12 个 ID，无重复 |
| Runner 亲自执行 Trace→Artifact Replay→Runtime Eval | PASS | 12 份 proof 均记录该序列；`verify_regression_suite` 重算通过 |
| Execution Replay Capsule/工作区密封 | PASS | workspace 92 文件、26 目录；可写文件/目录 0，符号链接 0；文件 `0444`、目录 `0555` |
| `configuration_equivalent` 重算 | PASS | Agent/Skill/Prompt/Schema/Model/Evidence/Risk/MCP/Profile 九类源/重放 hash 相等，持久结果重验通过 |
| Calibration 独立 dev_eval session | PASS | repeat 1/2 的 child session 分别为 `01a07c36…`、`01a07c3a…`；父会话也不同；rollout、Prompt/Input/Output、Agent/Skill hash 均匹配 |
| 独立可写 TMPDIR 全量测试证据 | PASS | 272 tests，exit 0，assertion/test/environment errors 均为 0；TMPDIR `/private/tmp/stock-agent-full-final-20260908` 可写且独立 |
| Promotion 底层重验能力 | PASS | 源码直接调用 Test、Calibration、Regression、Execution Replay、Runtime Eval、Ablation、Trace verifier，不采信摘要 PASS |
| 六类指定负向注入 | **FAIL** | 前五类是真实底层篡改；第六类运行不存在的测试类，产生 `test_errors=1`，不是规格要求的 `assertion_failures>0` |
| Regression future-leakage 实际注入 | **FAIL** | Runtime Gate 正常排除未来 Evidence，实际 Eval `leak_count=0`；`PIT_LEAKAGE` 仅来自独立预检查字段，Trace 中没有 PIT 篡改注入 |
| `valid-action-contract` 经过 Risk | **FAIL** | 只调用 action Schema 校验；对应真实 Run 最终为无关的 `SPECIALIST_VALIDATION` 失败，`risk_lineage=[]`，未验证合法草案经过 Risk Engine |
| 当前候选版本闭包 | **FAIL** | 当前锁 `ecc5578…`，旧 replay/ablation 还包含 `ae13c85…`、`5d0e5f…` |
| baseline assurance | **FAIL** | baseline manifest 缺少 `assurance`；baseline Runtime Eval 为 0、baseline Ablation 缼失 |
| Task 11.9 验收报告 | **FAIL** | 最终目录没有覆盖全部命令、ID、hash、模型、token、延迟、缓存和已知限制的统一验收报告 |
| Task 11.10 | PASS（状态真实性） | 仍为 `[ ]`，未发现人工批准；必须保持未完成 |

## Promotion FAIL 的判断

[Promotion result.json](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/promotion/candidate-final/result.json) 自哈希和 Schema 均有效，`FAIL` sentinel 为零字节且无 `PASS` sentinel。除 `version_completeness` 外，其余自动硬门禁均为 PASS。

其 FAIL 原因属实：

- 当前真实 Run/Regression 锁：`ecc5578a…`
- 旧 Execution Replay 锁：`ae13c85f…`
- 旧 Ablation 锁：`ae13c85f…`、`5d0e5faa…`
- baseline：旧 `2.0.0` manifest，无 assurance、无 baseline Eval、无 baseline Ablation

因此：

- **不应把这个 FAIL 单独当作实现失败**，否则会违背 11.8。
- **必须把它当作晋升阻断**；不能自行放宽 `version_completeness`。

`NO_MEASURABLE_GAIN` 不是阻断项，因为本 Change 没有新增或默认启用 Agent。成本/延迟 `MISSING_TELEMETRY` 目前也是软指标，不应擅自提升为失败理由。

## tasks 勾选真实性

不能认可下列已勾选项：

- **6.4：不真实。** Future leakage 没有注入实际 Runtime；合法 action 没有进入 Risk。
- **6.5：部分真实。** Runner 确实重验每例 Trace/Replay/Eval，但部分 deterministic outcome 与所绑定 Runtime 终态不是同一个行为链。
- **8.8：部分真实。** 五类注入符合要求；测试负例是 unittest 加载错误，不是规格要求的断言失败。
- **11.1：最终状态不真实。** 验收期间候选锁继续变化，没有保持单一版本闭包。
- **11.4、11.7：执行事实存在，但不能作为当前最终候选证据。** Replay/Ablation 属于旧锁。
- **11.9：不真实。** 未找到声明的统一审计验收报告。
- **11.10：正确保持未完成。**

其余重点项 4.6、5.8、6.8、10.5、11.8 有底层证据支持。

## 主要产物

- [OpenSpec tasks.md](/Users/caihaoming/Documents/stock_agent/openspec/changes/runtime-replay-and-eval-hardening/tasks.md)
- [最终 Regression result](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/regression/suite-final/result.json)
- [Regression 单例 execution proof](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/regression/suite-final/cases/normal-research/execution-proof.json)
- [旧 Execution Replay result](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/replay/execution-replay-risk-veto/result.json)
- [Calibration result](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/calibration/result/result.json)
- [全量测试 evidence](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/test-evidence/full-suite/result.json)
- [valid-action 实际 outcome](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/regression/suite-final/cases/valid-action-contract/outcome.json)
- [Promotion input](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/promotion/input-final.json)

## 实际检查命令

执行了以下只读检查，未运行任何会生成临时文件的测试：

```text
openspec validate runtime-replay-and-eval-hardening --strict
rg --files openspec/changes/runtime-replay-and-eval-hardening
sed -n ... proposal.md design.md tasks.md specs/**/spec.md
jq ... promotion/candidate-final/{result,input-manifest}.json
jq ... regression/suite-final/result.json
find <execution-workspace> -type f/-type d -perm +0222
stat -f '%Sp %N' <execution-workspace paths>
shasum -a 256 <promotion input artifacts and calibration rollouts>
PYTHONDONTWRITEBYTECODE=1 python3 -B -c '...verify_regression_suite(...)'
PYTHONDONTWRITEBYTECODE=1 python3 -B -c '...verify_execution_replay_result(...)'
PYTHONDONTWRITEBYTECODE=1 python3 -B -c '...verify_runtime_eval_job(...); trace_integrity_report(...)'
PYTHONDONTWRITEBYTECODE=1 python3 -B -c '...verify_calibration_execution_proof(...)'
PYTHONDONTWRITEBYTECODE=1 python3 -B -c '...verify_deterministic_test_evidence(...)'
rg -n '^    def test_' tests
```

最终裁定：**不能进入人工批准；Task 11.10 必须继续未完成。**