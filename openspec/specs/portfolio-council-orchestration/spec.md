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
