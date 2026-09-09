# runtime-replay-and-eval-hardening 最终独立只读 Release Gate 报告（v2）

- 日期：2026-09-08（Asia/Shanghai）
- 仓库：`/Users/caihaoming/Documents/stock_agent`
- 验收目录：`evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908`
- 独立临时目录：`/private/tmp/stock-agent-final-independent-v2-20260908`
- 候选版本：`0.3.0-candidate.1`
- 当前唯一 candidate lock：`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`
- 当前 Regression set assurance version：`1.1.0`
- 当前 Regression set hash：`6004fb79ed7ec5de46310e017cf493b2362b3259ddf2222982d78e75d9a143ef`
- 真实 Codex 模型：`gpt-5.6-terra`
- 最终结论：**FAIL — NOT_PROMOTABLE_BUT_CHANGE_VALIDATED**
- 阻断级别：**阻断发布/晋升；不阻断继续保留并修复候选实现**

## 1. 独立结论

本轮没有把旧 candidate lock 的运行或旧摘要冒充当前锁证据。当前锁下新建源运行 `rrh-final-independent-v2-source-normal-20260908`，并消费了用户授权的真实 Codex 执行事件。该进程虽然 `exit_code=0`，但 stdout 明确报告运行时缺少 `collaboration.spawn_agent` 所需能力以及 `mcp__fixture_runtime__query/calculate` 工具；底层运行目录只有准备阶段产物，`decision_trace.terminal_state=null`、事件数为 3，且没有 `agents/`、`cio/`、`risk/` 终态产物。因此不能把 shell 成功等同于 Council 成功。

统一 Trace Validator 随后真实拒绝该运行；Artifact Replay、Execution Replay prepare 和 Runtime Eval prepare 均按非终态 fail-closed。当前 typed 1.1.0 的 12-case Regression 只完成并通过 6 个确定性完整链案例，6 个需要真实 LLM 运行的案例因当前锁运行产物缺失失败。当前 candidate lock 下也没有可用的 A/B/C 运行；重新核验的历史 A/B/C 证据绑定的是两个旧锁，不能用于本轮晋升。

Promotion Gate 重读底层证据后为 FAIL，且没有当前候选的有效人工批准记录。故本轮 Release Gate 必须判 FAIL；Task 11.10 必须继续保持 `[ ]`，不得归档、同步、提交或推送。

另一方面，OpenSpec strict validate、277 项全量确定性测试、19 类 typed invariant 正负/未知类型 fail-closed、future Evidence pre-Gate injection、语义校准、运行时只读权限、硬 Risk Engine 边界、学习优化/自动生产修改禁令均获得有效证据。因此结论可标注为 `NOT_PROMOTABLE_BUT_CHANGE_VALIDATED`，但绝不等同于可发布。

## 2. 预读与评审范围

执行前已完整读取并据此评审：

- 根 `AGENTS.md`。
- `openspec/changes/runtime-replay-and-eval-hardening/proposal.md`。
- `openspec/changes/runtime-replay-and-eval-hardening/design.md`。
- `openspec/changes/runtime-replay-and-eval-hardening/tasks.md`。
- Change 下 `decision-trace-evaluation`、`controlled-learning-loop`、`portfolio-council-orchestration` 三组 delta specs。
- `reviews/runtime/runtime-replay-eval-runbook.md`。
- `reviews/runtime/runtime-replay-and-eval-hardening-acceptance.md`。
- 上一轮独立报告 `evals/results/runtime-replay-and-eval-hardening-final-independent-20260908/final-independent-release-gate-report-zh.md`，仅用于识别旧锁污染风险，不作为本轮通过证据。
- `evals/grading/semantic-rubric-v1.json` 及 Runtime Eval grading skill；该 skill 要求只有在冻结产物、hash、PIT、Trace 和执行证明完整时才允许评分，因此本轮源运行的 Runtime Eval 未被旧评分替代。

## 3. 阻断项

### B1. 当前锁真实源 Council Run 非终态

- run_id：`rrh-final-independent-v2-source-normal-20260908`
- candidate lock：`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`
- model：`gpt-5.6-terra`
- Codex 事件：`commands/05b-source-codex-exec-escalated.event.json`
- Codex shell exit：`0`
- Codex stdout SHA-256：`08fb59bd899433fa7fb5ac981b5639d726d7b761d3aa0e57a7e843a81900b7fc`
- 底层状态：`terminal_state=null`，Trace 事件数 `3`，无 Agent/CIO/Risk 终态目录。
- stdout 的实际结果：未启动子 Agent，原因是当前接口不支持所需 `agent_type`，且未提供 fixture runtime 的 query/calculate 工具。
- `check-run`：exit `3`，`TRACE_TERMINAL_STATE_INVALID`。

该项是执行环境/能力暴露失败，同时也是本 Release Gate 的硬证据缺口。按用户要求，不以旧运行、旧摘要或进程退出码替代当前运行终态。

### B2. 当前锁 Replay 与 Runtime Eval 链未成立

- Artifact Replay：exit `6`，`UNKNOWN_OR_NONTERMINAL_STATE`。
- Trace check：exit `6`，`TRACE_TERMINAL_STATE_INVALID`。
- Execution Replay prepare：exit `6`，源 Trace 非终态；因此没有生成可执行 replay prompt/event，也没有真实 replay Council 终态，更没有 Finalizer 的配置等价性结果。
- Runtime Eval prepare：exit `6`，源运行不满足评分前置条件。

因此无法证明当前锁下 Trace→Artifact Replay→真实 Execution Replay→Finalizer→Runtime Eval 的完整闭环。特别地，没有信任或复用旧的 `configuration_equivalent=true` 摘要。

### B3. 当前 typed 1.1.0 Regression 仅 6/12 PASS

- suite_id：`rrh-final-independent-v2-current-lock-fresh-20260908`
- suite status：`FAIL`
- suite hash：`2b6d6f6f489285780cadd0a0a07bb6ef3c9d413ba7744f14e5ba7ca1a9eadac6`
- 12 个 outcome `run_id` 全局唯一。
- 6 个确定性案例：完整执行 deterministic injection（适用时）→ Trace Integrity → Artifact Replay → Runtime Eval verify，全部 PASS。
- 6 个 LLM-required 案例：`normal-research`、`insufficient-evidence`、`analyst-skeptic-strong-conflict`、`risk-veto`、`high-concentration-portfolio`、`llm-overconfidence`，均因当前锁 runtime artifact 缺失而 FAIL。
- 旧 run-index 的首次尝试被 Runner 以 `REGRESSION_CANDIDATE_VERSION_MISMATCH` 拒绝，证明没有把旧锁当作 cache hit 使用。

### B4. 当前锁 A/B/C Ablation 证据缺失

本轮 Ablation Runner 确实重读并验证了历史 4 案例 × A/B/C 底层链，runner status 为 PASS、结论为 `NO_MEASURABLE_GAIN`。但其源证据绑定：

- `5d0e5faae763037c412665122a06db7d1dbf03a60a55092fd4da31c12f8c7f48`
- `ae13c85f3189025de2ea9dcdd3156b3d25c15544802950f9a86e95cf4ad1edb4`

均不等于当前唯一锁 `618f...`。底层审计因此明确记录 `current_lock_equivalent=false`。历史结果可验证 Runner 行为和“无可测增益”的诚实报告，但不能充当当前候选锁的晋升证据。

### B5. Promotion Gate FAIL

- gate_id：`rrh-final-independent-v2-gate-20260908`
- status：`FAIL`
- result hash：`47729fb2d64595bfe1a145e5926ece55df7053b939c779c76045d716c61f80de`
- reason codes：
  - `PROMOTION_HARD_GATE_FAILED:mandatory_no_trade`
  - `PROMOTION_HARD_GATE_FAILED:runtime_regression`
  - `PROMOTION_HARD_GATE_FAILED:version_completeness`
- 版本绑定重读发现 candidate 证据仍出现上述两个旧锁，而不是当前锁。
- baseline `0.2.1-candidate.1` manifest 缺少非空 assurance，且无 baseline Runtime Eval/Ablation，不能补写或伪造。
- 安全负例把一个真实 assertion failure 输入 Gate 后，Gate 额外产生 `PROMOTION_HARD_GATE_FAILED:deterministic_tests`，证明不信任上游 PASS 摘要。

### B6. 缺少当前候选的人工批准记录

未找到满足当前 candidate/version lock、`approved_by`、`decided_at` 和 rollback 条件的 PromotionRecord。`evals/reports/candidate-0.1.0.json` 的历史状态字符串不是本候选的合法人工批准记录。自动 Gate 即使未来 PASS，也不得自动修改生产 Skill、Agent、manifest 或版本指针。

## 4. 已通过或非阻断验证

### 4.1 OpenSpec 与全量确定性测试

- `openspec validate runtime-replay-and-eval-hardening --strict`：PASS，exit `0`。
- 全量测试：277 tests，0 assertion failures，0 test errors，0 environment errors，PASS。
- test event ID：`test-event-8c6ec9c1-a159-4b25-8f92-45141a8e32ac`。
- test result hash：`5375e3d3411e60d572c8c7a62c6a70a7fa2902991fceb9987210d447c0458fa0`。
- 独立 TMPDIR：`/private/tmp/stock-agent-final-independent-v2-20260908/full-suite`。

这些结果证明实现层确定性契约、架构扫描和 fail-closed 单测有效，但不能替代当前锁真实 Council 终态和真实 Runtime Eval。

### 4.2 19 类 typed invariant 与 canonical registry/schema

canonical registry 与 checked-in schema 完全一致，共 19 类：

`TERMINAL_STATE_IN`、`AGENTS_INCLUDE`、`AGENTS_EXCLUDE`、`RISK_NOT_BYPASSED`、`EXPECT_RISK_PASS`、`EXPECT_RISK_VETO`、`EXPECT_NO_TRADE`、`NO_FUTURE_EVIDENCE`、`EVIDENCE_CLOSURE`、`TRACE_COMPLETE`、`SPECIALIST_OUTPUT_VALID`、`CIO_CONFLICT_HANDLED`、`EXPECT_FAILED_STAGE`、`EVIDENCE_SUBSET_OF_GATE`、`SEMANTIC_DIMENSIONS_APPLICABLE`、`EXPECT_VALIDATION_REJECTION`、`LLM_CALLS_EQUAL`、`VALID_ACTION_SET`、`FORBIDDEN_ACTION`。

全量测试及 4 项聚焦测试证明每一类都有正/负求值覆盖；未知类型和拼写错误类型均 fail-closed；12-case set 的类型与 provenance 受 schema/registry 约束。

### 4.3 future Evidence 是真实 pre-Gate injection

- case：`future-information-leakage`
- run_id：`regression-rrh-final-independent-v2-current-lock-fresh-20260908-future-information-leakage-0c1ee5e5f05d`
- producer：`regression-fixture-injector`
- type：`FUTURE_EVIDENCE`
- mechanism：`append_declared_evidence_before_pit_gate`
- version：`future-evidence-injection/1.0.0`
- cutoff：`2026-01-31T23:59:59Z`
- IDs：`ev-future-asof`、`ev-future-retrieval`
- Gate allowed evidence IDs：空集合。
- `ev-future-asof`：原始时间 `2026-02-01T21:00:00Z` / retrieved `2026-02-01T21:05:00Z`，被标记 `FUTURE_AS_OF`、`FUTURE_RETRIEVAL`。
- `ev-future-retrieval`：as_of `2025-12-31T00:00:00Z`、published `2026-02-02T12:55:00Z`、retrieved `2026-02-02T13:00:00Z`，被标记 `FUTURE_RETRIEVAL`。
- Eval 从 Trace/Gate 重算：`injection_verified=true`、`leak_count=0`、PASS。
- 实际操作链：`deterministic_injection`、`trace_integrity_report`、`artifact_replay`、`runtime_eval_verify`。

这不是事后篡改 Eval 摘要；注入发生在 PIT Gate 之前，原始时点、cutoff、producer、mechanism、version 和 evidence IDs 均在 Trace/产物中留痕。

### 4.4 Calibration

- calibration_id：`portfolio-council-semantic-calibration/1.0.0`
- status：PASS
- observations：30
- agreement：`1.0`，threshold：`0.8`
- 独立 dev_eval sessions：`01a07c36-2f13-7492-a0ca-9a540320547f`、`01a07c3a-de28-75e2-bc08-dbc6727f7a95`
- result hash：`833076bc17d413e266ab4a8ccb8cb964aedf8f3e5a7dd46e02cda37ed7577242`

### 4.5 只读运行时、硬 Risk Engine 与学习边界

底层审计 `audit/bottom-up-audit.json` 结论：

- Runtime tool `AccessMode` 只有 `read`；全部 tool contracts 为只读。
- fixture MCP 仅启用 `query`、`calculate`；annotations 为 `readOnlyHint=true`、`destructiveHint=false`、`openWorldHint=false`。
- Runtime Agent 只持有 fixture evidence query / deterministic math calculate；没有 filesystem-write、investment-decision、broker-write 或 production-promotion 权限。
- Risk Engine 规则基础仅为 `accounting_identity`、`mathematical_definition`、`data_quality`、`explicit_mandate`。
- Risk metric allowlist 仅为 `amount_conservation`、`price_age`、`position_weight`、`sector_weight`、`cash_weight`、`turnover`、`adv_participation`、`long_only`、`leverage`。
- Risk REJECTED 映射为 `NO_TRADE` + `RISK_VETO`；不存在用主观投资评分代替明确硬约束的规则面。
- `ImprovementProposal` 只能产出提案；promotion policy 明确 `automatic_production_mutation=false`。
- Promotion Gate 只写指定输出目录，不修改生产系统；人工批准边界仍生效。

## 5. 实际命令、ID、输入输出与阶段映射

每条命令的完整 argv、开始/结束时间、exit code、stdout/stderr 路径均保存在 `commands/*.event.json`。以下为本轮实际命令，不包含仅阅读文件的命令。

| 阶段 | 实际命令（参数略去共同绝对前缀时仍由 event 保存完整值） | 结果与主要产物 | Specs / Tasks 映射 |
|---|---|---|---|
| OpenSpec | `openspec validate runtime-replay-and-eval-hardening --strict` | PASS；`commands/01-*` | Tasks 10.2、11.10 |
| 全量测试 | `python3 -m product.runtime.cli test-evidence --repo ... --output-dir .../test-evidence/full-suite --tmpdir /private/tmp/.../full-suite` | PASS，277；`test-evidence/full-suite/result.json` | Tasks 1.x、10.1、10.2、10.5 |
| Run prepare | `python3 -m product.runtime.cli prepare --fixture evals/fixtures/codex-native/normal-research.json --run-dir .../runs/source-normal --run-id rrh-final-independent-v2-source-normal-20260908 --model gpt-5.6-terra ...` | DISPATCH_REQUIRED；当前锁 Replay Capsule | Council spec；Tasks 2.x、3.x、11.1–11.2 |
| Smoke prompt | `python3 -m product.runtime.cli smoke-prompt --repo ... --run-dir .../runs/source-normal` | prompt/event 已保存 | Tasks 9.3、11.2 |
| 初次 Codex | `codex exec --ephemeral --ignore-user-config --strict-config --json -s read-only -m gpt-5.6-terra -` | exit 1；state DB read-only 环境错误 | Tasks 11.2 |
| 授权 Codex | `codex exec --ephemeral --ignore-user-config --strict-config --json -s workspace-write --add-dir .../runs/source-normal -m gpt-5.6-terra -` | shell exit 0，但 agent message 报能力缺失；run 非终态 | Council spec；Tasks 4.3、11.2 |
| Run check | `python3 -m product.runtime.cli check-run --repo ... --run-dir .../runs/source-normal` | exit 3，`TRACE_TERMINAL_STATE_INVALID` | Trace spec；Tasks 3.2–3.4 |
| Artifact Replay | `python3 -m product.runtime.cli artifact-replay --repo ... --run-dir .../runs/source-normal --output .../replay/source-normal.json` | exit 6，非终态 fail-closed | Replay spec；Tasks 4.1、11.3 |
| Trace check | `python3 -m product.runtime.cli trace-check --run-dir .../runs/source-normal --output .../traces/source-normal.json` | exit 6 | Trace spec；Tasks 3.x |
| Execution Replay prepare | `python3 -m product.runtime.cli prepare-execution-replay --source-run-dir .../runs/source-normal --run-dir .../runs/execution-replay-normal --run-id rrh-final-independent-v2-execution-replay-normal-20260908 --workspace .../workspaces/execution-replay-normal` | exit 6；未 dispatch、未 finalize | Replay/Council specs；Tasks 4.2–4.6、11.4 |
| Runtime Eval prepare | `python3 -m product.runtime.cli eval-prepare --repo ... --run-dir .../runs/source-normal --eval-dir .../runtime-evals/source-normal --eval-id rrh-final-independent-v2-eval-source-normal-20260908` | exit 6；未评分 | Eval spec；Tasks 5.x、11.5 |
| 旧 run-index 检查 | `python3 -m product.runtime.cli regression ... --candidate-hash 618f... --run-index .../runtime-replay-and-eval-hardening-final-20260908/regression/run-index.json` | exit 6；旧锁不匹配，拒绝 | Regression spec；Tasks 6.6、6.8 |
| 当前 12-case Regression | `python3 -m product.runtime.cli regression ... --suite-id rrh-final-independent-v2-current-lock-fresh-20260908 --candidate-hash 618f... --run-index .../current-lock-run-index.json` | FAIL，6/12；`regression/suite-fresh/result.json` | Tasks 6.1–6.8、11.6 |
| Calibration | `python3 -m product.runtime.cli eval-calibration --labels evals/grading/calibration/v1/labels.json --grader-index .../calibration/index.json --output-dir .../calibration/result` | PASS | Controlled learning spec；Tasks 5.5、5.8 |
| Ablation | `python3 -m product.runtime.cli ablation --repo ... --output-dir .../ablation/result --ablation-id rrh-final-independent-v2-ablation-20260908 --variants .../variants-hardening-final.json` | Runner PASS、历史 `NO_MEASURABLE_GAIN`，当前锁不等价 | Ablation specs；Tasks 7.x、11.7 |
| Promotion | `python3 -m product.runtime.cli promotion --repo ... --input-manifest .../promotion/input.json --output-dir .../promotion/result` | FAIL；gate `rrh-final-independent-v2-gate-20260908` | Controlled learning spec；Tasks 8.x、11.8 |
| assertion 负例 | `python3 -m product.runtime.cli test-evidence ... --test-target evals.promotion.assertion_failure_fixture.IntentionalPromotionAssertionFailure.test_intentional_assertion_failure` | 1 个真实 assertion failure | Tasks 8.8、11.8 |
| Promotion 负例 | `python3 -m product.runtime.cli promotion ... --input-manifest .../promotion/input-negative-assertion.json --output-dir .../promotion/negative-assertion` | FAIL，额外拒绝 deterministic tests | Tasks 8.2、8.8、11.8 |
| invariant 聚焦 | `python3 -m unittest` 加 4 个 `tests.test_runtime_regression.RuntimeRegressionTests` 目标 | PASS，4/4 | Tasks 6.1–6.4、6.8 |
| 底层审计 | `python3 .../_bottom_up_audit.py` | 最终 `22c` exit 0；`audit/bottom-up-audit.json` | Tasks 1.4、3.x、6.8、8.8、11.9 |
| after 证明 | `python3 .../_capture_source_proof.py after` | exit 0 | 只读约束；Tasks 4.1、5.1、8.5 |
| 逐字节比较 | `python3 .../_compare_source_proof.py` | exit 0，`all_protected_source_bytes_equal=true` | 同上 |

一次额外的受限复制环境 Codex 尝试在无进展后被终止，`commands/20-source-codex-exec-restricted-copy.event.json` 记录 `exit_code=130`、`TIMEOUT_NO_PROGRESS`；它没有被计为成功或替代用户授权的 `05b` 事件。

## 6. Promotion 对底层证据的重读结果

Promotion 输入故意保留了可定位的旧 Execution Replay / Runtime Eval / Ablation 引用，以验证 Gate 是否会被上游 PASS 字段欺骗。Gate 没有信任摘要，而是发现：

- Regression 的 `normal-research` 缺少当前 runtime execution；
- candidate evidence lock 集合仅含 `5d0...` 与 `ae13...`，和当前 `618f...` 不一致；
- baseline manifest 缺少 assurance，baseline runtime evals 为 0，baseline ablation 缺失；
- mandatory NO_TRADE 所需当前完整链未满足；
- 注入 assertion failure 后 deterministic test hard gate 立即 FAIL。

这证明 Promotion 的底层重读/fail-closed 机制有效，但当前候选证据本身仍不足，所以只能得到 FAIL。

## 7. 源树未修改证明

验收目录被明确排除在受保护源树集合之外；除此目录外，对源树做了开始/结束快照并逐字节比较。

- before HEAD：`1e565bbb534df473d92cf46ac330f33395a0c005`
- after HEAD：`1e565bbb534df473d92cf46ac330f33395a0c005`
- before/after branch：`main`
- before/after protected tree hash：`5e06930f7c8a572fc31ff89146d1c613c6c8ba2a023598dcc1762e979b36b282`
- before/after manifest entries：`11118`
- `head.txt_byte_equal=true`
- `branch.txt_byte_equal=true`
- `git-status-porcelain-v1.txt_byte_equal=true`
- `git-diff-unstaged.patch_byte_equal=true`
- `git-diff-staged.patch_byte_equal=true`
- `untracked-files.protected.txt_byte_equal=true`
- `source-tree-manifest.tsv_byte_equal=true`
- `source-tree.sha256_byte_equal=true`
- `all_protected_source_bytes_equal=true`

证据：`source-tree-proof/before/`、`source-tree-proof/after/`、`source-tree-proof/comparison.txt`。本轮未修改源代码、配置、fixture、OpenSpec、Tasks 或 Git；未归档、未同步主规格、未提交、未推送。Task 11.10 仍为 `[ ]`。

## 8. 最终判定矩阵

| Gate | 判定 | 发布影响 |
|---|---|---|
| OpenSpec strict validate | PASS | 非阻断 |
| 全量确定性测试 | PASS | 非阻断 |
| 19 typed invariant/schema/unknown fail-closed | PASS | 非阻断 |
| 当前锁 Run/Seal | FAIL | **阻断** |
| 当前锁 Artifact Replay | FAIL（源非终态） | **阻断** |
| 当前锁真实 Execution Replay + Finalizer | 未产生 | **阻断** |
| 当前锁 Runtime Eval | 未产生 | **阻断** |
| 当前 typed 1.1.0 12-case Regression | FAIL，6/12 | **阻断** |
| Future Evidence pre-Gate injection | PASS | 非阻断 |
| Calibration | PASS | 非阻断 |
| 当前锁 A/B/C Ablation | 缺失 | **阻断** |
| 历史 A/B/C 底层重验 | PASS，但锁不等价 | 仅诊断，不可晋升 |
| Promotion Gate | FAIL | **阻断** |
| Promotion assertion 负例 | 预期 FAIL | 非阻断，证明 fail-closed |
| Runtime tools / Risk / learning boundary | PASS | 非阻断 |
| 当前人工批准记录 | 缺失 | **阻断** |
| 源树逐字节未修改 | PASS | 非阻断 |

## 9. 最终输出

**FAIL — NOT_PROMOTABLE_BUT_CHANGE_VALIDATED。**

候选实现的确定性验证与安全边界有效，但当前唯一 candidate lock 下缺少完整真实 Run、Replay、Runtime Eval、12/12 Regression、A/B/C 和人工批准闭环。不得晋升、归档、提交或推送。
