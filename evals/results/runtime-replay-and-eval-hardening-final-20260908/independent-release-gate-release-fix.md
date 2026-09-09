# 独立只读 Release Gate：FAIL

结论分两层：

- **Change 实现验收：FAIL。** 四个重点缺口中，断言失败负例、同 Run PIT 证据链、合法 action 实际经过 Risk、中文报告绝对路径闭包均已实质改善；但严格对照 Design/Tasks，仍有 Regression invariant 契约与验收报告完整性缺口。
- **候选版本 Promotion：FAIL。** 唯一自动晋升原因是 `version_completeness`：候选证据混用三个版本锁，且 baseline 缺少新版 assurance、Runtime Eval 和 Ablation。按 Task 11.8，这个带 reasons 的 FAIL 本身不代表 Change 实现失败，但当前候选绝对不得晋升。

全程未修改任何代码、文档、tasks 或产物；Task 11.10 保持 `[ ]`，未归档。

## PASS/FAIL 矩阵

| 验收项 | 结果 | 底层复核 |
|---|---:|---|
| OpenSpec strict validate | PASS | 实际返回 `Change 'runtime-replay-and-eval-hardening' is valid` |
| 全量确定性测试证据 | PASS | 底层 transcript/hash 重验：272 tests，exit 0，assertion/test/environment errors 均为 0 |
| Promotion 断言失败负例 | PASS | 真实 `AssertionError`：1 test、1 failure、0 error、exit 1；Promotion 的 `deterministic_tests` 硬门禁 FAIL |
| future-information 同 Run 证据链 | PASS | 同一 run_id 的 Gate 排除两项未来 Evidence，Trace 记录相同排除集合，Artifact Replay 与 Runtime Eval 重算通过，Eval leak_count=0 |
| future-information 确定性注入契约 | **FAIL** | Design 要求 PIT 篡改由 fixture producer 注入并在 Trace 留痕；实际没有 `audit/regression-injection.json`，Trace 无 fixture producer，`validator_rejection=PIT_LEAKAGE` 是 runner 根据正常排除结果直接写入 outcome，并非实际 Runtime Validator rejection |
| valid-action 实际经过 Risk | PASS | HOLD 草案进入 Risk Engine；终态 COMPLETED；risk_lineage 1 项且结果 APPROVED |
| valid-action expected invariant | **FAIL** | case 仅声明 action 集、REDUCE 禁止和零 LLM，没有 `must_pass_risk`/`risk_not_bypassed`；因此 case 契约本身不能保证未来运行仍经过 Risk |
| 12-case Regression | PASS | 12 个唯一 run_id；`verify_regression_suite` 从底层重跑每例 Trace→Artifact Replay→Runtime Eval，全部通过 |
| typed expected_invariants | **FAIL** | Regression Schema 接受任意字符串/任意 value；Design 列出的 `must_pass_risk`、`must_fail_stage`、`evidence_subset_of_gate` 未完整实现 |
| Replay Capsule 完整性 | PASS | Capsule Schema、manifest/root hash、93-object 闭包重验通过 |
| Execution Replay 工作区密封 | PASS | 92 文件、26 目录；可写路径 0、符号链接 0；文件 0444、目录 0555 |
| `configuration_equivalent` 重算 | PASS | Finalizer/Verifier 重新计算 Agent、Skill、Prompt、Schema、Model、Evidence、Risk、MCP、Profile 九类 hash，源/重放一致 |
| Runtime Eval | PASS | 当前 Promotion 引用的两个 Eval 及 Execution Replay pair 的两个 Eval 均从底层重验通过 |
| Calibration 独立 session | PASS | repeat child sessions 为 `01a07c36…`、`01a07c3a…`；父会话、rollout、Prompt/Input/Output、Agent/Skill hash 均重验通过 |
| A/B/C Ablation | PASS | 四案例可比性 PASS；真实结论 `NO_MEASURABLE_GAIN`，不构成当前 Change 阻断 |
| 六类 Promotion 负向注入 | PASS | 测试源码确实修改底层 decision/gate/trace/workspace/test event；全量测试证据覆盖并通过 |
| 中文统一验收报告存在 | PASS | [验收报告](/Users/caihaoming/Documents/stock_agent/reviews/runtime/runtime-replay-and-eval-hardening-acceptance.md:1) 存在且为中文 |
| 报告绝对路径闭包 | PASS | 实际抽取 15 个绝对路径，`missing=[]` |
| Task 11.9 报告完整性 | **FAIL** | 报告没有记录完整纵向链路的全部命令、全部 run/eval/gate ID、全部产物路径与 hash；Execution Replay、Runtime Eval、Calibration、Ablation 的执行命令缺失，两个 Promotion hash 仅写“见产物内” |
| 当前候选 Promotion | FAIL（预期限制） | 仅 `version_completeness` FAIL；其他硬门禁 PASS |
| Task 11.10 | PASS（状态真实性） | 仍为 `[ ]`，不得归档、提交或推送 |

## 阻断问题

1. **Regression invariant 契约未完整实现。**  
   [Design](/Users/caihaoming/Documents/stock_agent/openspec/changes/runtime-replay-and-eval-hardening/design.md:159) 明确列出 `must_pass_risk`、`must_fail_stage`、`evidence_subset_of_gate` 等 typed invariants；当前 [Regression Schema](/Users/caihaoming/Documents/stock_agent/product/schemas/runtime/regression-case.schema.json:18) 对 type/value 几乎不设约束，[valid-action case](/Users/caihaoming/Documents/stock_agent/evals/regression/v1/cases/valid-action-contract.json:1) 也没有 Risk invariant。虽然本次实际产物经过 Risk，但契约不能持续保证这一点。

2. **future-information 的同 Run 链已闭合，但 Design 所要求的注入语义仍未闭合。**  
   当前正常 PIT Gate 排除了未来 Evidence；随后 [runner](/Users/caihaoming/Documents/stock_agent/evals/regression/runner.py:684) 直接把 outcome 标为 `validator_rejection=PIT_LEAKAGE`。该 Run 因 Agent 前安全终止，没有生成 [runner 预期的 injection artifact](/Users/caihaoming/Documents/stock_agent/evals/regression/runner.py:526)，也未在 Trace 标记 fixture producer。这与 Design 的“PIT 篡改并在 Trace 留痕”不一致。

3. **Task 11.9 报告不完整。**  
   报告只列出八条命令，[并称其为“按实际执行意图记录”](/Users/caihaoming/Documents/stock_agent/reviews/runtime/runtime-replay-and-eval-hardening-acceptance.md:23)，没有覆盖 Design 要求的完整纵向链路；[两个 Promotion SHA-256 也未直接记录](/Users/caihaoming/Documents/stock_agent/reviews/runtime/runtime-replay-and-eval-hardening-acceptance.md:48)。绝对路径均存在，但“引用不悬空”不等于“全部证据已纳入报告”。

## 非阻断但禁止晋升的问题

[Promotion result](/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/promotion/candidate-release-fix-v2/result.json) 的 FAIL 属实：

- 当前锁：`ecc5578a…`
- 历史 Replay/Ablation 锁：`ae13c85f…`、`5d0e5faa…`
- baseline manifest 缺 assurance；
- baseline Runtime Eval 为 0，baseline Ablation 缺失。

按照用户指定的判定边界，这些只作为“当前候选不得晋升”的已知限制，不单独用来否定 Change 实现。

## Tasks 勾选不一致

建议独立批准前重新审视以下已勾选项：

- **6.1：不完整**——`expected_invariants` 不是严格 typed schema。
- **6.3：不完整**——valid-action case 未声明 Risk hard invariant。
- **6.4：部分不真实**——valid-action 实际注入已关闭；future case 没有 Design 要求的 PIT 篡改/Trace fixture producer。
- **11.9：不真实**——统一报告存在且路径闭包完整，但未记录“全部”命令、ID、路径和 hash。
- **11.10：正确保持未完成。**

6.8、8.8、10.5、11.8 的底层证据目前可信。11.1/11.4/11.7 的旧版本锁问题仅按 Promotion 已知限制处理，没有单独据此判定实现失败。

## 实际执行的只读命令

```text
openspec validate runtime-replay-and-eval-hardening --strict

PYTHONDONTWRITEBYTECODE=1 python3 -B -c '<调用：
verify_deterministic_test_evidence；
verify_regression_suite；
verify_execution_replay_result；
verify_runtime_eval_job；
verify_runtime_ablation_result；
verify_calibration_execution_proof；
validate_replay_capsule；
validate_materialized_snapshot>'

PYTHONDONTWRITEBYTECODE=1 python3 -B -c '<抽取验收报告绝对路径并检查 exists；结果 missing=[]>'

jq ... <Regression/Trace/Gate/Risk/Eval/Promotion JSON>
stat -f '%Lp %Sp %N' <Capsule 与 Execution Replay workspace>
shasum -a 256 <测试、Replay、Calibration、Ablation、Regression、Promotion 产物>
```

最终裁定：**不得进入人工批准，不得勾选 Task 11.10，不得归档或晋升。**