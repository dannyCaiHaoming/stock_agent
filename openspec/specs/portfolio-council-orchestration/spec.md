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

### Requirement: Council 终态加固必须通过真实 fixture 稳定性门禁
候选版本 MUST 通过 Codex-native 产品入口分别实际运行正常研究、未来或过期证据、Evidence 冲突和 Risk veto 四类版本化 fixture，并对每次运行执行终态检查和实际 Eval。Evidence 冲突 fixture MUST 在没有修改候选产品文件的情况下连续运行至少三次；三次均 MUST 生成与合法 `COMPLETED` 或 `SAFE_NO_TRADE` 终态一致的 `decision.json`、`report.md`、`decision_trace.json` 和 Eval 结果，全部 Evidence References 必须闭合，且任何已形成 CIO 草案的运行不得绕过 deterministic Risk Engine。

#### Scenario: 重新执行四类真实 fixture
- **WHEN** `harden-council-terminal-contracts` 候选进入 Release Gate
- **THEN** 四类 fixture 均通过真实 Codex-native 入口运行并保存各自命令、显式模型、唯一 `run_id`、终态产物、Trace 和实际 Eval 判定；未来或过期证据场景仍可在专业 Agent 前安全终止

#### Scenario: Evidence 冲突连续三次形成合法终态
- **WHEN** 操作者以相同候选版本和三个全新输出目录连续运行 Evidence 冲突 fixture
- **THEN** 三次均完成双 Agent 独立研究、CIO 冲突综合、Risk Engine 检查、Evidence Closure、三项发布产物和实际 Eval，且不得依赖固定 Thesis、Action 或 Confidence

#### Scenario: 任一次冲突运行产生非法 NO_TRADE
- **WHEN** 三次 Evidence 冲突运行中的任一次生成 `maximum_notional: 0`、非空 `target_weight_range`、悬空 Evidence 或缺失 Risk lineage
- **THEN** 该次 Release Gate 返回非零，连续稳定性验收整体失败，不得以另外两次成功抵消

### Requirement: Execution Replay 必须通过受控的 Codex-native Council 入口运行
Execution Replay MUST 使用经过验证的 Replay Capsule，通过现有 Codex-native `portfolio-council` 入口重新执行研究链路，而不是由 Python callback 重建 LLM 结论。重放运行 MUST 使用新的 `run_id` 和空输出目录，明确关联 `source_run_id`，保留相同 Portfolio、PIT Evidence、研究问题、Model、Agent、Skill、Prompt、Schema、MCP Adapter 和 Risk Policy 版本，并重新生成独立 Agent、CIO、Risk、Trace 和 Eval 产物。原运行目录 MUST 保持只读。

#### Scenario: 重放完整双 Agent Council
- **WHEN** 来源运行在 Evidence Gate 后执行了 Company Analyst、Independent Skeptic 和 CIO
- **THEN** Execution Replay 在相同冻结能力计划下重新调用三个独立上下文，并重新经过 deterministic Risk Engine 和终态校验

#### Scenario: 重放 Agent 前安全终止运行
- **WHEN** 来源运行因全部 Evidence 被 PIT Gate 排除而在 Agent 前合法终止
- **THEN** Execution Replay 重建相同 Gate 输入与允许集合，不调用 Agent，并生成关联来源运行的新安全终态与 Eval

#### Scenario: 试图覆盖历史运行目录
- **WHEN** 新输出目录已存在或与来源目录相同
- **THEN** 系统在任何写入或 LLM 调用前拒绝重放

### Requirement: Ablation Profile 必须与默认产品 Council 隔离
CIO-only、Company Analyst + CIO 和完整双 Specialist Council MUST 作为显式 `EVAL_ABLATION` Profile 运行，使用各自版本化的拓扑输入与输出契约，但不得修改或放宽默认产品 Profile 对 Company Analyst、Independent Skeptic、CIO、Evidence Closure 和 Risk Engine 的要求。Ablation 产物 MUST 标记为实验性、仅供评估且不可作为正常产品建议发布。

#### Scenario: 运行 CIO-only Ablation
- **WHEN** Ablation Runner 选择 Variant A
- **THEN** 现有 CIO 在独立实验上下文中直接消费同一 Gate-scoped Evidence，输出符合 Variant 契约的草案并经过 Risk Engine，且不会伪造 Specialist 报告

#### Scenario: 运行 Company Analyst + CIO Ablation
- **WHEN** Ablation Runner 选择 Variant B
- **THEN** 系统只调用现有 Company Analyst 和 CIO，Trace 明确记录 Skeptic 未参与的实验拓扑，不把它伪装成默认 Council 完整运行

#### Scenario: Ablation 配置被用于产品发布
- **WHEN** 普通 `portfolio-council` 运行或产品 Release Gate 收到 `EVAL_ABLATION` Profile 产物
- **THEN** 系统拒绝将其作为产品建议或生产候选运行通过

### Requirement: 重复 LLM 执行必须遵循模型路由和消耗策略
普通实现与确定性开发验证 SHALL 使用 GPT-5.6 Sol；Runtime Regression、Execution Replay 验收和重复 Ablation LLM 运行 MUST 使用显式 GPT-5.6 Terra。只有架构或 Eval 方法存在书面记录的重大争议且获得人工批准时，才 MAY 使用 GPT-6 Astra。每次真实执行 MUST 记录模型标识、token、延迟、cache provenance 和触发原因，并禁止在输入与所有版本 hash 未变化时无理由重复调用 LLM。

#### Scenario: Regression 使用默认重复运行模型
- **WHEN** 一个需要真实 LLM 的 Regression 或 Ablation 案例没有模型覆盖
- **THEN** Runner 使用 GPT-5.6 Terra，并将模型纳入运行锁和缓存键

#### Scenario: 请求升级 GPT-6 Astra
- **WHEN** 操作者拟因架构或 Eval 方法争议升级模型
- **THEN** 运行必须引用争议记录和人工批准；缺少任一项时 fail closed，不得静默升级

#### Scenario: 确定性反例无需 LLM
- **WHEN** Regression 案例只验证悬空 Evidence、Schema、PIT 或 Risk 的确定性 fail-closed 行为
- **THEN** Runner 不调用 LLM，并在报告中记录零 token 与确定性执行原因

### Requirement: Agent Package Demo 与真实 Portfolio Council 必须分离
系统 SHALL 将 `DEMO_SCAFFOLD` 作为开发控制面的装配验证 Profile，而不是现有真实 `portfolio-council` 产品 Profile。Demo MAY 使用确定性 Adapter 产生示例角色输出，并静态验证实际 `portfolio-council` Skill 与 Agent Package 绑定；它 MUST NOT 声称入口 Skill 已执行推理、Codex 主线程已担任 CIO 或真实 Subagent 已启动。真实 fixture 或 live 产品 Profile 仍 MUST 使用其声明的真实 Codex Agent、Skill 和 LLM 约束，不得自动降级到 Demo Adapter。

#### Scenario: 运行 Demo Profile
- **WHEN** 开发者显式选择 `DEMO_SCAFFOLD`
- **THEN** 系统执行固定多 Agent 数据流且不启动真实 LLM，验证实际 Package 静态绑定，并在全部产物中保留 Demo 身份和未执行真实 Skill/CIO/Subagent 的边界

#### Scenario: 真实产品 Agent 调用失败
- **WHEN** 真实 `portfolio-council` Profile 无法调用声明的 LLM Agent
- **THEN** 真实运行按原契约失败或安全终止，不切换到 Demo Adapter 伪造产品报告

### Requirement: Demo 拓扑必须传递经过验证的上游对象
Demo 编排 SHALL 逻辑 fan-out 两份独立输入给 Company Analyst 和 Independent Skeptic，并在 fan-in 后将两份结构化响应作为 CIO 的显式输入，再将 CIO 草案作为 deterministic Risk Engine 的显式输入。任何阶段 MUST 在传递前校验发送者、接收者、`run_id`、`invocation_id` 和 Evidence References，并由编排层保存 Dispatch Record；禁止让 Agent 自行选择下一节点，也禁止使用同一个回调冒充多个 Agent 身份。

#### Scenario: Agent 输出传给下一个节点
- **WHEN** 一个 Demo Agent 返回合法响应
- **THEN** 编排器将该原始结构化对象作为下一节点输入的一部分并保留发送者与接收者，不通过重新生成文本替代传递

#### Scenario: 响应来自错误运行
- **WHEN** CIO 输入包含其他 `run_id` 的 Specialist 响应
- **THEN** 编排器在 CIO 响应前拒绝该输入并报告跨运行传递错误

### Requirement: Demo Adapter 必须保留到真实 Agent 的替换接缝
Demo AgentPort 和只读 ToolPort SHALL 与未来 Codex Agent/MCP Adapter 使用相同的请求、响应和角色输出边界。将任一 Demo Specialist 替换成真实 Codex Subagent，或将 CIO Demo Adapter 替换成当前主线程 CIO 时，MUST NOT 要求下游重写 Portfolio、Evidence、专业报告、CIO Draft 或 Risk 契约。

#### Scenario: 后续替换 Company Analyst
- **WHEN** 后续 Change 为 Company Analyst 接入真实 Codex Subagent 和专业 Skills
- **THEN** 该 Agent 仍消费同一类 Gate-scoped 请求并产生同一角色报告，CIO 和 Risk 接口无需因生产者变化而修改

### Requirement: CouncilRequest 必须与 PortfolioHandoff 独立版本化
系统 SHALL 使用独立 `CouncilRequest` 表达研究请求，通过 `handoff_id`、`handoff_hash` 和 `portfolio_hash` 引用已确认的中立 `PortfolioHandoff v3`。研究请求 SHALL 承载研究问题、期限、范围、比较基准、组合约束引用及可选用户约束；持仓交接对象不得复制这些任务字段。对同一持仓创建不同请求 MUST NOT 改变持仓 hash 或要求重新确认账户状态。

系统 SHALL 从用户研究意图自动构造请求。新增版本的显式 `COMMON_STOCK_RESEARCH` 阶段允许 `holding_horizon`、`benchmark_id` 与 `mandate_artifact_id` 为 null，表示未知期限或本阶段不需要的组合字段；不得填入假值。期限未知时只作当前公司研究并说明限制，不输出期限性组合结论。旧版本及完整 Council 阶段仍按其必要输入约束校验，进入完整决策前必须补齐适用信息。

当前产品约定 `research_scope: ALL_INPUT_POSITIONS`，请求证券集合 MUST 与持仓全部 Position 一致，不得通过缩小请求范围隐瞒资产能力缺口。真正必需字段缺失时 SHALL 请求补充或安全停止，不把哨兵字符串写入持仓交接对象。

#### Scenario: 对同一持仓提出不同问题
- **WHEN** 用户先后对同一个持仓交接对象提出是否继续持有和未来三个月风险问题
- **THEN** 系统生成不同请求但引用相同持仓 hash，不要求重新确认账户状态

#### Scenario: 持有期限未知
- **WHEN** 用户未提供期限且调用显式普通股研究阶段
- **THEN** 新版请求记录 null 和研究限制，不猜测期限；完整决策阶段仍检查所需期限

#### Scenario: 研究请求遗漏部分持仓
- **WHEN** 请求声明 ALL_INPUT_POSITIONS 但证券集合少于确认持仓
- **THEN** 在 Agent 启动前拒绝请求

#### Scenario: 公司研究未指定比较基准和组合约束
- **WHEN** 用户已有确认持仓并仅请求公司研究
- **THEN** 系统自动构造新版阶段请求，相应非必需字段为 null，不要求用户为此额外准备文件

### Requirement: Council 规划只能消费确认状态与研究请求的组合
Council 的最小确定性规划接缝 SHALL 同时消费一个有效 `PortfolioHandoff v3` 和与之绑定的有效 `CouncilRequest`，再根据自身版本和 Product Profile 产生能力映射、能力缺口、批次及 Research Plan。规划产物 MUST 标记 `planning_only: true`，保留输入 hash 和全部持仓覆盖状态；它不得获取研究 Evidence、启动 Agent、生成 Thesis、动作、Risk 结果或最终报告。

#### Scenario: 只生成多资产研究计划
- **WHEN** 有效 Handoff 包含普通股、ETF 和期权且 CouncilRequest 覆盖全部持仓
- **THEN** 规划接缝输出相应能力需求和缺口，保持零 Agent/LLM 调用且不产生投资结论

#### Scenario: 研究请求绑定错误 Handoff
- **WHEN** CouncilRequest 的 Handoff 或 Portfolio hash 与实际 Handoff 不一致
- **THEN** 规划接缝 fail closed，不生成 Research Plan

### Requirement: Portfolio Council 必须接受全持仓研究 Handoff
`portfolio-council` SHALL 接受通过确定性校验的中立 `PortfolioHandoff v3` 和独立 `CouncilRequest`，并在两者绑定通过后，根据每项持仓的 `asset_type` 和当前产品 Profile 建立 Research Capability 映射、能力可用性判断、研究计划、批次与 Agent 派发。Handoff 中每个持仓证券 MUST 进入后续规划，且任何已启动阶段都 MUST 保留同一完整 Portfolio hash；未确认、确认失效、不完整、请求绑定错误或 Portfolio hash 不一致的输入 MUST 在任何研究 Agent 启动前失败。

Handoff 包含 ETF 或期权时，Council 前置规划 MUST 保留这些资产并声明所需研究能力。若当前候选版本没有对应 Skill/Agent，默认完整 Council MUST 以明确能力缺口停止，不得要求 Intake 预先计算能力状态、不得将这些资产交给 Company Analyst 冒充专业覆盖，也不得仅研究普通股后声称组合完成。

显式普通股研究阶段 MAY 在完整 Council 尚不具备 ETF/期权能力时，对规划中标记为可用的普通股有界并行启动 Company Analyst，同时保存全部持仓覆盖清单、未研究资产及能力缺口。该阶段 SHALL 止于研究报告集，不自动启动 Skeptic、CIO 决策或 Risk；无论输入是否全为普通股，都不得把它视为完整 Council。混合资产未覆盖时 MUST 标记 PARTIAL_RESEARCH，不得把部分覆盖作为完整 Council、完整 Portfolio Risk 或候选版本晋升证据。原 planning_only 入口 MUST 保持零 Agent 调用。

#### Scenario: 十只持仓全部交接
- **WHEN** 中立 Handoff 包含十只已确认持仓且 CouncilRequest 声明 `ALL_INPUT_POSITIONS`
- **THEN** Council 从十只资产事实生成完整研究计划并使用相同 Portfolio hash，不只处理前三只

#### Scenario: Draft 直接提交
- **WHEN** 调用方提交 Draft、未知版本、失效 Handoff 或缺少 CouncilRequest
- **THEN** Council 在研究前拒绝输入并返回需要补全、迁移或确认的原因

#### Scenario: 多资产 Handoff 缺少研究能力
- **WHEN** Handoff 同时包含普通股、ETF 和期权，但当前运行版本只有公司研究能力且调用默认完整 Council
- **THEN** Council 自行识别并报告缺少 ETF/期权能力，保留全部研究对象且不启动不完整的完整 Council

#### Scenario: 显式执行普通股部分研究
- **WHEN** 同一混合资产 Handoff 进入显式普通股研究阶段
- **THEN** Council 只为普通股生成独立 Company Analyst 研究请求，保留 ETF/期权为能力缺口，并输出不得被解释为完整组合建议的覆盖状态和普通股研究产物

#### Scenario: 完整组合暂时不能估值
- **WHEN** ETF/期权价格或账户保证金缺失但对应普通股资料有效
- **THEN** 显式普通股阶段不执行完整组合估值作为前置门槛，保留完整持仓引用继续研究；完整决策阶段的核算与风险要求保持不变

#### Scenario: Intake Handoff 夹带能力状态
- **WHEN** v3 Handoff 包含能力状态、研究计划、研究问题、持有期限、benchmark 或 Mandate
- **THEN** Council 拒绝混合边界输入，不信任 Intake 代替 Council 生成的能力状态

#### Scenario: 公司研究入口直接承接确认持仓
- **WHEN** 用户通过 portfolio-council Skill 提出研究意图，已有有效确认 Handoff，并可选指定研究模型
- **THEN** Skill 接续确认结果，经现有宿主承载自动派生请求并准备公司资料，不要求用户转换持仓文件或传入 Gate；所选模型作用于本批 Analyst，父运行与评分模型分别记录，普通使用不隐式启动评分

#### Scenario: 资产覆盖与专业方向覆盖不同
- **WHEN** 所有普通股均已生成公司报告，但尚未开展市场、板块、图形或资金研究
- **THEN** 清单与报告仍明确本阶段专业范围，普通股全部处理不等于全维度研究完成，未研究方向不被当成无风险或公司研究的前置门槛

#### Scenario: 归集实际评价
- **WHEN** 某份公司报告的绑定有效 Eval 已完成
- **THEN** 覆盖清单关联该报告真实评价状态和产物路径，不继续显示未评估或借用不同报告的 PASS，其他持仓状态保持独立

### Requirement: 大组合只能透明分批而不能减少研究范围
后续 Council 执行 MAY 使用有界并发或分批处理全部持仓，但 MUST 保存总数、已完成、待处理和失败项目。只要有持仓尚未形成规定的研究状态，系统 MUST NOT 声称全部组合研究完成；批大小和并发限制不得写成 Portfolio Schema 的持仓数量上限。

#### Scenario: 分两批研究十只持仓
- **WHEN** 执行资源一次只允许处理五只
- **THEN** 系统执行两个批次并最终覆盖十只；中间状态明确列出剩余五只

### Requirement: Intake Change 验收不得隐式启动研究链路
本 Change SHALL 止于统一 Portfolio Draft、账户快照、用户确认、中立 Handoff v3、独立 CouncilRequest 和 `planning_only` Research Plan 的确定性验证，不委派 Company Analyst、Independent Skeptic 或任何按资产划分的输入 Agent，不调用 CIO 综合、获取市场 Evidence、执行 Risk 或生成投资报告。

#### Scenario: 验证输入能力
- **WHEN** 开发者执行 `refine-unified-portfolio-intake` 限定验收
- **THEN** 系统证明股票、ETF、期权、现金及可见保证金字段完整进入中立 Handoff，并可与独立 CouncilRequest 生成只读规划输出后停止，不启动真实研究链路

### Requirement: 研究任务终止与报告成功必须分别识别
系统 SHALL 使用可信派发、Start 子会话绑定与最终 Stop/执行结果识别正向及反证任务终止，不依赖模型草案中的身份字段。失败任务终止后 MUST 释放并发槽位并保留失败原因；只有验证成功的报告满足下游依赖。格式修复仍在进行时不得提前认定终止。全部任务已终止或依赖阻塞后 SHALL 收尾，不持续等待已结束任务；超时保留成功产物及未完成清单，不补造报告或生命周期事件。本修复 MUST NOT 新增调度器、自动研究重试或补查询再提交机制。

#### Scenario: 草案缺身份且全部子任务已结束
- **WHEN** 可信生命周期已确认全部派发任务结束，但部分草案缺失技术身份或报告校验失败
- **THEN** 系统完成失败归集而非继续空等，保留成功结果和具体错误，核心失败时不启动 Skeptic

#### Scenario: 子任务尚在格式修复或缺终止证明
- **WHEN** Stop 被一次格式修复阻止，或当前任务没有可信最终终止记录
- **THEN** 系统不把它计为已结束；超时按执行未完成处理，不制造成功或终止事件

### Requirement: Portfolio Council 必须提供显式独立反证研究阶段
`portfolio-council` SHALL 支持显式 `stage=INDEPENDENT_COUNTER_THESIS_RESEARCH`，从有效的 PortfolioHandoff 与绑定 CouncilRequest 开始，在同一运行中依次复用资料准备、多维正向研究、正向研究包确定性验证和逐普通股 Independent Skeptic。现有 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 阶段仍 SHALL 停止于正向研究包，不得因本能力存在而自动启动 Skeptic。

#### Scenario: 用户明确请求正向多维研究和独立反证
- **WHEN** 用户已有确认 Handoff，并通过 `portfolio-council` 明确选择独立反证研究阶段
- **THEN** 系统使用同一 Portfolio、Request、run、cutoff 和 Gate 完成正向研究及独立反证，再生成正反研究交接产物

#### Scenario: 用户只请求多维研究
- **WHEN** 用户选择既有 `MULTI_DIMENSIONAL_HOLDING_RESEARCH`
- **THEN** 系统保持原有停止点，不启动 `runtime_skeptic`，也不把缺少反证显示为该阶段失败

### Requirement: 独立反证阶段必须在 CIO 与 Risk 之前停止
独立反证研究阶段 SHALL 只产生正向研究包、逐证券 `CounterThesisReport`、正反研究交接包、同源中文摘要和必要执行证明。该阶段 MUST NOT 构造或调用 `runtime_cio`，不得运行 Risk Engine、生成 `CIODecisionDraft`、`decision.json`、组合动作、Outcome、历史重放或回测，也不得将研究交接包描述为完整 Portfolio Council 建议。

#### Scenario: 正反研究全部技术就绪
- **WHEN** 正向研究和每只普通股的反证报告均通过阶段校验
- **THEN** 运行以研究阶段完成状态结束，明确标记 `complete_portfolio_decision=false` 和未启动 CIO/Risk

#### Scenario: 调用方试图在同一阶段提交 CIO 草案
- **WHEN** 独立反证研究运行目录出现 CIO、Risk 或最终决策产物，或调用方请求阶段 finalizer 消费这些产物
- **THEN** 阶段校验 fail closed，不把越界产物纳入合法研究交接

### Requirement: 独立反证阶段必须保留全持仓覆盖与可恢复失败
阶段 SHALL 保留 Handoff 中全部持仓及能力覆盖，只对当前支持的普通股启动 Skeptic。非普通股、正向研究未就绪的普通股和 Skeptic 系统失败 MUST 以逐资产覆盖缺口保留；任一缺口不得被隐藏为完整正反研究。Agent 合法领域状态与系统失败 MUST 分开表示。冻结输入、版本锁和成功产物 hash 均保持有效时，SHALL 允许通过既有恢复入口续跑未完成或失败任务，保留成功结果。重试使用独立 Invocation/attempt 与输出引用，不覆盖历史尝试或成功报告；每次显式恢复每个目标任务最多一个新研究尝试，格式修复沿用一次上限。cutoff、Gate、Handoff、Request 或版本锁变化时 MUST 使用全新运行。

#### Scenario: 混合资产组合进入阶段
- **WHEN** Handoff 同时包含普通股与当前不支持独立反证的 ETF 或期权
- **THEN** 系统只为合格普通股派发 Skeptic，保留其他资产的能力缺口，并拒绝把交接包标记为完整组合决策输入

#### Scenario: 一项 Skeptic Invocation 系统失败
- **WHEN** 某证券反证输出存在非法结构、身份或 Evidence 引用
- **THEN** 系统保存该证券失败与已完成证券的合法产物，交接包不标记为 `DOWNSTREAM_READY`，且不启动 CIO 或 Risk

#### Scenario: 同一冻结运行恢复失败证券
- **WHEN** 用户通过宿主恢复入口重试失败 Skeptic 且冻结输入与成功产物重验通过
- **THEN** 仅派发目标未完成任务，保留其他研究结果和旧尝试，显式记录采用的新结果，不重新采集资料或重跑已成功正向研究

#### Scenario: 恢复时版本或资料发生变化
- **WHEN** 当前运行代码版本锁或冻结输入与原运行不一致
- **THEN** 拒绝原地续跑并要求新运行，不能把新旧资料拼接为原截止点的研究

### Requirement: 首个真实样本必须证明研究链路而非投资结果
Change 验收 SHALL 通过宿主产品入口对至少一个已确认的真实普通股样本执行一次新的独立反证研究运行，保存正向研究、Skeptic 调用、只读 Evidence 工具事件、输入隔离、交接包和阶段边界证据。验收 MUST 使用全新运行目录和同一 point-in-time 边界，不得复用不同 cutoff 的临时报告拼装结果，也不得以市场涨跌、固定 Thesis、固定动作或回测收益作为通过条件。

#### Scenario: MRVL 作为首个真实纵向样本
- **WHEN** 操作者使用当前确认的 MRVL 普通股持仓启动本 Change 的宿主验收
- **THEN** 运行证明正向研究与独立 Skeptic 共享同一 Gate 但保持结论隔离，形成可验证正反研究交接，并明确未启动 CIO、Risk 或回测

#### Scenario: 首次 MRVL 验收发生失败
- **WHEN** 首次样本未完成真实反证或交接验证失败
- **THEN** 允许显式有界修复和重试，满足冻结条件时续跑，否则新运行；不因“一次运行”限制接受失败，不自动扩张样本集

#### Scenario: 工具调用真实但报告空泛
- **WHEN** 执行证明合法而人工复核发现报告只有通用风险、缺少事实支持或可检验解释
- **THEN** Change 不能仅凭 Schema 和工具事件宣称研究质量验收通过；记录具体问题，不引入固定观点、挑战数量或自动分数门槛


### Requirement: 正反交接包必须通过显式独立阶段进入研究级 CIO
系统 SHALL 提供 `PREDECISION_CIO_SYNTHESIS` 阶段，从经过重新验证的 `PreDecisionResearchPackage`、绑定的来源 Handoff 和显式研究请求启动。本 Change 只发布 `RESEARCH_SYNTHESIS`；该阶段 MUST 拒绝 `PORTFOLIO_ADVICE` 请求，不得自动降级后假称已完成建议。阶段 MUST 使用新 run_id 和仓库外独立输出目录，保留 source_run_id、package_hash、源请求及新请求身份。原独立反证阶段的停止点、`complete_portfolio_decision=false` 和源产物 MUST 保持不变。CIO SHALL 由现有宿主入口下的 Codex 主线程执行，不新增 CIO 子 Agent 或第二套编排器。

#### Scenario: 用户研究已清仓的 MRVL
- **WHEN** 用户指定历史合格 MRVL 交接包并明确请求 CIO 研究综合
- **THEN** 新阶段在独立运行中综合原截止点的正反研究，标注当前持仓适配未评估，不要求用户提供新的账户截图或把 MRVL 伪装为现持仓

#### Scenario: 请求本阶段未发布的持仓建议
- **WHEN** 调用方选择 `PORTFOLIO_ADVICE`
- **THEN** 宿主在模型前明确拒绝该级别，不产生持仓动作、Risk 通过或建议文件

#### Scenario: 只运行研究阶段
- **WHEN** 用户仅请求多维研究或独立反证
- **THEN** 原阶段仍停止于研究产物，不自动调用 CIO 或 Risk，也不因缺少决策报告而失败

### Requirement: CIO 准备必须验证来源闭包与时点
系统 MUST 验证源交接包及其 forward bundle、逐股反证、执行证明、完整 coverage、原始报告引用和内容哈希，要求 `consumability=DOWNSTREAM_READY`。CIO 输入 MUST 绑定相同来源 Handoff、portfolio hash、decision_cutoff 与 Gate；源研究 run_id 与新 CIO run_id MUST 分别保留，不改写源报告身份。CIO MUST 只能查询该冻结 Gate 允许的 Evidence，不得获得原始缓存、其他运行或未来事实。承载事实的输入 MUST 保留 source_id、as_of、retrieved_at。旧研究包在新运行中的使用 MUST 明确为原研究截止点的综合，不能标记为当前行情或当前持仓判断。

#### Scenario: 资料篡改或报告来自另一批研究
- **WHEN** 任一报告 hash、证券身份、Gate、cutoff、执行证明或组合绑定不匹配
- **THEN** 系统在 CIO 前报告 `FAILED_VALIDATION`，保留具体错误，不启动模型且不生成建议性 NO_TRADE

#### Scenario: 历史报告不冒充当前研究
- **WHEN** MRVL 的来源 cutoff 早于实际生成时间
- **THEN** 报告分别展示两个时间，说明判断适用于来源 cutoff，不把新价格与旧结论拼接

### Requirement: CIO 阶段必须区分来源失败与研究不确定性
系统 SHALL 按下列范围处理缺口：身份、hash、引用或执行证明错误导致 FAILED_VALIDATION，不得降级发布；正向包未就绪或适用 Skeptic 为 INSUFFICIENT_EVIDENCE、TIMEOUT、缺失或失败时，沿用源包不可下游消费的限制，阻止本阶段；合法完成的 LOW_CONFIDENCE 以及辅助维度的数据不足、不适用、未覆盖 SHALL 保留给 CIO 解释影响。当前账户现金、仓位、ETF 或期权能力不构成本研究级调用的输入前提，也不得据此生成账户适配或完整组合建议。包的 DOWNSTREAM_READY MUST 与逐资产、逐维度 coverage 一起检查，不能代表组合决策就绪。必需上游任务执行失败不得当作普通数据限制。

#### Scenario: 当前账户持有 ETF 和期权但 MRVL 已清仓
- **WHEN** 用户只请求冻结来源包的 MRVL 非动作研究
- **THEN** 系统不要求当前完整账户 Risk 输入，不裁剪历史或当前持仓来制造建议，报告明确账户适配未评估

#### Scenario: 合格交接包有实质性研究不确定性
- **WHEN** 完整性校验和上游就绪规则通过但报告保留置信度限制
- **THEN** CIO 接收真实限制，自主解释其对研究判断的影响，不用 NO_TRADE 代替不确定性

#### Scenario: Skeptic 本身尚未完成研究
- **WHEN** Skeptic 返回 INSUFFICIENT_EVIDENCE 而交接包仅为 STRUCTURALLY_CONSUMABLE
- **THEN** 本阶段列出未完成研究项并停止，不将其与辅助维度信息缺失混同，也不强制修改上游 readiness

#### Scenario: 辅助维度合法受限
- **WHEN** 合格交接包的某个辅助维度为合法资料不足或不适用，且没有必需任务执行失败
- **THEN** CIO 保留限制并解释其是否改变判断；不能把无资料描述为无风险，也不由程序强制投资结论

### Requirement: 研究级成功检查必须核对宿主进程结果
`check-predecision-cio` 在返回成功 PASS 前 MUST 读取既有 `invocation/process-result.json`，确认运行身份与 Request/Trace 相同，`process_exit_code` 为整数 0、`timed_out` 为布尔 false、`failure_code` 为 null、`stage_status=COMPLETED_RESEARCH_SYNTHESIS` 且与 Trace 终态一致、`source_integrity_unchanged` 为布尔 true。缺文件、缺必需字段、非法类型、失败值或身份/状态矛盾 MUST 拒绝成功；不得仅凭报告及 `turn.completed` 认定宿主运行成功。该检查 SHALL 复用现有文件与检查器，不增加独立证明服务；既有模型、版本、Evidence 和同源报告校验保持有效。

#### Scenario: 有研究报告但缺进程结果
- **WHEN** 报告、Trace 和模型事件存在，而宿主进程结果缺失或必需字段缺失
- **THEN** 事后检查拒绝 PASS，保留原始文件，不自动启动模型或补造成功证据

#### Scenario: 宿主失败与研究终态矛盾
- **WHEN** 进程结果表明非零退出、超时、源码变化或失败原因非空，或运行身份/终态不一致
- **THEN** 事后检查拒绝成功，即使研究报告本身符合 Schema

#### Scenario: 合格进程与研究证据一致
- **WHEN** 宿主进程结果满足成功条件，且原有版本、模型、来源、引用及报告检查均通过
- **THEN** 事后检查返回研究级 PASS，仍不代表 Risk、回测或 Promotion 通过

### Requirement: 源码保护验收必须准确表达有限保证
本阶段 SHALL 保留原生沙箱，将模型可写工作区放在仓库外，不将源码目录纳入可写根，并沿用现有受保护产品文件的执行前后完整性检查；发现变化 MUST 阻止成功发布。验收 SHALL 记录实际命令、执行证据及宿主完整性结果，并明确受保护文件清单的范围。全进程 OS 强制只读 SHALL 保持 `UNVERIFIED`，不是本 Change 的完成前提；命令配置、前后 hash 相同或一次路径拒写均 MUST NOT 被解释成运行期间所有进程从未写入源码的证明。本 Change 不新增权限探针平台或额外外层沙箱。

#### Scenario: 宿主完整性证据满足有限保证
- **WHEN** 仓库外工作区与原生沙箱配置正确，宿主结果及原有完整性校验通过，但没有全进程 OS 拒写证明
- **THEN** 可按本阶段有限保证验收，明确保留 OS 强制只读未验证的限制，不要求额外权限工程

#### Scenario: 受保护产品文件发生变化
- **WHEN** 宿主执行前后的受保护产品文件完整性不一致
- **THEN** 启动器拒绝成功发布，事后检查不得把失败的完整性结果认证为 PASS

### Requirement: 新 CIO 阶段必须通过真实 MRVL 研究级验收
Change 验收 MUST 从宿主入口对合格 MRVL 交接包完成真实 CIO 研究综合，证明多维正向报告和独立反证、只读 Evidence 查询、主线程身份、模型及锁定指令版本和最终同源内容。研究级路径 MUST 有非持仓、缺当前账户输入仍可交付且禁止动作字段的聚焦测试。已通过的旧 MRVL 真实研究运行只可复用未受实现和版本锁变化影响的证据；本轮收敛入口后须对受影响路径补一次真实宿主 Smoke 与独立内容复核。模拟资料或固定草案 MUST NOT 替代真实消费证据。实现完成 MUST 经独立只读复核和人工批准；本次不要求完整组合建议、固定动作、市场收益或晋升 PASS。

#### Scenario: MRVL 已不在当前持仓
- **WHEN** 来源包来自过去持有 MRVL 的时点，而当前已清仓
- **THEN** 真实验收只检查正反研究综合的证据、内容和边界，不要求或伪造持仓动作及 Risk

#### Scenario: 实际运行只完成准备
- **WHEN** 没有可信 CIO 模型消费及查询证据
- **THEN** 验收保持未完成，不把输入文件存在或进程退出成功当作消费证明

### Requirement: 研究级 CIO 必须接收阶段适用且可追溯的有效指令
`PREDECISION_CIO_SYNTHESIS` 的模型输入中的指令段 SHALL 只交付本阶段适用的产品安全边界、CIO 研究方法、冻结来源及 Evidence 使用规则、输出契约和非动作限制；不得把旧 fixture Council、`EVAL_ABLATION` 或尚未发布的建议分支作为本阶段执行指令。系统 MUST 在模型调用前锁定有效指令文本及其来源版本，并在终态验证实际交付的内容与该锁一致；仅有源文件存在或源文件 hash 一致不足以证明有效内容已交付。产品安全、来源截止点、Skeptic 分歧、事实与推断区分及证券特定 Macro/Market 传导不得因精简而消失。旧运行的指令和产物 MUST 保持原样。

#### Scenario: 研究级 MRVL 调用
- **WHEN** 合格的冻结 MRVL 正反研究包进入 `PREDECISION_CIO_SYNTHESIS`
- **THEN** CIO 接收本阶段有效规则及已验证报告，不接收无关阶段的执行说明，并继续只输出原研究截止点的非动作综合

#### Scenario: 输入资料夹带执行指令
- **WHEN** 冻结报告或工具返回内容包含改变角色、越权查询或修改产品文件的指令文字
- **THEN** CIO 的有效规则明确将其视为待分析资料而非执行指令，并保留禁止编造事实和修改产品文件的约束

#### Scenario: 阶段指令段落损坏
- **WHEN** 有效指令所依赖的显式标记缺失、重复、不配对或内容为空
- **THEN** 准备阶段给出具体来源和错误并拒绝启动模型，不静默使用空规则或其他阶段全文；普通文档标题调整不作为段落定位依据

#### Scenario: 有效指令与运行锁不一致
- **WHEN** 保存的模型输入、有效指令或其来源版本与运行清单声明不一致
- **THEN** 运行拒绝成功验证，不以源文件仍存在、旧运行通过或报告文字看似合理代替交付证明

### Requirement: 指令消减必须保留研究质量与确定性门禁
系统 SHALL 对同一冻结来源包记录修改前后的提示规模和可取得的实际模型输入用量，区分固定输入大小与包含工具往返、缓存的运行用量；不得以文件字节数或单次 token 数代替研究质量验收。重复机械规则去重后 MUST 保留一处简短完整的操作说明及现有确定性门禁，不得因校验器能拒绝错误就删除完成查询与输出所需的指导；不得把主观投资判断改写为 Python 规则。真实研究级验收 MUST 保留 Evidence 查询与引用闭包、现金及债务等双侧比较证据、未消解 MD&A 冲突限制、相对市场表现的证券特定传导、Skeptic 挑战取舍及非动作边界，并由独立内容复核确认无重大退化。验收 SHALL 记录本轮全部尝试的引用/工具错误、验证失败和重试；由消减引入的错误须修复并补受影响验证，不得只展示最终成功。不要求固定投资观点、动作、收益或任意百分比的 token 降幅，单次 Smoke 不证明统计成功率。

#### Scenario: 机械说明已有等效确定性约束
- **WHEN** 某项重复说明拟从 CIO 模型输入删去
- **THEN** 验收记录指出保留的简短操作说明、现有校验位置与失败行为，复用或补充聚焦负例证明非法结果仍被拒绝；必要操作信息和研究语义不得删去

#### Scenario: 真实研究运行结构通过但内容退化
- **WHEN** 新版本 MRVL 宿主运行通过 Schema、Evidence 和 Trace，却遗漏重要反证、误写未证实因果、丢失双侧事实或把研究变成交易建议
- **THEN** Change 内容验收失败，不能以输入缩短或历史运行 PASS 宣称完成

### Requirement: 指令更新必须保持资源一致性和阶段兼容
指令及其必要版本绑定 MUST 成套更新和回退，更新后的产品资源发现 SHALL 成功。切换共享源码前 MUST 确认使用该源码的受影响运行已经结束，不得在运行中替换其锁定指令、实现或版本清单，也不得通过弱化完整性校验规避冲突。旧 fixture 配置和指令加载、既有 Company/多维/Skeptic 停止点及合格 MRVL 来源包的下游准备 SHALL 保持可用；本 Change 对上游三个角色仅做只读审计。旧报告 MUST 保持可读取且原始产物不改写，旧版本运行不冒充新版本验收。

#### Scenario: 指令已更新而版本清单未同步
- **WHEN** 产品源资源与声明的版本 hash 不一致
- **THEN** 资源发现明确拒绝启动；实施方成套修正新版本资源，不改写旧运行锁或跳过检查

#### Scenario: 受影响研究仍在运行
- **WHEN** 已有运行仍依赖待修改的共享源码和指令
- **THEN** 变更等待该运行自然结束后切换，不强行结束运行或在收尾前替换其资源

#### Scenario: 新版本消费既有研究来源
- **WHEN** 更新后对原合格 MRVL 来源包执行零模型准备
- **THEN** 原报告及来源闭包验证通过，新 CIO 输入保留相同来源内容和截止点；原研究阶段不自动进入 CIO/Risk，旧 fixture 加载仍通过其原有检查
