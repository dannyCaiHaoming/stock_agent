## 1. 建立 canonical decision contract

- [x] 1.1 在 `product/contracts/` 增加版本化、机器可读的 Council decision contract，声明动作分组、字段条件、稳定规则码以及合法/非法 `NO_TRADE` 示例；通过契约结构测试确认 `target_weight_range: null`、`maximum_notional: null` 和“数值 0 非法”均被明确表达。
- [x] 1.2 实现只负责加载、规范化、哈希和解释结构规则的 deterministic contract loader/compiler，并验证它不包含 Thesis、Action 选择、Confidence 或其他投资判断规则。
- [x] 1.3 将 canonical contract 的版本和哈希纳入产品 discovery、Invocation Manifest、version lock 与受保护运行时完整性快照；通过篡改或漂移测试证明缺失、版本不一致和 hash 不一致都会在真实运行前 fail closed。

## 2. 统一 CIO Schema、Prompt 与 Validator

- [x] 2.1 由 canonical contract 生成并提交新版 CIO JSON Schema 动作条件分支，保留生成来源版本/hash；通过 Schema 契约测试证明合法 `NO_TRADE` 的两个执行字段均为 `null`，`maximum_notional: 0` 和非空 `target_weight_range` 不符合 Schema。
- [x] 2.2 从同一 canonical contract 渲染 CIO 可见的条件规则和合法/非法 JSON 示例，并接入实际 `runtime_cio` task prompt；通过 Prompt 测试确认示例包含“0 不等于 JSON null”，且 Prompt 未另行手写一套动作规则。
- [x] 2.3 将 CIO 运行时动作字段校验切换为 canonical contract interpreter，同时保留 Evidence Closure、身份、Skill execution proof、报告 hash 和 `advisory_only` 等既有校验；通过回归测试证明 fail-closed 边界没有降低。
- [x] 2.4 增加 CIO 条件契约测试矩阵：合法 `NO_TRADE` null/null 通过，非法 `maximum_notional: 0` 拒绝，非法非空 `target_weight_range` 拒绝，普通动作继续遵守既有字段约束；验证 Schema 与 Validator 使用相同稳定规则语义。
- [x] 2.5 增加派生产物一致性检查，重新生成 CIO Schema 和 Prompt 片段后与仓库产物比较；通过故意修改任一派生物的测试证明漂移会阻止候选运行。

## 3. 引入失败阶段与阶段感知 Trace

- [x] 3.1 定义并版本化 `failed_stage` 枚举和有序阶段矩阵，升级 Decision Trace 与 Run Error Schema；通过 Schema 测试确认 `FAILED_VALIDATION` 必须有阶段、发布终态阶段为 `null`，且 Trace、Run Error、失败事件必须一致。
- [x] 3.2 重构集中失败入口，使每条 `FAILED_VALIDATION` 路径显式传入实际失败阶段，并在不生成 `decision.json`/`report.md` 的前提下保存 `run_error.json` 与可审计 Trace；通过覆盖各调用点的测试确认没有默认或猜测阶段。
- [x] 3.3 在调用 Risk Engine 前写入带 policy version、草案输入 hash 和 `STARTED` 状态的 Risk lineage，并在成功、修改、否决或异常后补全结果；通过异常注入测试证明进入 Risk 后即使失败也留下完整 lineage。
- [x] 3.4 将 Trace Validator 改为按终态、失败阶段、阶段事件、Agent 产物和 Risk 文件交叉校验；通过测试证明 Risk 前失败允许空 `risk_lineage`，Risk 中/后失败缺少 lineage 必须拒绝，发布链路仍不得绕过 Risk。
- [x] 3.5 将 artifact matrix 改为按失败阶段计算 required/allowed/forbidden 产物；通过参数化测试覆盖九个阶段、发布终态、Run Error 不一致和失败状态意外存在发布产物。
- [x] 3.6 为已归档 2.0.0 运行包建立显式版本拒绝或旧版只读识别测试，证明旧产物不会被静默当作新版候选通过，也不会被迁移过程改写。

## 4. 支持 FAILED_VALIDATION 诊断 Replay

- [x] 4.1 在现有 deterministic artifact replay 中增加 `FAILED_VALIDATION` 诊断分支，按 `failed_stage` 验证已有输入、产物、hash、错误与 lineage，并跳过失败点之后的产物；通过 Risk 前 CIO 条件失败 fixture 证明 Replay 不再误报 `TRACE_RISK_LINEAGE_MISSING`。
- [x] 4.2 对可确定性复验的失败执行相同 Gate、Schema、Evidence 或 Risk 校验并核对错误类别；通过测试确认 Replay 只诊断、不调用 LLM、不修改源 run 目录且不生成建议产物。
- [x] 4.3 增加失败 Replay 反例测试，覆盖阶段前必需产物缺失、阶段后越界产物存在、错误码/阶段不一致、Risk 后 lineage 缺失和 artifact hash 被篡改。

## 5. 增加独立 Release Gate 状态判定

- [x] 5.1 实现只读 `check-run --repo ... --run-dir ...`（或等价）CLI，聚合终态、Run Error、Trace、artifact matrix、Evidence/Risk 不变量和实际 Eval；通过命令测试确认输出稳定的机器可读 `PASSED`/`FAILED` 结果。
- [x] 5.2 实现并测试退出码：完整 `COMPLETED`/`SAFE_NO_TRADE` 为 0，合法 `FAILED_VALIDATION` 为 2，非终态或损坏运行包为 3，发布运行 Eval 缺失/失败为 4；特别验证外层 Codex 状态为 0 时内部 `FAILED_VALIDATION` 仍返回非零。
- [x] 5.3 更新 `portfolio-council` Skill 和可复制 Smoke 操作说明，使每次 Codex-native 运行后独立调用 `check-run`，并记录 Codex 进程状态与 Council Release Gate 状态；通过文档/Prompt 测试确认不再宣称只靠 `codex exec` 状态即可通过。

## 6. 修复只读计算工具参数契约

- [x] 6.1 将必需的非空 `calculation_id` 同步到 `fixture_math.calculate` 的 MCP `inputSchema`、绑定 callable、无状态代理、结果和审计事件，并更新 Company Analyst 可见工具调用说明；通过一次合法调用证明无需 LLM 重试即可执行且 ID 端到端一致。
- [x] 6.2 增加工具参数契约测试，比较 manifest 的 required/properties/additionalProperties 与实际 handler/代理/事件映射，覆盖缺失 `calculation_id`、错误类型、未知额外参数和未经授权工具；所有非法请求必须在计算前确定性拒绝。
- [x] 6.3 回归验证计算仍只访问本次 Gate 允许的两个数值事实，保持只读审计且不改变 Evidence、投资判断或工具授权边界。
- [x] 6.4 为两个 Specialist 确定性生成 Gate-scoped 输出 Schema，将全部 Evidence 引用字段约束为 `allowed_evidence_ids` enum；Invocation Manifest 锁定并复验 Schema，动态 Prompt 明确只允许原始 ID 且禁止拼接来源、时间或说明文字，Evidence Closure Validator 保持严格不变且不得静默截断。
- [x] 6.5 增加 Specialist Evidence ID 契约矩阵测试：单个正确 ID 与多个合法 ID 通过，拼接 source、拼接时间和不存在 ID 均 fail closed；验证实际 prepare 产物包含独立 `allowed_evidence_ids`、run-scoped enum Schema 和明确 Prompt。

## 7. 确定性测试与架构回归

- [x] 7.1 运行与 canonical contract、CIO 校验、Trace、artifact matrix、Replay、Release Gate 和 MCP 参数相关的聚焦单元/集成测试，并保存零失败结果。
- [x] 7.2 运行完整测试套件，确认既有 point-in-time、Evidence Closure、双 Agent 独立性、Risk veto、报告一致性、架构 guard 和无真实交易能力测试全部通过。
- [x] 7.3 运行架构扫描与评审，确认没有新增 Python LLM 编排后端、callback、多 Agent 模拟、硬编码 Thesis/Action/Confidence、大型投资 if/else、外部 Provider 或写入交易工具。
- [x] 7.4 运行 `openspec validate harden-council-terminal-contracts --strict` 并修复全部规划/实现一致性错误后，才允许开始真实 Codex Smoke。

## 8. 真实 Codex 四 fixture 与稳定性验收

- [x] 8.1 锁定候选版本、显式模型、Codex runtime、Skill/Agent/Schema/contract/MCP/Risk/Data hashes，准备六个全新输出目录并保存运行前产品完整性快照；验证冲突三次运行期间不会修改产品文件。
- [x] 8.2 通过真实 Codex-native `portfolio-council` 入口运行正常研究 fixture，执行实际 Eval 和 `check-run`；验证完整双 Agent→CIO→Risk 链路、三项发布产物、Evidence Closure 和零 Release Gate 状态。
- [x] 8.3 通过真实 Codex-native 入口运行未来/过期证据 fixture，执行实际 Eval 和 `check-run`；验证 point-in-time Gate 在专业 Agent 前安全终止、合法 `SAFE_NO_TRADE`、三项发布产物和零 Release Gate 状态。
- [x] 8.4 通过真实 Codex-native 入口运行 Risk veto fixture，执行实际 Eval 和 `check-run`；验证真实 CIO draft 经过 Risk Engine、确定性 boundary draft 被稳定否决、最终建议未覆盖 veto 且 Release Gate 为零。
- [x] 8.5 通过真实 Codex-native 入口连续运行 Evidence 冲突 fixture 三次，每次使用唯一 `run_id` 和全新目录，并分别执行实际 Eval 与 `check-run`；验证三次均生成 `decision.json`、`report.md`、`decision_trace.json`，无悬空 Evidence、无非法 NO_TRADE、无 Risk 绕过且 Release Gate 为零。
- [x] 8.6 汇总六次真实运行的实际命令、Codex 进程退出状态、Council Gate 退出状态、run ID、模型、产物路径和 Eval 结果；逐项对照规格确认没有以固定 Thesis、Action、Confidence 或 fake adapter 代替真实验收。

## 9. Release Review

- [x] 9.1 对照 proposal、四份 delta spec、design 和 tasks 进行只读 Release Gate，检查所有任务均有实际实现与可核验证据，不得仅因勾选而判定完成。
- [x] 9.2 确认所有测试、六次真实 Smoke、三次冲突稳定性、`check-run` 状态和 OpenSpec strict validation 全部通过后，记录人工批准点；在批准前不得归档、提交或推送该 Change。
