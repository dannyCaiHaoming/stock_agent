## MODIFIED Requirements

### Requirement: LLM 与确定性计算职责必须分离
真实 Codex LLM SHALL 负责 Company Research、Counter Thesis、证据是否足以支持投资判断、规范化冲突是否具有实质性、冲突影响和 CIO 决策综合；确定性程序 SHALL 仅负责 fixture 数据读取与标准化、point-in-time 过滤、声明式 freshness 检查、可机械判定的规范化字段冲突、数学计算、持仓核算、硬风控、契约验证和存储。系统 MUST NOT 使用 Python callback、固定字符串或条件分支生成 Thesis、Action 或 Confidence，也不得使用同一个 callback 模拟多个专业 Agent。

#### Scenario: 专业 Agent 对 fixture 开展研究
- **WHEN** Company Analyst 或 Independent Skeptic 接收已通过 Evidence Gate 的输入
- **THEN** Agent 使用自己的 Codex Agent 定义和专业 Skills 生成结构化研究结果，Python 只提供确定性数据与校验结果

#### Scenario: 估值能力执行
- **WHEN** Agent 评估标的估值
- **THEN** 确定性层计算给定假设下的数值，Agent 解释假设、情景、适用性和不确定性

#### Scenario: 实现尝试恢复硬编码投资结论
- **WHEN** 验收发现 Thesis、Action 或 Confidence 来自预写 callback、fixture 预期输出或大型条件规则
- **THEN** 运行真实性门禁失败，候选版本不得通过 Change 验收

#### Scenario: 主观判断被编码为规则
- **WHEN** 实现将“优质公司”“好估值”或“应买入”等主观投资判断写入大型 if/else 规则
- **THEN** 架构评审判定其违反职责边界并阻止晋升

### Requirement: 专业研究输出必须结构化
每份真实 Agent Research Report MUST 通过对应 Schema 校验，并包含研究范围、Agent 身份、Claims、实际存在的 Evidence References、反证、不确定性、数据缺口、失效条件、置信度及其理由；报告 MUST NOT 直接决定完整组合的最终动作，校验失败的报告不得进入 CIO 综合。

#### Scenario: Company Analyst 完成真实 LLM 研究
- **WHEN** Company Analyst 返回分析结果
- **THEN** CIO 只接收通过 Schema 和 Evidence Closure 校验的结构化报告，并能区分事实、假设和解释

#### Scenario: Company Analyst 完成研究
- **WHEN** Company Analyst 完成一个标的的质量和估值研究
- **THEN** CIO 收到符合统一 Schema 的报告，并能区分事实、假设和解释

### Requirement: 反证能力必须保持独立性
系统 SHALL 通过独立的 Skeptic Agent 定义和独立 LLM 上下文执行 `INDEPENDENT_FIRST_PASS`；第一轮 Skeptic 输入不得包含 CIO 草案、Company Analyst 输出或其摘要，且 Trace MUST 保存可验证的输入哈希。只有第一轮报告完成后，系统才可在未来 Change 中引入明确授权的定向压力测试。

#### Scenario: 独立反证研究
- **WHEN** CIO 为同一标的并行委派 Company Analyst 和 Independent Skeptic
- **THEN** Skeptic 的第一轮输入哈希对应的结构化输入只包含证券、研究范围、截止时点和 Evidence Bundle，不包含其他 Agent 结论

## ADDED Requirements

### Requirement: 每个专业 Agent 必须实际加载声明的 Skills
每个专业 Agent 运行 MUST 绑定其版本化 Agent 定义和专业 Skills。系统 MUST 在调用前生成不可变 Invocation Manifest，记录解析后的 Agent 定义、纳入仓库可控指令包的 Skill 名称/版本/内容哈希、task prompt 哈希和完整 instruction bundle 哈希，并以 Codex 机器可读执行事件证明对应 Agent 调用真实发生。专业报告还 MUST 满足所绑定 Skill 的专属输出协议并关联其实际工具结果。仅验证文件存在、配置声明或 Agent 自报 Skill 名称均不构成实际参与；系统不得声称能够证明模型内部注意力或保存隐藏推理。

#### Scenario: 审计 Company Analyst 运行
- **WHEN** 评审者检查一次真实 Company Analyst Trace
- **THEN** Invocation Manifest 和 Codex 执行事件证明 `evidence-grounding`、`company-research` 和 `valuation` 的固定内容被纳入该 Agent 的仓库可控指令包且调用真实发生，报告通过三个 Skill 的专属协议与工具结果校验

#### Scenario: Agent 只在输出中自报 Skill 名称
- **WHEN** 专业报告声明使用了某 Skill，但 Invocation Manifest、内容哈希或 Skill 专属输出证据缺失
- **THEN** Skill 参与真实性校验失败，该运行不得作为真实 Council 验收证据
