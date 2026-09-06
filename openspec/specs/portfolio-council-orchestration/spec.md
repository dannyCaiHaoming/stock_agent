# portfolio-council-orchestration Specification

## Purpose

定义 Codex 主线程作为 CIO 的组合决策协议，使专业研究可动态并行委派、独立完成、显式处理冲突并接受不可绕过的风险校验。

## Requirements

### Requirement: Portfolio Council 必须由 CIO 主线程主持
用户提供 fixture 持仓并调用 `portfolio-council` Skill 后，当前 Codex 主线程 SHALL 承担 CIO 职责，持有用户目标、Portfolio Snapshot、Mandate、`decision_cutoff` 和完整决策上下文；研究判断与组合综合 MUST 由本次 Codex LLM 运行产生，不得由预写 Python callback 或固定模板代替。运行 MUST 解析并记录仓库内实际使用的产品 Skill、CIO 指令和 runtime Agent 定义，用户全局同名资源不得被静默用作验收对象。

#### Scenario: 启动 Codex-native fixture 组合评审
- **WHEN** 用户通过 `portfolio-council` Skill 提交有效 fixture 持仓
- **THEN** 当前 Codex 主线程先完成产品包发现预检，再建立唯一 `run_id`、研究问题、固定能力计划、证据截止时点和产物目录，并以 CIO 身份执行后续综合

#### Scenario: 启动组合评审
- **WHEN** 用户提交有效持仓并调用 portfolio council
- **THEN** CIO 建立本次运行的研究问题、能力需求、证据时点和委派计划

### Requirement: CIO 必须按能力需求动态委派
CIO SHALL 根据当前运行的能力计划委派专业 Agent；在本 Change 的固定 fixture Smoke Profile 中，只要 Evidence Gate 与确定性输入预检没有触发安全终止，能力计划 MUST 同时包含 Company Analyst 和 Independent Skeptic，且动态增加、删除或替换其他 Agent 不属于本 Change 的验收范围。

#### Scenario: 执行固定 fixture 能力计划
- **WHEN** CIO 运行 `activate-codex-native-fixture-council` Smoke Profile
- **THEN** CIO 并行委派 Company Analyst 和 Independent Skeptic，且不委派 Market/Catalyst 或其他未纳入固定链路的 Agent

#### Scenario: 持仓仅需公司基本面复核
- **WHEN** 市场和事件数据仍然有效且不存在相应缺口
- **THEN** CIO 可以只委派 Company Analyst 和 Skeptic，并在 Trace 中记录未调用其他能力的理由

### Requirement: 并行研究必须隔离初始结论
被并行委派的 Company Analyst 与 Independent Skeptic SHALL 使用独立 Codex Agent 定义和独立 LLM 上下文完成第一轮研究；两个委派请求 MUST 在等待任一专业报告前发出。Skeptic 的初始输入 MUST NOT 包含 Analyst、CIO 或其他 Agent 的结论，CIO 只能在两个结构化报告均完成并通过验证后比较共识、冲突和证据质量。

#### Scenario: 两个 Agent 独立形成相反判断
- **WHEN** Company Analyst 与 Independent Skeptic 对同一 Evidence Bundle 独立研究并形成实质冲突
- **THEN** Trace 证明两个第一轮输入均不含对方结论，CIO 记录双方证据、未解决冲突及其对动作和置信度的影响

#### Scenario: 两个 Agent 给出相反判断
- **WHEN** Company Analyst 与 Skeptic 对关键 Thesis 存在实质冲突
- **THEN** CIO 明确记录冲突事实、双方证据、未解决部分及其对动作和置信度的影响

### Requirement: Fixture Council 必须通过 Codex-native 入口端到端执行
系统 MUST 提供由 `portfolio-council` Skill 驱动的固定链路：读取 portfolio fixture、执行 Evidence Gate、通过 Gate-scoped 只读 MCP 向两个专业 Agent 提供证据、并行委派、由 CIO 综合、调用 deterministic Risk Engine、验证并保存最终产物；系统 MUST NOT 为此引入独立 Python LLM 编排后端。

#### Scenario: 正常 fixture 完成固定链路
- **WHEN** 操作者使用公布的 Codex-native Smoke 命令运行正常 fixture
- **THEN** 同一 `run_id` 下产生两个真实 LLM 专业报告、CIO 草案、Risk Report、最终决策和完整 Trace，且 Trace 包含专业 Agent 的只读 MCP 调用

### Requirement: Fixture Agent 只能访问 Gate-scoped 只读 MCP
进入专业研究阶段后，Company Analyst 与 Independent Skeptic MUST 通过本次 `run_id` 绑定的只读 fixture MCP 工具解析允许的 Evidence References；该工具面 MUST NOT 返回 Gate 排除事实，不得暴露原始 fixture 文件、外部网络、真实 Provider、券商或账户写入能力。CIO SHALL 只接收已验证的结构化专业报告和 Evidence References；需要核验事实时，只能通过相同 Gate-scoped 只读工具解析引用。

#### Scenario: Agent 请求被 Gate 排除的事实
- **WHEN** 专业 Agent 使用未知、被排除或不属于本次 `run_id` 的 Evidence ID 查询 fixture MCP
- **THEN** 工具拒绝请求并记录只含 ID 和原因的审计事件，不返回该事实内容

#### Scenario: CIO 核验专业报告引用
- **WHEN** CIO 需要查看某项专业报告所引用的事实
- **THEN** CIO 通过本次运行的只读 Evidence 工具解析该引用，而不是读取原始 fixture 或未过滤 Evidence Bundle

### Requirement: 固定链路必须定义安全终止点
在 portfolio 输入无效、Evidence Gate 后不存在任何可用事实，或确定性前置条件无法满足时，系统 SHALL 在委派 LLM Agent 前终止并输出合法 `SAFE_NO_TRADE`；只要存在可用证据且输入契约有效，系统 MUST 执行固定双 Agent 委派。专业 Agent 返回结构有效的 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE` 或 `TIMEOUT` 状态时，CIO SHALL 基于两份状态形成安全决策；非法结构、悬空引用或伪造元数据 SHALL 进入 `FAILED_VALIDATION`，不得转为投资性 `NO_TRADE`。

#### Scenario: Gate 后没有任何可用事实
- **WHEN** 所有 fixture 事实都因未来、过期或元数据无效被 Gate 排除
- **THEN** 系统不调用专业 Agent，保存前置终止血缘，并输出原因明确的 `SAFE_NO_TRADE`

#### Scenario: Agent 输出包含悬空引用
- **WHEN** 任一专业 Agent 在受控修复后仍返回悬空 Evidence Reference
- **THEN** 运行进入 `FAILED_VALIDATION`，CIO 不综合该报告且系统不发布最终建议

### Requirement: Smoke 运行必须可重复调用并留下可核验产物
系统 SHALL 提供 `codex exec` 或等价 Codex-native 命令，接受明确 fixture、显式模型和全新输出目录，执行仓库产品包发现预检，并输出可保存的机器可读 Codex 事件；命令完成后 MUST 返回可自动检查的退出状态，并在输出目录保存与终态对应的全部验收产物。Smoke 运行前后 MUST 验证产品代码、Agent、Skill、Schema 和 Risk Policy 未被运行过程修改。

#### Scenario: 评审者重复执行 Smoke 命令
- **WHEN** 评审者在相同候选版本上使用同一 fixture 和新的输出目录再次运行命令
- **THEN** 两次运行均保存各自唯一 `run_id`、显式模型、仓库资源解析结果和固定版本输入，且可以独立通过 Schema、Evidence、Risk、Trace 与产品文件完整性校验

### Requirement: CIO 必须允许 NO_TRADE
当关键数据缺失或过期、证据存在无法解决的实质冲突、置信度不足或风险约束不可满足时，CIO SHALL 输出 `NO_TRADE`，不得为了完成流程而强制产生交易建议。

#### Scenario: 关键证据无法及时补齐
- **WHEN** CIO 判断缺失信息可能实质改变决策且当前运行无法获取
- **THEN** 草案使用标准原因码输出 `NO_TRADE` 并列出所需补充证据

### Requirement: 风险否决后最多允许一次修订
Risk Engine 对完整草案返回 `REVISE_REQUIRED` 时，CIO MAY 根据可行边界修订一次；修订后仍不合规则最终计划 MUST 为 `NO_TRADE` 或删除受否决的交易意图。

#### Scenario: 修订后仍违反仓位上限
- **WHEN** CIO 的第二版草案仍违反相同或其他硬约束
- **THEN** 系统停止循环并输出风险否决结果，不继续自动协商
