## Context

参见 [proposal.md](./proposal.md) 的动机。本次设计建立在已归档的 Codex-native fixture Council 上：Codex 主线程担任 CIO，两个独立 runtime Agent 负责研究，Python 负责 point-in-time Gate、契约验证、Risk、产物和 Eval。当前问题不是缺少投资能力，而是同一结构规则散落在 CIO Schema、动态 Prompt 和 Python Validator 中，以及失败运行仍按完整成功链路要求 Risk lineage。

现有运行包已经区分 `COMPLETED`、`SAFE_NO_TRADE` 和 `FAILED_VALIDATION`，但 Trace 没有规范化 `failed_stage`；artifact replay 默认读取 `decision.json`；CLI 只根据当前子命令返回值推断退出状态。`fixture_math.calculate` 的 MCP Schema 与 callable 都不接受真实运行中模型使用过的 `calculation_id`，导致一次可预防的工具失败后依靠 LLM 重试恢复。

## Goals / Non-Goals

**Goals:**

- 让动作相关结构规则在 canonical contract、JSON Schema、CIO 指令和运行时校验之间可机械证明一致。
- 让成功、Risk 前失败、Risk 中/后失败都具有明确、可验证、可诊断的终态矩阵。
- 提供独立于 `codex exec` 退出码的 deterministic Release Gate。
- 让计算工具第一次调用即可按公开参数契约执行，并保留调用关联血缘。
- 用真实四 fixture 和连续三次冲突场景证明修复不是只在 fake adapter 中成立。

**Non-Goals:**

- 不增加真实行情 Provider、外部网络、券商、订单或账户能力。
- 不新增 Agent、Skill、动态路由或 Python LLM 编排后端。
- 不改变 LLM 与 Python 的职责边界，不把投资判断编码为规则。
- 不建设通用 Replay Executor；只扩展当前 deterministic artifact replay 对失败包的阶段感知诊断。
- 不以固定 Thesis、Action、Confidence 或自然语言逐字一致作为验收条件。

## Decisions

### 1. 使用版本化声明文件作为 canonical decision contract

在 `product/contracts/` 下增加一个仓库拥有、机器可读、版本化的 Council decision contract。它只描述可确定性验证的结构规则，不包含投资判断。最少包含：

- 契约版本和受约束的 CIO Schema 版本；
- 动作集合及动作分组；
- 每组动作的字段 `required`、`forbidden`、`const`、类型和最小基数约束；
- `NO_TRADE` 的合法示例，以及 `maximum_notional: 0`、非空 `target_weight_range` 的非法示例；
- 可用于错误归因的稳定规则码。

增加一个小型确定性 contract loader/compiler：

1. 从 canonical 文件生成 CIO JSON Schema 的动作条件片段；
2. 从同一文件渲染 CIO task prompt 的规则说明与合法/非法 JSON 示例；
3. 为运行时 Validator 提供同一组动作字段检查，而不是再次手写 `if action == ...` 规则；
4. 计算 canonical contract 哈希并纳入 discovery、Invocation Manifest、版本锁和受保护文件完整性快照。

生成后的 CIO Schema继续作为仓库内可审阅、可锁定哈希的静态产物提交，但带有生成来源版本与哈希。测试以重新生成后的规范化内容进行逐字节或 canonical JSON 对比；发生漂移即失败。CIO 动态 task prompt 直接调用同一 renderer，静态 Agent 指令只引用该契约及“必须遵守动态 task prompt”，不复制完整规则。

选择声明文件而不是把 Python Validator 或自然语言 Prompt 作为源，是因为 JSON 能同时稳定驱动 Schema、Prompt 和 Validator。选择保存生成后的 Schema，是因为 Codex Invocation 需要一个可审阅、可哈希的输出契约。未选择在运行时静默改写 Schema；运行过程仍不得修改产品文件。

本 Change 只修复并集中化既有动作结构意图。`NO_TRADE` 明确要求两个执行字段为 JSON `null`，其中数值 `0` 明确非法；其他动作的现有确定性约束原样迁入 canonical contract，并通过回归测试锁定，不借机添加主观交易规则。

### 2. JSON Schema 与 Validator 都直接执行动作条件

CIO JSON Schema 使用 Draft 2020-12 的 `if`/`then`/`else` 或等价 `oneOf` 分支表达动作条件。`NO_TRADE` 分支至少对以下内容进行 Schema 级约束：

- `target_weight_range` 的值为 `null`；
- `maximum_notional` 的值为 `null`；
- NO_TRADE 原因和说明为非空，重评条件至少一项；
- 与普通动作互斥的字段遵守 canonical contract。

运行时仍保留确定性 Validator，作为 JSON Schema 之后的第二道 fail-closed 边界，但动作条件由 contract interpreter 执行。两层返回共享稳定规则码，便于 `run_error.json`、Trace、Replay 和 Release Gate 自动归因。Schema 不替代 Evidence Closure、Agent 身份、Skill execution proof、报告哈希和 Risk 校验。

### 3. 为失败运行建立阶段枚举和阶段矩阵

引入有序、版本化的粗粒度 `failed_stage` 枚举，覆盖：

1. `PREFLIGHT`
2. `EVIDENCE_GATE`
3. `SPECIALIST_EXECUTION`
4. `SPECIALIST_VALIDATION`
5. `CIO_SYNTHESIS`
6. `EXECUTION_PROOF`
7. `CIO_VALIDATION`
8. `RISK_ENGINE`
9. `PUBLICATION_VALIDATION`

`failed_stage` 表示错误实际发生阶段，不表示最后成功阶段。所有进入 `FAILED_VALIDATION` 的路径必须显式传入该值；`run_error.json`、Decision Trace 的顶层字段和最终 `VALIDATION_FAILED` 事件必须一致。成功终态的 `failed_stage` 为 `null`。

阶段矩阵定义每个失败点之前必须存在、可以存在和禁止存在的产物与 lineage。例如：

- `PREFLIGHT`/`EVIDENCE_GATE` 失败不要求 Agent 或 Risk lineage；
- `SPECIALIST_*` 至 `CIO_VALIDATION` 失败按已经持久化的 Invocation 和 Agent 产物校验，允许 `risk_lineage` 为空；
- `RISK_ENGINE` 或 `PUBLICATION_VALIDATION` 失败必须存在 Risk lineage；
- 任意 `FAILED_VALIDATION` 都禁止 `decision.json` 与 `report.md`；
- 任意发布终态只要形成过 CIO draft，就必须有完整 Risk lineage。

为避免仅修改 `failed_stage` 就绕过 Risk 要求，Validator 还会交叉检查阶段事件、Risk 文件、Risk 输入/输出和 artifact hashes。进入 Risk 前先写入包含 policy version、草案 input hash 和 `STARTED` 状态的 lineage 项；成功时补全确定性结果、修改与否决，异常时补全结构化错误和 `FAILED` 状态。这样“已进入 Risk 但未产出成功结果”仍有可审计血缘。

Trace 和 Run Error Schema 升级到新的内部契约版本。旧 2.0.0 运行包保持不可变，不能在未识别版本的情况下作为新候选通过；本 Change 不批量迁移历史产物。

### 4. Artifact Replay 对失败包采用诊断分支

Replay 先读取 Trace 终态，再选择路径：

- 发布终态沿用现有 Evidence Gate、Agent/CIO、Risk、报告渲染和哈希重建；
- `FAILED_VALIDATION` 使用阶段矩阵校验 `run_error.json`、Trace 和截至失败点的产物，重新执行能够从已保存输入确定性复验的 Gate/Schema/Evidence/Risk 检查，并确认错误类别与记录一致；
- 失败阶段之后的产物不被要求，禁止的发布产物一旦存在则 Replay 失败。

诊断 Replay 成功表示“失败运行包可解释且自洽”，不表示原运行成功。Replay 结果同时输出 `source_terminal_state=FAILED_VALIDATION`、`failed_stage`、原错误码和诊断检查。它不调用 LLM、不补写源运行目录，也不生成 `decision.json` 或 `report.md`。

### 5. 增加独立的 `check-run` Release Gate

在现有确定性 CLI 命令面增加 `check-run --repo ... --run-dir ...`。该命令只读取文件并输出一个紧凑 JSON 判定：终态、失败阶段、运行错误、artifact matrix、Trace、Evidence Closure/Risk passage、Eval 状态及最终 `PASSED`/`FAILED`。

退出码约定为：

- `0`：`COMPLETED` 或 `SAFE_NO_TRADE`，且所有终态产物、Trace、Risk 要求和实际 Eval 均通过；
- `2`：结构合法但终态为 `FAILED_VALIDATION`；
- `3`：未知/非终态、产物缺失、Trace/矩阵不一致或其他运行包损坏；
- `4`：发布产物有效但 Eval 缺失或失败。

Smoke 操作说明在 Codex-native 运行结束后独立执行该命令，并记录两层状态：`codex exec` 进程状态仅表示 Codex 进程是否结束，`check-run` 状态才表示 Council 是否通过 Release Gate。这样不需要也不尝试改变 Codex CLI 自身的退出语义。

### 6. 将 calculation_id 纳入计算工具 canonical 参数面

`fixture_math.calculate` 的公开输入契约把 `calculation_id` 定义为调用方提供的必需非空字符串。MCP `inputSchema`、绑定工具方法、无状态代理、计算结果和 MCP 审计事件都接受并原样保留该字段。它只用于一次调用的关联和排错，不参与数值计算或投资结论。

参数契约测试从公开 tool manifest 构造合法与非法调用，验证 required/optional/additionalProperties、handler 接收能力、代理转发、结果映射和事件映射一致。未知额外参数继续 fail closed。选择支持并追踪 `calculation_id`，而不是只在 Prompt 中禁止模型传入，是因为真实工具调用已经表明该标识对模型和审计都自然有用，且 Schema 应准确表达可执行接口。

### 6.1 使用 run-scoped Schema 约束 Specialist Evidence ID

基础 Specialist Schema 保持产品所有；每次完成 Evidence Gate 后，运行时从该基础 Schema 与 `allowed_evidence_ids` 确定性生成 run-scoped Schema，把 Company Analyst 和 Skeptic 所有 `evidence_refs`、`counter_evidence_refs` 的 item 约束编译为同一允许集合的 `enum`。Invocation Manifest 锁定实际 Schema 的路径与哈希，验证时从 Agent 输入重新生成并比较，避免 Schema 与 Gate 漂移。

Specialist 动态 task prompt 同时逐字列出 `allowed_evidence_ids`，明确引用字段只能保存原始 ID，禁止拼接来源、时间、分隔符或说明文字。来源语义继续写入 statement、scope、uncertainties 或 data_gaps。现有 Evidence Closure Validator 不修改，也不把 `ev-id|source|as_of=...` 自动截断为 `ev-id`；非法值继续以 `FAILED_VALIDATION` 终止。

### 7. 验收采用确定性测试加真实 Codex 稳定性运行

实现阶段先运行聚焦测试，再运行全量单元/集成测试和严格 OpenSpec 校验。真实验收使用锁定模型、版本化 fixture 和全新目录执行六次 Codex-native Smoke：正常一次、未来/过期一次、Risk veto 一次、Evidence 冲突连续三次。每次运行后都独立执行 `check-run`；冲突三次之间不得修改产品文件。

验收记录保存命令、Codex 版本、模型、run ID、输出路径、两层退出状态和 Eval 结果。三次冲突运行必须各自满足发布产物完整、实际 Eval 通过、Evidence Closure 完整、双 Agent 独立、CIO 消费冲突并经过 Risk Engine。验收器不得要求三次生成相同的 Thesis、Action 或 Confidence。

## Risks / Trade-offs

- [生成后的 Schema 与 canonical contract 仍可能被手工同时修改] → 提供单向生成/校验命令，并在单元测试、完整测试和运行前 discovery 中比较 source hash 与生成结果。
- [阶段枚举过细会使失败路径难以维护] → 使用上述九个稳定边界阶段，不记录函数级步骤；所有失败通过一个集中入口写入阶段和错误。
- [阶段字段被错误填写可能掩盖 Risk 缺失] → 交叉验证阶段、事件、Risk 文件和 lineage，进入 Risk 时先持久化 `STARTED` 记录。
- [对 `calculation_id` 改为必需会使旧调用失效] → 同步 Agent task prompt、MCP Schema、handler 和测试，并通过真实正常/冲突 Smoke 验证首调成功；旧产物保持只读。
- [真实 LLM 输出具有随机性，三次冲突运行可能动作不同] → 只校验结构、证据、独立性、Risk passage 和 Eval 不变量，不固定投资结论；任一结构失败仍按要求阻断。
- [LLM 可能把 Evidence provenance 编码进引用字符串] → run-scoped enum Schema 与明确 Prompt 在生成侧限制原始 ID；严格 Closure 在消费侧继续 fail closed，不引入静默修复。
- [Release Gate 与 Eval 职责重叠] → `check-run` 只聚合并验证已有确定性结果，不重新进行投资质量判断；Eval 仍是质量检查的唯一生产者。

## Migration Plan

1. 先引入 canonical decision contract、loader/compiler 和一致性测试，不切换运行时。
2. 生成并审阅新版 CIO Schema 与 Prompt 片段，随后切换 Validator 和 Invocation/version lock。
3. 升级 Trace、Run Error、阶段矩阵和失败入口，补齐 Risk `STARTED`/完成/失败 lineage。
4. 扩展失败诊断 Replay 和 `check-run`，再更新 Smoke 操作说明。
5. 同步 `calculation_id` 工具契约并完成参数面测试。
6. 完成全量确定性验证和六次真实 Codex Smoke；只有全部通过才允许归档。

若迁移中出现回归，回滚整个候选版本到上一个已锁定的运行时版本；不得只回滚 Schema、Prompt、Validator、Trace 或 MCP 参数面的其中一项。旧运行包不重写、不补造 `failed_stage`，使用其原版本工具审计。
