# runtime-replay-and-eval-hardening 可审计验收报告

## 1. 当前结论与范围

- Change 实现进度为 69/70；`Task 11.10` 保持未完成。
- 本轮只关闭 typed `expected_invariants`、未来信息确定性注入证明、验收报告完整性三个阻断，没有重新执行泛化全量 Release Gate。
- 当前 canonical candidate version lock 为 `618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`；Regression Set 版本为 `1.1.0`，set hash 为 `6004fb79ed7ec5de46310e017cf493b2362b3259ddf2222982d78e75d9a143ef`。
- 聚焦单元/集成测试为 15/15 PASS；受影响的六个确定性 Regression/Runtime Eval 案例为 6/6 PASS。
- 历史完整 12-case Regression 在旧锁 `ecc5578a...`、Regression Set `1.0.0` 下为 12/12 PASS；它证明完整链已经实际运行，但不能替代最终 Gate 对当前 `1.1.0` typed contract 的一次完整重验。
- Promotion Gate 保持真实 FAIL。当前状态定义为 `NOT_PROMOTABLE_BUT_CHANGE_VALIDATED`：Change 能力已具备进入最终独立只读 Gate 的条件，但现有证据包不能晋升。

## 2. 三项阻断的 Root Cause 与修复映射

| 阻断 | Root Cause | 修复 | 关闭证据 | 结果 |
|---|---|---|---|---|
| typed `expected_invariants` | Schema 只约束为字符串，Runner 维护手写分支，未知 invariant 可能进入 fixture，Eval 与 Regression 词汇不统一 | 新增 canonical invariant registry；Schema 由 registry 生成 discriminated `oneOf`；Runner 与 Runtime Eval 共享验证/事实派生；未知类型、错误 value 类型和 schema 漂移均 fail-closed | `tests.test_runtime_regression` 15/15；19 类 invariant 均有正负判定；未知类型与错误类型负例通过；六个受影响案例 6/6 | PASS |
| Future-information-leakage 注入 | Runner 在 PIT 结果产生后推导 `PIT_LEAKAGE` 摘要，没有可证明的 pre-Gate producer、注入对象和机制 | fixture 显式声明 `injection_evidence_ids`；先生成 baseline，再由版本化 injector 在 PIT Gate 前追加未来 Evidence；Trace、注入记录、Gate 与 Eval 绑定同一 ID/时间/hash | run `regression-focused-closure-20260908-future-information-leakage-0c1ee5e5f05d`；两个未来 ID 均被 Gate 排除；Eval `injection_verified=true`、`leak_count=0`；删除 Trace 注入事件或模拟 Gate 放行均 FAIL | PASS |
| Verification Report 完整性 | 原报告只有部分命令和 PASS 摘要，缺少全链每阶段的 ID、输入、输出、锁、hash、Specs/Tasks 映射 | 本报告第 4 节逐项列出 Run、Artifact Replay、Execution Replay、Runtime Eval、Calibration、12-case Regression、Ablation、Promotion Gate 的实际证据 | 第 4 节路径闭包及第 7 节状态边界 | PASS |

## 3. 本轮聚焦验证

### 3.1 聚焦测试

```text
TMPDIR=/private/tmp/stock-agent-typed-invariants-20260908 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_regression
```

- 结果：15 tests，0 assertion failure，0 test error，PASS。
- 覆盖：typed registry 全类型正负判定、未知 invariant、错误 value 类型、Schema/registry 同源、全局唯一 run_id、Runner 执行 Trace→Artifact Replay→Runtime Eval、未来注入正负路径、合法 action 实际经过 Risk。

### 3.2 受影响 Regression / Eval 子集

```text
TMPDIR=/private/tmp/stock-agent-typed-invariants-20260908 PYTHONDONTWRITEBYTECODE=1 python3 -c 'exec("""from pathlib import Path
import json
from evals.regression.runner import load_regression_set, _materialize_deterministic_case, _check_invariant, _write
from product.runtime.hashing import canonical_hash
root = Path.cwd()
out = root / "evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908"
reg = load_regression_set(root)
candidate = canonical_hash(json.loads((root / "product/version-manifest.json").read_text(encoding="utf-8")))
rows = []
for case in (item for item in reg["cases"] if not item["llm_required"]):
    outcome, proof = _materialize_deterministic_case(root, case=case, suite_id="focused-closure-20260908", candidate_hash=candidate, case_dir=out / case["case_id"])
    status = "PASS" if all(_check_invariant(invariant, outcome) for invariant in case["expected_invariants"]) else "FAIL"
    rows.append({"case_id": case["case_id"], "run_id": outcome["run_id"], "status": status, "case_hash": case["case_hash"], "outcome": outcome, "execution_proof": proof})
result = {"schema_version": "focused-regression-subset/1.0.0", "suite_id": "focused-closure-20260908", "candidate_version_lock": candidate, "regression_set_hash": reg["set_hash"], "selected_case_count": len(rows), "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL", "cases": rows}
result["result_hash"] = canonical_hash(result)
_write(out / "subset-result.json", result)
""")'
```

- suite_id：`focused-closure-20260908`
- 输入：`evals/regression/v1/manifest.json`、六个 typed case、对应版本化 fixture。
- 输出：`evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908/subset-result.json`
- 输出 SHA-256：`5f03a6347d846b90f44babdf4e9dc1008e153af89a5b54d7fd2ed262eaa0a43c`
- candidate lock：`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`
- 结果：6/6 PASS，零 LLM 调用。

| case_id | run_id | 结果 |
|---|---|---|
| all-evidence-stale | `regression-focused-closure-20260908-all-evidence-stale-b9647dff76d9` | PASS |
| future-information-leakage | `regression-focused-closure-20260908-future-information-leakage-0c1ee5e5f05d` | PASS |
| dangling-evidence-reference | `regression-focused-closure-20260908-dangling-evidence-reference-d7e9374b2aa1` | PASS |
| mandatory-no-trade | `regression-focused-closure-20260908-mandatory-no-trade-c85c4991cf29` | PASS |
| valid-action-contract | `regression-focused-closure-20260908-valid-action-contract-acd3c70a183b` | PASS |
| invalid-specialist-output | `regression-focused-closure-20260908-invalid-specialist-output-0054b5e5c8f3` | PASS |

### 3.3 Future Evidence 确定性证明

- producer：`regression-fixture-injector`
- mechanism/version：`append_declared_evidence_before_pit_gate` / `future-evidence-injection/1.0.0`
- decision cutoff：`2026-01-31T23:59:59Z`
- 注入 ID：`ev-future-asof`、`ev-future-retrieval`
- baseline fixture SHA-256：`540515997273f22a32ae0402680d9028b1c8449d823ec58e4f9ed76f75c1d154`
- injected fixture SHA-256：`293beb7a78a6727fb17caa0484e623a90c8596922fd8d87354d04eaf1796e7da`
- injection record SHA-256：`8c49597add8e74d4973c0167c5ea5e8da7669f1c8376ffc7e541346810fbd09c`
- Trace event：`REGRESSION_FIXTURE_INJECTED`，包含 producer、evidence_id、原始 `as_of/published_at/retrieved_at`、cutoff、mechanism/version 和 artifact hash。
- PIT Gate：两个 ID 均不在 `allowed_evidence_ids`；排除原因包含 `FUTURE_AS_OF` / `FUTURE_RETRIEVAL`。
- Runtime Eval：`pit_leakage.status=PASS`、`injection_verified=true`、`leak_count=0`。
- 产物：
  - `evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908/future-information-leakage/injection/baseline-fixture.json`
  - `evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908/future-information-leakage/injection/injected-fixture.json`
  - `evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908/future-information-leakage/run/audit/regression-injection.json`
  - `evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908/future-information-leakage/run/evidence/gate.json`
  - `evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908/future-information-leakage/run/decision_trace.json`
  - `evals/results/runtime-replay-and-eval-hardening-focused-closure-20260908/future-information-leakage/runtime-eval/eval/result.json`

## 4. Change 实际执行链

本节记录已实际完成的全链证据。历史产物保持其真实 version lock；不把不同锁伪装成同一可晋升候选。

### 4.1 Run → Persist

实际命令：

```text
python3 -m product.runtime.cli smoke-prompt --repo /Users/caihaoming/Documents/stock_agent --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/runs/normal-research | codex exec -C /Users/caihaoming/Documents/stock_agent/product --add-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/runs/normal-research --strict-config --json -m gpt-5.6-terra -
```

- ID：`rrh-final-normal-research-20260908`
- 输入：`evals/fixtures/codex-native/normal-research.json`，SHA-256 `663ce7ed097e20cee418c2748822cde2a968ae474e819b5a841c2e7ce41d8173`。
- 输出：`evals/results/runtime-replay-and-eval-hardening-final-20260908/runs/normal-research/`；Trace SHA-256 `4777f9e77b39f9e4dbd85a41a1e458351e4f80c58c6cceedb677062014f6dce9`。
- Capsule manifest/root hash：`ec1c89fb4d5262652aa68bc2843b4e7369fe77335b80b616090a8eb8ae5d4e10` / `51055c8bc16ac11ee8d1be85e887209b520fcf161ad00230a5c512e868fe6285`。
- 锁：`ecc5578a0116d1ef0220cbaa5698a4bc6aabe7bbc8aa425b7244d5beaa925017`；model `gpt-5.6-terra`；Codex `codex-cli/0.153.4`。
- 结果：`SAFE_NO_TRADE`；三个独立 Agent 上下文均在 Trace 中。
- Specs / Tasks：portfolio-council-orchestration「Execution Replay 必须通过受控的 Codex-native Council 入口运行」；11.1、11.2。

### 4.2 Artifact Replay

实际命令：

```text
python3 -m product.runtime.cli artifact-replay --repo /Users/caihaoming/Documents/stock_agent --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/runs/normal-research --output /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/replay/artifact-replay-normal-release-fix.json
```

- ID：source run `rrh-final-normal-research-20260908`。
- 输入：源运行、Trace、Replay Capsule；输出：`replay/artifact-replay-normal-release-fix.json`。
- 输出 SHA-256：`68953b285ecf7dd863f064ec5062df20625e17d7c35fa5793017ef9d6feffc9e`；锁：源运行 `ecc5578a...`；LLM calls=0。
- 结果：PASSED，源运行未修改。
- Specs / Tasks：decision-trace-evaluation「Artifact Replay 与 Execution Replay 必须是两个独立模式」；4.1、11.3。

### 4.3 Execution Replay

实际命令链：

```text
python3 -m product.runtime.cli prepare-execution-replay --source-run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/candidate-risk-veto-current --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runs/execution-replay-risk-veto --run-id rreh-hardening-execution-replay-risk-veto-20260907 --workspace /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/workspaces/execution-replay-risk-veto
codex exec -C /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/workspaces/execution-replay-risk-veto/product --add-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runs/execution-replay-risk-veto --strict-config --json -m gpt-5.6-terra -
python3 -m product.runtime.cli finalize-execution-replay --source-run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/candidate-risk-veto-current --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runs/execution-replay-risk-veto --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/replay/execution-replay-risk-veto
```

- ID：source `rreh-candidate-risk-veto-current-20260907`；replay `rreh-hardening-execution-replay-risk-veto-20260907`。
- 输入：source Replay Capsule、密封 workspace；输出：`replay/execution-replay-risk-veto/result.json`。
- 输出 SHA-256 / result hash：`ab4f8dca8028376a977e993dda0d343859677c044235619ff2da6434ab7ee284` / `3ef4e04212ff6a5988b71795be35a1379f40d09a8fe1220da9536ee0c1e18f4e`。
- 锁：source 与 replay 均为 `ae13c85f3189025de2ea9dcdd3156b3d25c15544802950f9a86e95cf4ad1edb4`。
- 结果：PASS；Finalizer 重算九类配置 hash，`configuration_equivalent=true`。
- Specs / Tasks：decision-trace-evaluation「可执行重放必须依赖完整且内容寻址的 Replay Capsule」及 portfolio-council-orchestration 受控入口；4.2–4.6、11.4。

### 4.4 Runtime Eval

实际命令与 Codex 执行事件：

```text
python3 -m product.runtime.cli eval-prepare --repo /Users/caihaoming/Documents/stock_agent --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/candidate-risk-veto-current --eval-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runtime-evals-regraded/candidate-risk-veto-current --eval-id rreh-hardening-regression-eval-risk-veto-current-20260908
Codex execution event：受保护 dispatch dev_eval / gpt-5.6-terra；执行事件和输入输出 hash 保存于 candidate-risk-veto-current/grader-execution-proof.json
python3 -m product.runtime.cli eval-finalize --repo /Users/caihaoming/Documents/stock_agent --eval-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runtime-evals-regraded/candidate-risk-veto-current --semantic-result /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runtime-evals-regraded/candidate-risk-veto-current/semantic-result.json
python3 -m product.runtime.cli eval-prepare --repo /Users/caihaoming/Documents/stock_agent --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runs/execution-replay-risk-veto --eval-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runtime-evals-regraded/execution-replay-risk-veto --eval-id rreh-hardening-regression-eval-execution-replay-risk-veto-20260908
Codex execution event：受保护 dispatch dev_eval / gpt-5.6-terra；执行事件和输入输出 hash 保存于 execution-replay-risk-veto/grader-execution-proof.json
python3 -m product.runtime.cli eval-finalize --repo /Users/caihaoming/Documents/stock_agent --eval-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runtime-evals-regraded/execution-replay-risk-veto --semantic-result /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/runtime-evals-regraded/execution-replay-risk-veto/semantic-result.json
```

| eval_id / run_id | 输入与输出 | hash | 结果 |
|---|---|---|---|
| `rreh-hardening-regression-eval-risk-veto-current-20260908` / `rreh-candidate-risk-veto-current-20260907` | `runtime-evals-regraded/candidate-risk-veto-current/input-manifest.json` → `eval/result.json` | eval hash `769fbb5a...`；文件 SHA-256 `5919c851...` | PASS |
| `rreh-hardening-regression-eval-execution-replay-risk-veto-20260908` / `rreh-hardening-execution-replay-risk-veto-20260907` | `runtime-evals-regraded/execution-replay-risk-veto/input-manifest.json` → `eval/result.json` | eval hash `dbdd61c9...`；文件 SHA-256 `65d587df...` | PASS |

- 输入 manifest 逐项保存 run tree、Trace、Artifact Replay、rubric、prompt、schema 与语义输入 hash。
- grader：`dev_eval` / `gpt-5.6-terra` / `runtime-eval-grading/1.0.0`。
- Specs / Tasks：decision-trace-evaluation「Runtime Eval 必须直接评估真实运行产物」「确定性硬门禁与语义 Rubric 分离」；5.1–5.8、11.5。

### 4.5 Calibration

两个独立 Codex `dev_eval` session 完成评分后执行：

实际命令与执行事件：

```text
python3 -m product.runtime.cli eval-calibration --repo /Users/caihaoming/Documents/stock_agent --labels /Users/caihaoming/Documents/stock_agent/evals/grading/calibration/v1/labels.json --grader-index /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/calibration/index.json --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/calibration/result
```

- session ID：`01a07c36-2f13-7492-a0ca-9a540320547f`、`01a07c3a-de28-75e2-bc08-dbc6727f7a95`。
- 输入：labels SHA-256 `c0da4243...`；grader index SHA-256 `79a1b34f...`。
- 输出：`calibration/result/result.json`；文件 SHA-256 / result hash：`cf8cf8b63d79818dad358a9aece82b02bec81df677365d50276d46ae84b1aa79` / `833076bc17d413e266ab4a8ccb8cb964aedf8f3e5a7dd46e02cda37ed7577242`。
- proof：`calibration/repeat-1/grounded-balanced.execution-proof.json`、`repeat-2/grounded-balanced.execution-proof.json`，含 session、事件、模型、prompt/input/output 与 rollout hash、时间。
- 结果：PASS；30 observations，agreement=1.0，门槛=0.8。
- Specs / Tasks：controlled-learning-loop「语义校准必须证明独立 dev_eval 执行」；5.5、5.8。

### 4.6 12-case Regression

实际命令：

```text
python3 -m product.runtime.cli regression --repo /Users/caihaoming/Documents/stock_agent --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/regression/suite-release-fix --suite-id rrh-release-fix-20260908 --candidate-hash ecc5578a0116d1ef0220cbaa5698a4bc6aabe7bbc8aa425b7244d5beaa925017 --run-index /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/regression/run-index.json --force
```

- ID：`rrh-release-fix-20260908`。
- 输入：run index SHA-256 `3289f928...`；candidate lock `ecc5578a...`；set hash `1946efea...`。
- 输出：`regression/suite-release-fix/result.json`；SHA-256 / suite hash：`99bce356b0f9edf18792905e7e87d8b94c46fc39e02b38f62e3136ae82eec552` / `7f6bca3ba4d3cabb735791db4ee57e72a2d1bdfdbcaeb3b792c2ea4a8c4e9321`。
- 结果：12/12 PASS；六个真实 LLM 案例 run_id 唯一，六个确定性案例零 LLM；Runner 对每例执行 Trace→Artifact Replay→Runtime Eval。
- 当前 typed `1.1.0` 增量证明见 3.2；最终独立 Gate 需对当前 set 再完整运行一次，本轮不提前执行。
- Specs / Tasks：decision-trace-evaluation「Regression Set 必须以 expected_invariants 描述至少十二类案例」；6.1–6.8、11.6。

### 4.7 Ablation

实际命令：

```text
python3 -m product.runtime.cli ablation --repo /Users/caihaoming/Documents/stock_agent --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/ablation/comparison-hardening-final --ablation-id rreh-hardening-ablation-final-20260908 --variants /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/ablation/variants-hardening-final.json
```

- ID：`rreh-hardening-ablation-final-20260908`。
- 输入：A/B/C 真实 run/eval index；variants SHA-256 `21ca3798...`；profiles hash `7e69d262...`。
- 输出：`ablation/comparison-hardening-final/result.json`；SHA-256 / report hash：`25bbf81a719fe724feab279fc5064efdc4701f12207d2ff7047efbeb3068c7e8` / `2ceb98504ef84662042c0d91d7d3424181c92aebd74c81e79dba6744ca8f1cf0`。
- 结果：comparability PASS；`NO_MEASURABLE_GAIN`，没有预设多 Agent 更优。
- Specs / Tasks：decision-trace-evaluation「Ablation 必须基于可比的真实运行而非人工分数」；7.1–7.6、11.7。

### 4.8 Promotion Gate

实际命令：

```text
python3 -m product.runtime.cli promotion --repo /Users/caihaoming/Documents/stock_agent --input-manifest /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/promotion/input-release-fix.json --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-20260908/promotion/candidate-release-fix-v2
```

- ID：`rrh-release-fix-promotion-20260908`。
- 输入：`promotion/input-release-fix.json`，SHA-256 `3289c5f10ed5364681f2eb02649ecdf66ca4b812a0ec418e371ec12e5eba48b2`，逐项绑定测试、Eval、Regression、Replay、Calibration、Ablation 与 Trace hash。
- 输出：`promotion/candidate-release-fix-v2/result.json`；SHA-256 / result hash：`f35325a4acc4564b24e6abeb3ba4b1e2c48b15e350f019c18c27aeb162afe78a` / `34aa720163af3d30b31414f1db92dfe6db03e7b28650115f1767e65b1d19d348`。
- 结果：FAIL；唯一失败硬门禁为 `version_completeness`。其他安全与质量门禁由 Gate 重读底层证据后通过。
- 真实断言失败负例：`promotion/negative-assertion-release-fix-v2/result.json` 为 FAIL。
- Specs / Tasks：controlled-learning-loop「Promotion Gate 必须直接消费真实验证产物并执行安全硬门禁」；8.1–8.8、11.8。

## 5. Promotion version_completeness 分类

### A. 本 Change 生成证据的版本混用

现有 Promotion 输入同时引用 `5d0e5f...`、`ae13c85...`、`ecc5578...` 三个候选锁。这来自实现期间分阶段生成的 Execution Replay、Ablation、Regression/Eval 证据被组合进同一次候选 Gate。它们各自在自己的锁下可验证，但不能共同证明一个可晋升候选。

处理：不修改门禁，不继承或强制写入 `configuration_equivalent=true`，不把历史证据改写成当前 `618f746...`。这些产物只用于证明 Change 能力已实际执行，不能用于当前版本晋升。

### B. 历史 baseline 天然不完整

baseline `0.2.1-candidate.1` 缺少新版 assurance、Runtime Eval 与 Ablation 闭包，旧 manifest 也不满足当前完整性 Schema。该历史事实不补写、不伪造。

因此 Promotion 保持：

```text
NOT_PROMOTABLE_BUT_CHANGE_VALIDATED
```

真正 Promotion PASS 需要在单一新鲜 version lock 下重建候选全链，并建立符合当前契约的 baseline；不能通过放宽门禁获得。

## 6. 版本、模型与消耗

- 本轮受影响子集 LLM calls=0；没有升级 GPT-6 Astra。
- 历史真实 Runtime Regression 使用 `gpt-5.6-terra`。
- 历史六个真实 LLM Regression 案例共记录 96 次调用事件、3,216,952 input tokens、67,505 output tokens、2,717,952 cached tokens、1,402,929 ms 累计延迟；这是 Trace 聚合遥测，不是本轮新增调用。
- canonical registry SHA-256：`36170c9f6e7313d2f0edf9f6dabff8c5bc32aaf26e43faa6bab23e3477955a35`。
- regression-case Schema SHA-256：`ea1153a7d6425e58a169e6872dfa64862a1bf6d3afd209358f1a51498be1502f`。

## 7. 最终边界

- 三项指定阻断均有明确关闭证据。
- `FINAL_RELEASE_GATE_READY=true`，但尚未执行最终独立只读 Release Gate。
- `Task 11.10` 仍未完成；不得归档、提交、推送或晋升。
- 当前 Promotion 为 `NOT_PROMOTABLE_BUT_CHANGE_VALIDATED`，不生成 `promotion/PASS`。
- 本 Change 未增加真实行情、SEC/FRED、新投资 Agent、Reflection Agent、自动修改 Skill 或真实交易能力。
