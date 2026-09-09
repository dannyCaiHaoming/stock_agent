# runtime-replay-and-eval-hardening 最终独立只读 Release Gate 报告

日期：2026-09-08（Asia/Shanghai）  
仓库：`/Users/caihaoming/Documents/stock_agent`  
Change：`runtime-replay-and-eval-hardening`  
评审范围：仅按本 Change 的 Proposal、Specs、Design、Tasks 与中文 Runbook；不验收真实行情、新 Agent 或未来数据能力。

## 1. 最终裁定

**Release Gate：FAIL。**

可采用状态描述：`NOT_PROMOTABLE_BUT_CHANGE_VALIDATED`，但只表示本 Change 的主要确定性加固能力和历史真实运行证据已得到验证；它不表示当前候选满足晋升条件。

不得晋升、归档、提交或推送。`Task 11.10` 已核对并保持 `[ ]`。

直接阻断项：

1. 当前 canonical candidate lock 为 `618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`，当前 12-case Regression set hash 为 `6004fb79ed7ec5de46310e017cf493b2362b3259ddf2222982d78e75d9a143ef`；本轮 Regression 在第三例 `all-evidence-stale` 因 `REGRESSION_CANDIDATE_VERSION_MISMATCH` fail closed，未形成当前锁下的完整 12-case PASS。
2. 可用历史 12-case PASS 绑定旧 candidate lock `ecc5578a0116d1ef0220cbaa5698a4bc6aabe7bbc8aa425b7244d5beaa925017` 和旧 set hash `1946efea07c2337c76551f8fb32d8fbf7a55cc3cef8a2eedb8e855049faef7b7`。当前 verifier 明确以 `REGRESSION_SET_HASH_MISMATCH` 拒绝，不能替代当前候选证据。
3. Promotion Gate 实际输出 `FAIL`，失败硬门禁为 `runtime_regression`、`mandatory_no_trade`（由不可验证的当前 Regression 派生）和 `version_completeness`。候选证据还混有 `5d0e5faa...` 与 `ae13c85f...` 两种历史锁。
4. 本轮未新启动具有文件写入/投资决策能力的 Council。评审权限明确禁止 `filesystem-write`、`investment-decision`、`broker-write` 和 `production-promotion`；因此只能复核已有真实 `gpt-5.6-terra` Run、Execution Replay 与 grader proof。若“本轮至少各新执行一次真实 LLM Run/Execution Replay”被解释为不可复用历史证明，则该条同样未满足。
5. 当前 Change 没有符合现行 `PromotionRecord` 契约的人工批准记录；历史 `candidate-0.1.0.json` 只有状态字符串，没有 `approved_by`、`decided_at` 和 rollback 条件，不能作为本候选批准。

## 2. 实际执行结果

| 阶段 | 结果 | 核心 ID / hash | 核心产物 |
|---|---|---|---|
| OpenSpec strict validate | PASS | exit 0 | `commands/01-openspec-strict-validate.log` |
| 全量确定性测试 | PASS | 277 tests；0 assertion failure；0 test error；event `test-event-f0e584f0-81d4-4ac1-9af7-1baba403ff40`；result hash `1a3cad9a...` | `test-evidence/full-suite/result.json` |
| Run/Seal 只读复核 | PASS（历史真实 Run） | Run `rrh-final-normal-research-20260908`；Execution Replay Run `rreh-hardening-execution-replay-risk-veto-20260907`；sealed workspace 可写对象数 0 | `commands/26-run-seal-check.log`、`commands/31-permission-seal-approval.log` |
| Artifact Replay | PASS | `llm_calls=0`；replay hash `3e25df5397...` | `replay/artifact-replay-source-normal.json` |
| Execution Replay Finalizer | PASS | source `rreh-candidate-risk-veto-current-20260907`；replay `rreh-hardening-execution-replay-risk-veto-20260907`；result hash `3ef4e042...` | `replay/execution-replay-refinalized/result.json` |
| Runtime Eval | PASS | 三份 eval hash：`a5993a27...`、`769fbb5a...`、`dbdd61c9...`；全部 `gpt-5.6-terra` | `runtime-evals/*/eval/result.json` |
| 12-case Regression（当前契约） | **FAIL** | `REGRESSION_CANDIDATE_VERSION_MISMATCH:all-evidence-stale:618f746c...`；CLI exit 6 | `commands/11-regression-12-case.log` |
| 12-case Regression（历史证据审计） | PASS，但不可用于当前晋升 | 12/12；12 个全局唯一 run_id；suite `rrh-release-fix-20260908`；suite hash `7f6bca3b...` | `commands/33-historic-12-case-lineage-audit-corrected.log` |
| Calibration | PASS | 30 observations；agreement 1.0；threshold 0.8；result hash `833076bc...` | `calibration/result.json` |
| Ablation | PASS | 4 cases × 3 profiles；comparability PASS；`NO_MEASURABLE_GAIN`；report hash `0de3fb2a...` | `ablation/result.json` |
| Promotion Gate | **FAIL（正确拒绝）** | Gate `rrh-final-independent-gate-20260908`；result hash `d8960e37...`；只有零字节 `FAIL` sentinel | `promotion/result.json` |
| Promotion 真实断言失败负例 | PASS（负例被拒绝） | assertion failure 1、test error 0；Gate reason 包含 `PROMOTION_HARD_GATE_FAILED:deterministic_tests` | `promotion-negative-assertion/result.json` |

所有相对路径均位于：

`/Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-final-independent-20260908`

核心文件 SHA-256 清单：`artifact-sha256.tsv`。

## 3. 关键专项核验

### 3.1 19 类 typed invariant 与 canonical registry

底层 verifier 重新加载 `INVARIANT_REGISTRY` 并校验 checked-in `regression-case.schema.json` 与 registry 精确绑定，结果 PASS，类型数恰为 19：

`TERMINAL_STATE_IN`、`AGENTS_INCLUDE`、`AGENTS_EXCLUDE`、`RISK_NOT_BYPASSED`、`EXPECT_RISK_PASS`、`EXPECT_RISK_VETO`、`EXPECT_NO_TRADE`、`NO_FUTURE_EVIDENCE`、`EVIDENCE_CLOSURE`、`TRACE_COMPLETE`、`SPECIALIST_OUTPUT_VALID`、`CIO_CONFLICT_HANDLED`、`EXPECT_FAILED_STAGE`、`EVIDENCE_SUBSET_OF_GATE`、`SEMANTIC_DIMENSIONS_APPLICABLE`、`EXPECT_VALIDATION_REJECTION`、`LLM_CALLS_EQUAL`、`VALID_ACTION_SET`、`FORBIDDEN_ACTION`。

证据：`commands/28-bottom-up-verifiers-corrected.log`；全量测试同时覆盖未知类型、错误 value 类型、Schema 漂移和各类型正负例。

### 3.2 Future Evidence

真实因果链已从底层核对：Runner 先生成 baseline fixture，再追加两个声明的未来 Evidence，随后将 injected fixture 交给 `prepare_run` 执行 PIT Gate；不是在 Gate 之后伪造摘要。

- producer：`regression-fixture-injector`
- mechanism：`append_declared_evidence_before_pit_gate`
- injection version：`future-evidence-injection/1.0.0`
- 注入 ID：`ev-future-asof`、`ev-future-retrieval`
- 注入记录 SHA-256：`8c49597add8e74d4973c0167c5ea5e8da7669f1c8376ffc7e541346810fbd09c`
- PIT：allowed IDs 为空；两项分别以 `FUTURE_AS_OF` / `FUTURE_RETRIEVAL` 排除
- Runtime Eval：`injection_verified=true`、`leak_count=0`、`status=PASS`
- Artifact Replay hash：`8ae1c3ed...`

证据：`commands/12-future-artifact-replay.log`、`commands/13-future-trace-check.log`、`commands/14-future-runtime-eval-verify.log`、`commands/28-bottom-up-verifiers-corrected.log`。

### 3.3 Replay Finalizer 不继承摘要

`verify_execution_replay_result` 从 source/replay 底层运行重新计算并逐项比较九类配置：agents、skills、prompt/instructions、schemas、model、MCP adapters、risk policy、evidence、runtime profile；全部相等后才得到 `configuration_equivalent=true`。密封 workspace 为目录 `0555`、文件 `0444`，可写文件/目录计数为 0。

证据：`commands/05-execution-replay-finalize.log`、`commands/28-bottom-up-verifiers-corrected.log`、`commands/31-permission-seal-approval.log`。

### 3.4 Promotion 不信任上游摘要

Promotion 输入包含一份历史 `status=PASS` 的 12-case 汇总，但当前 Gate 重新加载当前 Regression set 后产生 `REGRESSION_SET_HASH_MISMATCH` 并输出 FAIL；真实 assertion-failure 负例也由原始 subprocess event 重算并被 deterministic test hard gate 拒绝。因此 Gate 没有信任上游 PASS 或 `configuration_equivalent` 声明。

### 3.5 权限、Risk 与学习边界

- Runtime MCP registry 只有 `query` / `calculate`，`AccessMode` 只有 `READ`；MCP annotations 为 `readOnlyHint=true`、`destructiveHint=false`、`openWorldHint=false`；未发现 broker/order/account write capability。
- Risk Engine 的 deterministic rule basis 仅允许 `accounting_identity`、`mathematical_definition`、`data_quality`、`explicit_mandate`，指标来自有限 allowlist；REJECTED 强制映射 `NO_TRADE` + `RISK_VETO`，不编码主观 Thesis 选择。
- Learning 输出为 `ImprovementProposal`；Promotion ledger 需要明确 `approved_by`、时间、理由和 rollback 条件。Promotion policy 为 `automatic_production_mutation=false`，Gate 写入范围仅为调用方 output directory。
- 产品 runtime tool 权限为只读。`runtime_cio.toml` 的宿主 sandbox 配置仍是 `workspace-write`，用于运行产物持久化；本评审没有取得或使用该权限启动新 Council。Execution Replay 使用的实际物化 workspace 已被 seal 为只读。

证据：`commands/30-boundary-and-seal-audit.log`、`commands/31-permission-seal-approval.log`、全量测试中的权限、学习与 Promotion allowlist 负例。

## 4. 分类结论

### 产品/候选断言失败（阻断）

- 当前 candidate/version closure 下没有完整 12-case Regression PASS。
- 当前 Promotion Gate 为 FAIL，且 version completeness 不满足。
- 当前候选没有有效人工批准记录。

### 环境或权限失败

- 全量测试没有环境错误：`environment_errors=0`。
- 唯一能力限制是本评审明确禁止 filesystem-write / investment-decision 权限，故没有为了满足“新执行”而绕过边界启动 Council；已有真实 Terra 证据已完整重验，但不被冒充为本轮新调用。

### 历史基线不完整

- baseline `0.2.1-candidate.1` 缺少当前 Schema 要求的 assurance、baseline Runtime Eval 和 baseline Ablation，`baseline_manifest_valid=false`。本评审没有补写或伪造历史证据。

### 非阻断问题

- Ablation 如实报告 `NO_MEASURABLE_GAIN`；Change 没有新增或默认启用 Agent，按设计不构成单独阻断。部分 mandatory-no-trade profile 的 token/latency 为 `MISSING_TELEMETRY`，没有被当成 0。
- Change 自带验收报告称 Regression Set 为 `1.1.0`，但 checked-in manifest 的 `set_id`/schema 仍显示 `1.0.0`；真正变化由 set hash `6004fb79...` 标识。属于报告版本标签不一致，不改变本次 FAIL。
- Future injection Trace 的 `REGRESSION_FIXTURE_INJECTED` 事件在事件数组中位于 `EVIDENCE_GATE` 之后；底层代码和 fixture/hash 证明注入实际发生在 Gate 前，Runtime Eval 也核验同一对象。建议未来将 Trace 事件顺序与因果顺序对齐以减少审计歧义。
- 评审中两次底层校验脚本最初只因读取展示字段名错误退出，修正版 `commands/28...` 与 `commands/29...` 已通过；首次错误不作为产品失败。全量测试因会话句柄未回显被重复执行一次，两次均为 277/277 PASS，权威证据采用 `full-suite`。

## 5. 实际命令与证据索引

主要命令（固定仓库根目录执行）：

```text
openspec validate runtime-replay-and-eval-hardening --strict
python3 -m product.runtime.cli test-evidence --repo /Users/caihaoming/Documents/stock_agent --output-dir .../test-evidence/full-suite --tmpdir /private/tmp/stock-agent-final-independent-20260908/full-suite-tmp
python3 -m product.runtime.cli check-run --repo /Users/caihaoming/Documents/stock_agent --run-dir .../runs/normal-research
python3 -m product.runtime.cli artifact-replay --repo /Users/caihaoming/Documents/stock_agent --run-dir .../runs/normal-research --output .../replay/artifact-replay-source-normal.json
python3 -m product.runtime.cli finalize-execution-replay --source-run-dir .../runs/candidate-risk-veto-current --run-dir .../runs/execution-replay-risk-veto --output-dir .../replay/execution-replay-refinalized
python3 -m product.runtime.cli eval-prepare ...
python3 -m product.runtime.cli eval-finalize ...
python3 -m product.runtime.cli eval-calibration --repo /Users/caihaoming/Documents/stock_agent --labels evals/grading/calibration/v1/labels.json --grader-index .../calibration/index.json --output-dir .../calibration
python3 -m product.runtime.cli regression --repo /Users/caihaoming/Documents/stock_agent --output-dir .../regression/suite --suite-id rrh-final-independent-20260908 --candidate-hash ecc5578a0116d1ef0220cbaa5698a4bc6aabe7bbc8aa425b7244d5beaa925017 --run-index .../regression/run-index.json
python3 -m product.runtime.cli ablation --repo /Users/caihaoming/Documents/stock_agent --output-dir .../ablation --ablation-id rrh-final-independent-ablation-20260908 --variants .../ablation/variants-hardening-final.json
python3 -m product.runtime.cli promotion --repo /Users/caihaoming/Documents/stock_agent --input-manifest .../promotion-input.json --output-dir .../promotion
```

完整 stdout/stderr 与退出码位于 `commands/`。其中最重要的独立重算日志为：

- `commands/26-run-seal-check.log`
- `commands/28-bottom-up-verifiers-corrected.log`
- `commands/29-runtime-eval-bottom-up-verifiers.log`
- `commands/31-permission-seal-approval.log`
- `commands/33-historic-12-case-lineage-audit-corrected.log`

## 6. Specs / Tasks 映射

| 验收主题 | Specs / Design | Tasks | 本次结论 |
|---|---|---|---|
| Artifact/Execution Replay、Capsule、只读源运行、配置重算 | `decision-trace-evaluation` Replay requirements；Design §§2–4 | 2.1–2.6、4.1–4.6、11.3–11.4 | PASS（历史真实 Terra replay，底层重算通过） |
| Runtime Eval、硬门禁与语义评分分离、grader authenticity | `decision-trace-evaluation` Runtime Eval；`controlled-learning-loop` calibration | 5.1–5.8、11.5 | PASS |
| 12-case、typed invariant、唯一 run_id、逐例 Trace→Replay→Eval | `decision-trace-evaluation` Regression Set；Design §6 | 6.1–6.8、11.6 | 历史链 PASS；当前候选 FAIL，阻断 |
| Future Evidence pre-Gate 注入、PIT 排除、Trace/Eval 绑定 | `controlled-learning-loop` 安全负例；Regression design | 5.2、6.3–6.5、8.8 | PASS |
| Ablation 可比性与不预设增益 | `decision-trace-evaluation` Ablation；Design §7 | 7.1–7.6、11.7 | PASS，`NO_MEASURABLE_GAIN` |
| Promotion 重验底层证据、无自动生产变更、人工批准 | `controlled-learning-loop` Promotion requirements；Design §8 | 8.1–8.8、11.8、11.10 | Gate 正确 FAIL；人工批准缺失；11.10 保持未完成 |
| 完整验收报告 | Tasks acceptance chain | 11.1–11.9 | 本报告补齐命令、ID、路径、hash 与映射；不改任务勾选 |

## 7. 源树未修改证明

基线与结束状态完全一致：

- HEAD：`1e565bbb534df473d92cf46ac330f33395a0c005`
- branch：`main`
- protected source manifest entries：开始/结束均 10,675
- protected untracked files：开始/结束均 10,090
- protected source tree SHA-256：开始/结束均 `74cd955fdb09c491de903a8fdbd9be74a7b7eb36daf30a1bae80240be575146f`
- `git status --porcelain=v1`：逐字节相同
- unstaged diff：逐字节相同
- staged diff：逐字节相同（空）
- protected untracked 清单：逐字节相同
- HEAD / branch：逐字节相同

证明目录：`source-tree-proof/before/`、`source-tree-proof/after/`、`source-tree-proof/comparison.txt`。

本评审只写入用户允许的验收目录和 `/private/tmp/stock-agent-final-independent-20260908`；未修改源代码、OpenSpec、任务勾选或 Git 状态。
