## Context

见 [proposal.md](./proposal.md) 的动机。当前 Runtime 已具备以下基础：

- `run_manifest.json`、冻结 fixture、PIT Gate、Invocation Manifest、Decision Trace、Risk lineage 和终态产物；
- `replay_run()` 可只读复验 Artifact、Gate、Schema、Risk 和报告，但会从当前仓库解析 Agent/Skill/Schema，因此不等同于历史 Execution Replay；
- `prepare-rerun` 只在当前 discovery hash 与来源运行完全相同时准备新运行，尚不能在仓库演进后解析冻结资源；
- `native_eval` 能评估四类真实 fixture，但只输出 JSON、只接受发布终态，语义质量维度有限；
- `evals/ablation` 与 `evals/promotion` 当前接收人工构造的聚合值，不能作为真实 Runtime 晋升证据；
- 默认产品 Profile 固定为 Company Analyst 与 Independent Skeptic 并行、CIO 综合和 deterministic Risk Engine，不能为了 Ablation 放宽。

所有设计继续遵守三平面边界：Codex LLM 负责研究与语义判断，Python 负责冻结、确定性校验、数学/风控、运行准备、指标聚合和存储。不得引入调用模型 SDK 的独立 Python 编排后端。

## Goals / Non-Goals

**Goals:**

- 让新生成的 Runtime 运行包在工作区版本变化后仍能验证和重新执行其冻结上下文。
- 让 Artifact Replay、Execution Replay、Eval、Regression、Ablation 与 Promotion 共用一个 Trace 和版本可信根。
- 将安全硬门禁与 LLM 语义 Rubric 分离，既不把投资判断编码成规则引擎，也不允许平均分覆盖 Evidence/PIT/Risk 失败。
- 用固定、有限、可缓存的案例集完成真实 Runtime 验收，记录 token 与延迟并避免无意义重复调用。
- 允许评估如实得出多 Agent 无增益或候选不可晋升，而不把“必须 PASS”写入评估逻辑。

**Non-Goals:**

- 不保证 LLM 输出、动作、Confidence、token 或延迟逐字节一致。
- 不声称模型别名等同于冻结权重；只能验证可观察的模型标识和 Codex runtime。
- 不为没有 Replay Capsule 的旧运行猜测、回填或迁移执行环境。
- 不把 Ablation Profile 变成产品入口，不新增投资 Agent，不改变 canonical action 集合。
- 不接入真实数据、市场/行业/期权能力、Reflection、自修改或交易执行。

## Decisions

### 1. 以自包含、内容寻址的 Replay Capsule 作为 Execution Replay 可信根

新运行在 Agent 调用前创建 Capsule，终态后封存。建议结构：

```text
<run>/
  replay_capsule/
    manifest.json
    objects/<sha256>
  audit/fixture_snapshot.json
  evidence/gate.json
  ...
```

`manifest.json` 记录逻辑路径、对象 hash、字节数、媒体类型、角色和是否可执行，并包含：

- Portfolio/fixture、研究问题、截止时点和 Gate 完整输入输出；
- `product/AGENTS.md`、runtime profile、Agent TOML、Skill 文件及直接依赖、任务 Prompt、Schema 和 canonical contracts；
- deterministic Runtime 模块、MCP Adapter、Risk Policy 与版本清单；
- Model、Codex CLI、Python/runtime 兼容信息、产品完整性快照和可选 Git revision；
- Capsule Schema version、manifest hash 与根 hash。

执行时先把对象按 allowlist 物化到全新临时只读工作区；任何路径逃逸、符号链接、额外文件、hash 漂移或缺失均拒绝。Codex 与 deterministic Runtime 只从该工作区解析资源，不回退到当前仓库、全局同名 Skill 或插件缓存。敏感信息扫描在封存前执行，Capsule 禁止包含账户凭据、环境变量、完整隐藏系统指令或 Chain-of-Thought。

选择自包含对象而非只保存 Git commit，是因为未归档候选和本地 fixture 验收可能尚无可解析 commit；Git revision 仍作为额外来源证明。代价是运行包更大，但当前 fixture 规模可控，也避免历史分支被清理后失去重放能力。

### 2. Replay 分为 Artifact 与 Execution 两条不可混淆的命令

- `artifact-replay`：沿用并加固当前 deterministic replay；源目录只读，输出写入调用方指定的独立目录，LLM 调用数必须为零。
- `prepare-execution-replay`：验证来源 Trace 和 Capsule，在空目录创建新运行包、`replay_execution_manifest.json` 与 Codex-native task prompt。
- Codex 主线程按 `portfolio-council` 协议执行；完成后 `finalize-execution-replay` 验证新 Trace、Eval 和来源等价性并生成差异报告。

新运行拥有自己的 `run_id`，并记录 `source_run_id`、Capsule hash、来源终态和冻结配置 hash。比较分为：

物化后的 Capsule 工作区采用文件 `0444`、目录 `0555` 的密封策略，并在 Finalizer 阶段重新扫描文件集合、写权限和对象哈希。`configuration_equivalent` 不是上游可声明的输入，而是基于实际 Agent、Skill、Prompt/Instructions、Schema、Model/Codex runtime、Evidence/PIT Gate、Risk Policy、MCP Adapter 与 runtime profile 分类哈希全部一致后才产生的派生结论。

1. 必须相同：Portfolio、PIT Evidence、版本、Agent 拓扑、Prompt/Schema/Risk 和只读权限；
2. 必须满足：Schema、Evidence Closure、PIT、Risk、Trace 和适用 invariants；
3. 允许变化：自然语言、合法动作、Confidence、token 和延迟，并交给 Eval 解释。

不把 Python CLI 设计成模型 SDK 循环；它只准备、校验和封存。实际 LLM 调用继续由 Codex Skill/Subagents 完成。

### 3. 统一 Trace Integrity Validator，其他流程不得复制一套简化规则

在当前终态/失败阶段矩阵基础上建立单一 Validator API，并由 Artifact Replay、Execution Replay、Eval、Regression、Ablation、`check-run` 和 Promotion Gate 调用。Validator 分层验证：

1. Trace Schema 与 `run_id`/终态/失败阶段；
2. Run Manifest、Portfolio、Capsule、Gate 和 PIT；
3. 每个 Agent 的定义、Skill、Prompt、Schema、Model、输入输出和执行证明；
4. Evidence Closure 与 MCP 只读事件；
5. CIO 消费关系与 Risk lineage；
6. 终态 artifact matrix 和逐文件 hash。

Validator 接收显式 `runtime_profile`，按默认 Council、pre-Agent termination、各失败阶段、Execution Replay 和 `EVAL_ABLATION` 应用不同矩阵。Profile 决定“哪些阶段应该存在”，但不能关闭 Evidence/PIT/Schema/Risk 等适用硬门禁。

选择扩展现有 Validator，而不是另建 Regression Validator 和 Promotion Validator，可避免当前 `native_eval`、`replay`、`release_gate` 各自逐步产生规则漂移。

### 4. Eval Job 是运行包之后的派生产物，不反向改写源 Trace

Eval 使用独立、不可覆盖的 Eval Job 目录：

```text
evals/results/<eval_id>/
  eval/result.json
  eval/report.md
  deterministic.json
  semantic-rubric.json
  input-manifest.json
```

`input-manifest.json` 引用源 run ID、Trace hash、Artifact Replay hash、Regression case（如适用）、Rubric/Grader 版本和全部输入 hash。这样完整运行和预期 `FAILED_VALIDATION` 均可被评估，同时避免 Eval 结果写回 Trace 造成循环 hash 或改变历史包。

为兼容当前 `run/eval/result.json`，迁移期可以读取旧格式，但 Promotion Gate 只接受新版 Eval Job；不自动重写旧运行。

`eval/result.json` 为权威机器结果，`eval/report.md` 由它确定性渲染。任何报告新增分数、结论或 reason code 都会失败。

### 5. Eval 采用 Hard Gates + Semantic Rubric 两阶段

确定性层计算并输出稳定 reason codes：

- Schema、artifact matrix 和 hash；
- Evidence 引用总数、有效数与正确率；
- Gate 外引用、`as_of`/`retrieved_at` 超过 cutoff 的泄漏数；
- Trace 完整性和 profile/终态矩阵；
- 形成 CIO 草案后的 Risk passage、修改和 veto；
- 必须 NO_TRADE 或 fail-closed 案例的结构约束。

这些项任何一项失败，Eval 总状态立即为 `FAIL`，但仍可运行只读诊断。

语义层复用现有开发控制面的 `dev_eval` Agent，不新增投资 Agent。它读取经过最小化、已验证的 Evidence、Agent 报告、CIO 决策和 case invariants，按版本化 Rubric 返回结构化结果：

- Analyst Thesis 是否由所引 Evidence 支持；
- Skeptic 是否提出具体、独立、可证伪的反证或缺口；
- CIO 是否明确处理共识与冲突；
- NO_TRADE 原因、说明和重评条件是否与证据状态一致；
- Confidence 是否与证据充分度、冲突和不确定性方向一致。

Rubric 每项使用 `PASS/FAIL/NOT_APPLICABLE`、离散等级和证据引用，不要求隐藏推理。模型、Prompt、Schema 和输出 hash 均保存。先在少量人工标注样本上验证 Grader 一致性；无法达到预设一致性时，语义结果标记不可靠并阻止 Promotion，而不是退化为 Python 投资规则。

### 6. Regression Set 使用 typed expected_invariants，不使用固定投资答案

目录建议：

```text
evals/regression/v1/
  manifest.json
  cases/*.json
  schemas/*.schema.json
```

十二个 case ID 固定覆盖：

1. `normal-research`
2. `insufficient-evidence`
3. `all-evidence-stale`
4. `future-information-leakage`
5. `analyst-skeptic-strong-conflict`
6. `dangling-evidence-reference`
7. `risk-veto`
8. `high-concentration-portfolio`
9. `llm-overconfidence`
10. `mandatory-no-trade`
11. `valid-action-contract`
12. `invalid-specialist-output`

Invariant 类型包括 `terminal_state_in`、`must_run_agents`、`must_not_run_agents`、`must_pass_risk`、`must_veto`、`must_no_trade`、`must_fail_stage`、`evidence_subset_of_gate`、`future_leak_count_equals`、`required_semantic_dimensions` 和条件动作 Schema。`valid-action-contract` 使用明确标记为 deterministic contract fixture 的 BUY/HOLD/TRIM/EXIT 草案验证结构与 Risk，不把草案声明为 LLM 投资结论。

需要开放研究判断的案例由真实 Codex LLM 运行；悬空引用、非法 Specialist、PIT 篡改和动作 Schema 反例由确定性注入器生成，并在 Trace 中标记 producer 为 fixture。每个 suite 输出每例真实 run/eval 引用和 aggregate report，禁止只保存手工布尔值。

缓存键为：case hash、候选版本/受保护文件 hash、Model、Codex runtime、Profile、Evidence/Gate、Rubric 和 Grader hash。缓存命中前重新验证全部来源产物；缓存结果必须记录 `reused_from`。`--force` 只在人工明确要求时重跑。

### 7. Ablation 使用三个隔离 Eval Profile，共享同一冻结输入

定义版本化实验拓扑：

- A `cio-only`：现有 CIO 直接使用 Gate-scoped Evidence；
- B `analyst-cio`：现有 Company Analyst 先研究，CIO 消费一份验证报告；
- C `full-council`：当前 Company Analyst 与 Independent Skeptic 独立并行，CIO 消费两份报告。

每个拓扑都有专用实验输入/输出 Schema 和 Trace matrix。默认产品 Schema、Agent 列表和 Release Gate 不接受 A/B。三种 Variant 都必须使用相同 Portfolio hash、Gate hash、Model、Risk Policy、Rubric 和 case；每种形成 CIO 草案后都必须运行 Risk Engine。

首版从 Regression Set 选择四个具语义区分度的案例：正常、Evidence 不足、强冲突、必须 NO_TRADE。每组只运行一次有效样本，输入无变化时使用已验证缓存。比较输出逐案例维度、宏观分数、token、墙钟延迟、Schema/Risk 失败率和 `NO_MEASURABLE_GAIN`，不计算无法适用的反证维度为零分。

### 8. 模型路由是版本化策略而非散落在命令中的约定

增加开发/Eval 模型策略文件并纳入版本锁：

- `development_default = gpt-5.6-sol`
- `runtime_repeated = gpt-5.6-terra`
- `architecture_dispute = gpt-6-astra`，要求 dispute ID 与 human approval artifact

Regression case 可以声明 `llm_required=false`，此时任何模型调用都是错误。所有 LLM run 保存输入/输出 token、cache token（若可用）、模型和延迟；缺失成本遥测时不得默认为零，应标记 `MISSING_TELEMETRY` 并使成本比较不可用。

Regression Runner 对 12 个案例建立全局 `run_id` 唯一索引；每个案例无论来自新执行还是缓存，都必须由 Runner 当场依次执行 Trace Integrity、Artifact Replay 和 Runtime Eval 重验，并保存独立 execution proof 与 outcome artifact。缓存只减少 LLM 调用，不缓存验证责任。

### 9. Promotion Gate 使用证据图和分层政策，不读取人工结论字段

Promotion 输入 manifest 仅包含候选、已批准基线及以下产物的路径和 hash：

- deterministic test report；
- Regression suite result；
- 至少一个完整 Execution Replay pair；
- 每例 Runtime Eval；
- Ablation comparison；
- Trace Integrity summaries；
- 模型/成本预算与版本锁。

Gate 重新读取并验证底层产物，不信任摘要中的 `passed`。硬门禁包括 Evidence Closure、PIT leak=0、Risk bypass=0、适用 Schema/Trace 成功率=100%、必须 NO_TRADE 案例、预期失败阶段和版本完整性。软政策包括语义分项不低于基线的容忍区间、成本预算和 Ablation 结果。

Promotion 不采信测试、Regression、Replay、Eval、Calibration 或 Ablation 自报的 PASS。每类输入都通过对应 verifier 自底向上重算；确定性测试还要绑定显式可写 `TMPDIR`、原始测试事件、退出码、断言失败与环境错误。负向门禁直接篡改底层产物或原始测试事件，禁止仅翻转摘要布尔值。

语义校准的每次评分附带可重放 execution proof，绑定独立 `dev_eval` 子会话、父子 session ID、模型路由、Agent/Skill hash、Prompt/Input/Output hash、起止事件、评分产物和原始 rollout hash。同一案例的两个 repeat 不得复用 child session；同一 repeat 可由一个独立会话批量评分固定校准集，以避免无意义重复调用。Prompt 与输入 hash 必须由校验器重新读取绑定的原始文件计算，不接受调用方自报 hash；当 Codex 将子任务封装为受保护消息时，证明还必须同时绑定父任务原文、唯一 dispatch 与子会话输出。

本 Change 不改变默认 Agent 拓扑，因此 C 未显示可测增益会被如实报告，但只要没有安全退化、候选政策未要求拓扑增益，不自动导致 FAIL。未来增加或默认启用 Agent 时，预声明 Ablation 增益阈值成为硬条件。

输出结构：

```text
evals/promotions/<gate_id>/
  result.json
  report.md
  PASS | FAIL
  input-manifest.json
```

`PASS`/`FAIL` 是不可同时存在的零内容 sentinel，`result.json` 才是权威内容。Gate 不修改 `product/version-manifest.json`、插件、Agent、Skill 或 Risk Policy；人工批准后才由既有开发控制面生成 Promotion Record。

### 10. 完成验收采用一条真实纵向链路和有界批量运行

实现完成后必须实际执行：

```text
新真实 Run（含 Capsule）
→ Persist/Seal
→ Artifact Replay（0 LLM）
→ Execution Replay（Terra，新 run_id）
→ 两个运行的 Runtime Eval
→ 12-case Regression（仅标记案例调用 LLM）
→ 4-case × 3 Variant Ablation（可复用可信缓存）
→ Promotion Gate
```

验收要求保存命令、退出码、run/eval/gate IDs、模型、token、延迟、所有产物路径与 hash。Promotion 真实结果允许是 PASS 或带理由的 FAIL；Change 的实现正确性由 Gate 是否按声明政策、真实产物和硬门禁工作决定，不得为追求 PASS 修改评分或固定投资结论。

## Risks / Trade-offs

- [Capsule 复制受保护 Runtime 会增大运行包] → 使用内容寻址对象、逐对象大小上限和可选跨运行去重；验收先以小型 fixture 为边界。
- [执行冻结代码具有供应链风险] → 只允许仓库保护清单内文件，验证 hash/路径，使用无网络、最小权限、临时工作区执行；禁止从运行包加载未知依赖。
- [模型标识不等于冻结权重] → 报告只声称“可观察配置等价”；模型不可解析或标识变化时 fail closed，不声称 bit-for-bit execution reproduction。
- [同模型自评可能产生偏差] → Rubric 结构化、保存证据、与人工标签校准；重大方法争议才允许人工批准 Astra adjudication。
- [12-case Regression 和 Ablation 成本较高] → 确定性案例零 LLM、语义案例有限、内容 hash 缓存、无变化不重跑，并强制输出 token/延迟。
- [A/B Ablation 可能被误用为产品模式] → 独立 Profile、Schema 和 artifact namespace；默认 Release Gate 明确拒绝实验产物。
- [旧运行不具备 Capsule] → 保留 Artifact Replay，只对新版运行开放 Execution Replay，不静默回填。
- [软评分聚合掩盖关键失败] → 安全项先执行且不可被聚合覆盖；Promotion 保存稳定 reason codes 和逐案例证据。

## Migration Plan

1. 先增加 Schema、Replay Capsule builder/validator 和统一 Trace Validator，并保持现有 Artifact Replay、终态矩阵与 `check-run` 兼容。
2. 将新运行升级为 Capsule-aware 版本；旧版 2.1.0 运行保持只读 Artifact Replay，Execution Replay 返回明确的不支持原因。
3. 引入外置 Eval Job 和双层 Eval；旧 `native-eval/2.0.0` 可读取但不能单独作为新版 Promotion 证据。
4. 建立 12-case Regression Set、缓存索引和真实 Runner，再增加隔离 Ablation Profile。
5. 最后接入 Promotion Gate；现有 `evals/reports/candidate-0.1.0.json` 保留为历史记录，但不再能单独满足门禁。
6. 通过完整纵向验收和人工批准后再晋升版本；回滚时恢复上一版本清单和默认 Profile，新生成的 Replay/Eval/Promotion 记录保持不可变。

## Open Questions

- 首版 Capsule 是否跨运行做物理去重，可根据实现复杂度选择复制或硬链接；逻辑内容寻址、完整性和可移植行为不变。
- Codex 机器可读事件可提供的 token 分类字段可能随 CLI 版本变化；实现阶段可在不改变必需总 token、模型和延迟字段的前提下适配具体字段映射。
