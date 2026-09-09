# Runtime Replay、Eval 与 Promotion 运行手册

本文描述开发控制面的离线验证流程。所有输出仅用于研究建议验证；不得连接券商、修改账户或真实下单。

按当前任务读取所需章节，不要求每次执行完整手册。验收范围与证据复用见 [开发流程](../../docs/development/workflow.md)，权限及路径见 [开发环境](../../docs/development/environment.md)。以下模块命令从仓库根执行；产品子进程的工作目录由既有 launcher 固定，不能以 cwd 或配置存在宣称资源已经加载。

## 1. 运行与持久化

使用 `portfolio-council` Skill 创建全新的 Run 目录。Runtime 在 Agent 调用前完成 portfolio 校验和 PIT Evidence Gate，并生成 `replay_capsule/manifest.json` 与内容寻址对象。已有目录不会被覆盖。

Capsule 同时锁定研究问题、截止时点、模型、Codex/Python runtime、Profile、版本 manifest 和产品完整性 hash。

普通产品运行固定使用 Company Analyst、Independent Skeptic 与 CIO；`EVAL_ABLATION` 只能用于开发评估，不能作为产品建议发布。

按当前已批准范围，真实产品执行仅由宿主 Terminal 使用现有代理适配与统一 launcher，不额外创建项目沙箱。准备好的运行使用：

```text
bash <repository-root>/scripts/run-product-smoke.sh \
  --prepared-run <run-dir> <new-invocation-output-dir>
```

模型来自 prepare 写入的锁定 manifest。launcher 保存固定 prompt 文件、JSONL、stderr、环境和进程结果，调用现有 Hook 与完成判定；必须核对真实 Skill、Agent、MCP、Hook 事件与终态产物，不能只看 shell exit code。禁止恢复旧 `smoke-prompt | codex exec` 管道作为验收入口。

## 2. Artifact Replay

```text
python3 -m product.runtime.cli artifact-replay \
  --repo <repository-root> \
  --run-dir <source-run-dir> \
  --output <external-replay-result.json>
```

该命令只读验证历史运行包和 Replay Capsule，LLM 调用数必须为 0，输出必须位于源 Run 目录之外。缺失对象、hash 漂移或路径逃逸均 fail closed。

统一 Trace 报告可用以下命令生成，供 Promotion 证据图引用：

```text
python3 -m product.runtime.cli trace-check \
  --run-dir <run-dir> \
  --output <external-trace-integrity.json>
```

## 3. Execution Replay

先通过安装仓库的薄入口物化密封工作区并准备新的 Run（不是额外创建项目沙箱）：

```text
python3 <repository-root>/scripts/council-dev.py prepare-execution-replay \
  --source-run-dir <source-run-dir> \
  --run-dir <new-run-dir> \
  --run-id <new-run-id>
```

该薄入口在新 Run 保存 `host-replay-source.json`，供宿主 transport 校验来源 Capsule；直接使用底层 prepare 命令不会创建此绑定，不能用于随后宿主执行，也不得手工向旧 Run 补写。随后在宿主 Terminal 使用上述 --prepared-run 入口，既有转发器按 manifest 选择冻结 workspace，通过同一 nested-codex-smoke launcher 执行；不要手动传当前仓库的 --repo，不要使用当前工作树替换冻结资源或临时复制缺失文件。独立 Reviewer 只提出补跑缺口，不自动执行。完成后运行：

```text
python3 -m product.runtime.cli finalize-execution-replay \
  --source-run-dir <source-run-dir> \
  --run-dir <new-run-dir> \
  --output-dir <comparison-dir>
```

Execution Replay 要求 Portfolio、PIT Evidence、Agent、Skill、Prompt、Schema、Model 和 Risk Policy 等可观察配置一致，但不要求自然语言、合法动作、Confidence、token 或延迟逐字一致。

## 4. Runtime Eval

先创建外置 Eval Job：

```text
python3 -m product.runtime.cli eval-prepare \
  --repo <repository-root> \
  --run-dir <run-dir> \
  --eval-dir <new-eval-dir> \
  --eval-id <eval-id>
```

完整 Council 会生成 `grader-input.json` 和 `grader-prompt.txt`。由开发控制面的 `dev_eval` 使用 `runtime-eval-grading` Skill 输出结构化语义结果后执行：

```text
python3 -m product.runtime.cli eval-execution-proof \
  --repo <repository-root> --eval-dir <eval-dir> \
  --semantic-result <semantic-result.json> --sessions-root <codex-sessions-root>

python3 -m product.runtime.cli eval-finalize \
  --repo <repository-root> \
  --eval-dir <eval-dir> \
  --semantic-result <semantic-result.json>
```

权威产物为 `eval/result.json`，`eval/report.md` 由同一结果确定性渲染。带语义评分的真实 Eval 必须先通过 `eval-execution-proof`，静态 JSON 不能代替真实 `dev_eval` 会话。Eval 不回写源 Run。预期 `FAILED_VALIDATION` 案例可通过重复的 `--expected-terminal-state FAILED_VALIDATION` 进行诊断。

Rubric 校准使用人工标注的固定样本，并至少进行两次相互独立的 `dev_eval` 盲评。若同一维度的状态不一致或 grade 差值超过门槛，校准必须 FAIL；不得修改原始评分来追求通过。

## 5. Regression 与 Ablation

Regression Set 位于 `evals/regression/v1/`。需要 LLM 的案例必须在 run index 中引用真实 Terra Run 和外置 Eval；确定性反例不得调用 LLM。无变化时按 case、候选、模型、Profile、Evidence、Rubric 和 Grader hash 复用已验证缓存。

```text
python3 -m product.runtime.cli regression --repo <repository-root> \
  --output-dir <suite-dir> --suite-id <suite-id> \
  --candidate-hash <sha256> --run-index <run-index.json> \
  --cache-dir <verified-cache-dir>
```

缓存记录必须反向引用仍可验证的 Run、Eval 与来源 hash；命中时报告 `reused_from`。仅在人工明确要求重新调用模型时使用 `--force`。

Ablation 使用相同输入分别运行 `cio-only`、`analyst-cio` 和 `full-council`。三个 Variant 都必须经过同一 Risk Engine，并锁定相同的 Portfolio、PIT Evidence、Model、完整 version lock、Risk Policy 与 Rubric。缺少语义质量时结论为 `NOT_COMPARABLE`；缺少 token 或延迟时显示 `MISSING_TELEMETRY`，不得记为 0。

```text
python3 -m product.runtime.cli ablation --repo <repository-root> \
  --output-dir <ablation-dir> --ablation-id <id> \
  --variants <variants.json>
```

`variants.json` 可包含一个三 Profile 案例，也可使用 `{"cases": {...}}` 聚合版本化代表案例集。任一代表案例不可比较时，整体不得宣称有增益或无增益。

## 6. Promotion Gate

Promotion 输入必须是 hash-bound 证据图，引用确定性测试、Regression、Execution Replay、候选与基线 Runtime Eval、候选与基线 Ablation、Trace、模型政策、候选与基线版本。静态 candidate 摘要不能代替这些产物。

确定性测试证据必须由独立子进程实际生成，保存命令参数、独立且可写的 `TMPDIR`、起止时间、进程 ID、退出码、测试计数，以及 stdout/stderr 原文与哈希：

```text
python3 -m product.runtime.cli test-evidence --repo <repository-root> \
  --output-dir <test-evidence-dir> --tmpdir <empty-writable-tmpdir>
```

Promotion 不接受手工填写的 PASS 摘要作为测试证明。测试事件中的计数、退出码或 transcript 不一致时必须 fail closed。

```text
python3 -m product.runtime.cli promotion --repo <repository-root> \
  --input-manifest <promotion-input.json> \
  --output-dir <promotion-dir>
```

结果目录只会包含 `PASS` 或 `FAIL` 其中一个 sentinel，并同时生成 `result.json`、`report.md` 和 `input-manifest.json`。Evidence Closure、PIT、Risk bypass、Schema、Trace 和必须 NO_TRADE 案例是硬门禁。PASS 仍不修改生产版本，必须等待人工批准。

每次 Gate 必须使用新的 `gate_id`；重复检查相同证据时只要求硬门禁和 reason codes 保持一致，必须写入新的历史记录。候选 Eval/Ablation、基线 Eval/Ablation 必须分别从各自版本的 Runtime Trace 解析，路径或内容哈希复用会被视为自我比较并拒绝。

旧 baseline 若缺少当前 Assurance 字段，可以作为带 hash 的诊断输入，但 `version_completeness` 必须 FAIL；Gate 应输出可审计原因，而不是异常退出或静默借用候选版本资源。

## 7. 模型与消耗

- 普通开发：`gpt-5.6-sol`。
- Execution Replay、重复 Regression 与 Ablation：`gpt-5.6-terra`。
- `gpt-6-astra`：仅限记录在案的重大架构或 Eval 方法争议，并要求 dispute ID 与人工批准产物。

每次真实 LLM 执行从 Codex rollout 的 `token_count` 与时间戳生成最小化遥测，记录模型、输入/输出 token、可用的 cache token、延迟、调用数、触发原因和 cache provenance。原始 Prompt 与隐藏推理不会复制进证明。缺失遥测标记为 `MISSING_TELEMETRY`，不能当作零成本。
