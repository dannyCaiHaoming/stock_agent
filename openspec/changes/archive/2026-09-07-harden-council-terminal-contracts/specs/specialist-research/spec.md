## ADDED Requirements

### Requirement: 只读计算工具的参数契约必须端到端一致
`fixture_math.calculate` MUST 在其 MCP `inputSchema`、实际 callable、无状态代理、确定性计算结果和审计事件中使用同一版本化参数契约。该契约 SHALL 接受一个调用方提供的非空 `calculation_id` 作为计算关联标识，并要求其在结果及工具事件中原样保留；未声明参数、缺失必需参数或错误类型 MUST 在调用 LLM 恢复前由确定性契约校验拒绝。工具仍只能计算 Gate 允许的 fixture 数值事实，且不得增加开放网络、写入或投资判断能力。

#### Scenario: 使用受支持的 calculation_id 计算
- **WHEN** Company Analyst 按 MCP 暴露的 Schema 调用 `fixture_math.calculate`，并提供合法 `calculation_id`、身份、操作和两个允许的 Evidence IDs
- **THEN** 实际 callable 一次接受该请求，结果和只读审计事件均携带相同 `calculation_id`，无需依靠 LLM 修改参数后重试

#### Scenario: 工具清单与 callable 漂移
- **WHEN** MCP `inputSchema` 声明的必需或允许参数与实际 callable、无状态代理或事件映射不一致
- **THEN** 工具参数契约测试失败，候选版本不得进入真实 Codex Smoke

#### Scenario: 调用包含未声明参数
- **WHEN** 工具调用包含 canonical 参数契约未声明的额外字段
- **THEN** MCP 层在执行计算前确定性拒绝请求，并保存不泄露 Evidence 内容的错误诊断

### Requirement: Specialist Evidence 引用必须受当前 Gate 集合约束
系统 MUST 将当前运行的 `allowed_evidence_ids` 作为独立 Agent 输入，并为 Company Analyst 与 Independent Skeptic 生成 run-scoped 输出 Schema，使所有 `evidence_refs` 与 `counter_evidence_refs` 只能从该集合逐字选择 canonical Evidence ID。Specialist Prompt MUST 明确禁止把 `source_id`、`as_of`、`retrieved_at`、分隔符或说明文字拼接到引用字段；来源描述必须放入其他说明字段。严格 Evidence Closure Validator MUST 保持 fail closed，不得增加自动截断 `|` 后内容、猜测映射或其他静默修复。

#### Scenario: Specialist 使用 canonical Evidence ID
- **WHEN** Specialist 的引用字段包含一个或多个当前 Gate 允许的原始 `evidence_id`
- **THEN** run-scoped Schema 接受这些 ID，后续 Evidence Closure 校验通过

#### Scenario: Specialist 拼接来源或时间
- **WHEN** Specialist 在原始 `evidence_id` 后拼接 source、`as_of`、`retrieved_at` 或说明文字
- **THEN** 该值不属于 run-scoped enum，结构化输出或 Evidence Closure 确定性拒绝，系统不得截断后继续运行

#### Scenario: Specialist 引用不存在的 ID
- **WHEN** Specialist 输出不在当前 Gate 允许集合中的 Evidence ID
- **THEN** Schema 或严格 Evidence Closure Validator fail closed，不得进入 CIO 综合
