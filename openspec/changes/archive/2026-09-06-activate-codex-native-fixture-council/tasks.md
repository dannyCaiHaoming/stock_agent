## 1. 基线、版本与 Codex 能力确认

- [x] 1.1 记录当前 0.1.0 确定性测试、Eval 和只读运行时审计基线，并把 callback/reference 链路明确标记为 test-only；通过基线测试结果及产品入口不再引用 callback 的检查验证。
- [x] 1.2 使用本机 Codex 帮助和官方文档确认 Skill/Plugin 发现、独立 Agent/Subagent、并行委派、显式模型、JSONL 事件、输出 Schema、严格配置和非交互执行接口，保存 Codex 版本与能力记录；通过可重复的只读探测命令验证。`codex-cli 0.153.4` 已实际保留 `agent_type`，并加载对应项目 Agent 定义。
- [x] 1.3 建立候选版本 manifest，锁定 Codex runtime、显式模型、Agent、Skill、Schema、fixture MCP adapter、Risk policy 和数据快照版本字段；通过 manifest Schema 测试验证缺少任一验收必需字段时失败。

## 2. 仓库产品包发现与 Codex-native 入口

- [x] 2.1 实现 Smoke 资源发现预检，解析仓库内 Plugin manifest、`portfolio-council` Skill、CIO 指令和两个 runtime Agent 的实际路径、版本与内容 hash；通过全局同名资源存在时仍解析到仓库目标，以及 hash 不匹配时在 LLM 调用前失败来验证。
- [x] 2.2 将 `portfolio-council` Skill 更新为 fixture Council 唯一产品入口，声明固定阶段、安全终止点、三类终态、只读边界和输出契约；通过 Skill 校验及一次无 LLM 的资源/输入预检验证入口实际被加载。
- [x] 2.3 创建或完善 CIO、Company Analyst、Independent Skeptic 三个独立且带版本的 runtime Agent 定义，分别绑定所需专业 Skills 与最小只读工具；通过配置解析、内容哈希清单和 Agent 身份测试验证三者不会互相替代。
- [x] 2.4 增加架构边界门禁，禁止产品 Python 模块导入模型 SDK、运行 LLM 对话循环、用同一 callback 模拟多个角色或硬编码 thesis/action/confidence；通过静态检查和负向架构测试验证违规实现会失败。
- [x] 2.5 更新 Company Analyst、Independent Skeptic 和 CIO 综合能力的 Capability Contract，逐项关联 Input、Tool/Data、Skill/Reasoning、Structured Output 与 Eval；通过能力清单完整性测试验证不存在只有 Agent 名称或 Prompt、缺少执行闭环的空能力。

## 3. Fixture、Evidence Gate 与只读 MCP

- [x] 3.1 建立正常研究、未来或过期数据、Analyst/Skeptic 证据冲突、Risk Engine 否决四类版本化 fixture；Risk 场景同时提供明确标记为测试输入的 boundary draft，每条事实包含 `evidence_id`、`source_id`、`as_of` 和 `retrieved_at`，并通过 fixture Schema 与时间线测试验证。
- [x] 3.2 实现 Agent 前置 Evidence Gate，同时过滤 `as_of` 或 `retrieved_at` 晚于 `decision_cutoff` 的事实，并应用声明式 freshness policy；通过 future-as-of、future-retrieval、stale、missing-metadata 单元测试验证。
- [x] 3.3 对相同规范化 conflict key 的不兼容值进行机械标记并保留全部有效来源，不判断可信方或投资实质性；通过冲突 fixture 验证 Python 输出仅包含来源、值和冲突元数据。
- [x] 3.4 保存包含输入、允许、排除 Evidence IDs、排除原因、cutoff、freshness/conflict policy version 和 bundle hash 的 Gate artifact；通过同一输入重复运行的规范化 hash 一致性测试验证。
- [x] 3.5 实现绑定 `run_id` 的 fixture-only 只读 MCP 工具面，只返回 Gate 允许 Evidence 和确定性计算结果，拒绝未知、被排除或跨 run ID 的查询；通过工具契约、负向查询和无写操作测试验证。
- [x] 3.6 禁用 fixture Smoke 中的实时 Web、真实 Provider、券商和账户工具，并阻止 Agent 直接读取原始 fixture；通过 Agent 工具清单、网络/写入拒绝和原始 fixture 不可访问测试验证。
- [x] 3.7 实现确定性安全终止：portfolio 输入无效或 Gate 后无任何可用事实时不调用 LLM 并生成 `SAFE_NO_TRADE`；通过 Codex 事件中无 Agent 调用及终态三文件验证，仍有可用证据时不得由 Python 判断投资充分性。

## 4. Invocation、独立研究与引用闭包

- [x] 4.1 定义并版本化 Company Analyst、Independent Skeptic 和 CIO decision draft Schema，覆盖身份、范围、Claims、反证、不确定性、数据缺口、失效条件、置信度理由和 Evidence 引用；通过有效与缺字段样例的 Schema 测试验证。
- [x] 4.2 为 CIO 和两个专业 Agent 生成调用前不可变 Invocation Manifest，记录解析路径、Agent/Skill/task prompt/instruction bundle hashes、模型、Evidence IDs、工具权限和输入 hash；通过篡改任一输入或指令后 hash/校验失败验证。
- [x] 4.3 在等待任一结果前通过 Codex 原生能力发出 Company Analyst 与 Independent Skeptic 两个委派请求，并保存机器可读事件；通过事件顺序、Agent 身份和独立 session/context 标识验证并行委派。
- [x] 4.4 构造两个相互独立的规范化输入包，且 Skeptic 第一轮输入不含 Analyst/CIO 输出、摘要、hash 或派生结论；通过输入快照、hash 和敏感字段负向测试验证。
- [x] 4.5 以 Invocation Manifest、Codex 调用事件、Skill 专属输出协议和关联 MCP 工具结果共同证明 Skill 参与；通过删除任一证据或仅保留 Agent 自报 Skill 名称会使真实性门禁失败来验证。
- [x] 4.6 在专业报告进入 CIO 前执行 Schema 与 Evidence Closure 校验，只允许 Gate 允许集合中的 ID 或显式假设；通过未知、被过滤、跨 run 和悬空引用测试验证均进入 `FAILED_VALIDATION`。
- [x] 4.7 允许同一 Agent 对纯格式错误执行至多一次受控修复，且修复不得新增事实或扩大 Evidence 集合；通过重试次数、前后引用集合和 Trace 事件测试验证，第二次仍非法时不得转为 `NO_TRADE`。
- [x] 4.8 区分合法领域状态与系统错误：结构有效的 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE` 或 `TIMEOUT` 可进入 CIO，非法 JSON、Schema、引用或执行元数据不可进入；通过每种状态的集成测试验证。

## 5. CIO 综合与 deterministic Risk Engine

- [x] 5.1 让 CIO 只接收两份已验证结构化报告、Evidence References、组合确定性数据和 Gate-scoped MCP 核验能力，不读取原始 fixture、未过滤事实或 Subagent 隐藏推理；通过 CIO Invocation Manifest 与工具调用测试验证。
- [x] 5.2 要求 CIO 显式记录共识、来源冲突、未解决问题、失效条件及其对动作和置信度的影响，并允许 `NO_TRADE`；通过冲突 fixture 的结构化 Eval 验证，不预设具体动作或置信度数值。
- [x] 5.3 将每个可形成的 CIO draft 送入现有 deterministic Risk Engine，保留原始动作、可行边界、修改、违规、否决原因和最终动作；通过同一输入和 policy version 重复运行结果一致验证。
- [x] 5.4 使用明确标记为 fixture producer 的固定 Risk boundary draft 稳定触发 `REVISE_REQUIRED` 或 `REJECTED`/`RISK_VETO`，并证明最多一次 CIO 修订；通过重复执行获得相同状态、原因和修改记录验证，且该 draft 不得计作 LLM 输出。
- [x] 5.5 限制 Risk Engine 只执行仓位、集中度、现金、可交易性和组合核算等硬约束；通过架构审查和策略测试确认没有引入主观投资评分或大型投资判断 if/else。

## 6. 终态、输出、Trace 与运行完整性

- [x] 6.1 实现 `COMPLETED`、`SAFE_NO_TRADE`、`FAILED_VALIDATION` 三类互斥终态及转换规则；通过状态机测试验证数据/研究不足不会冒充系统错误、系统错误也不会转换成投资性 NO_TRADE。
- [x] 6.2 按 `run_id` 保存 manifest、输入、Gate、Invocation Manifests、最小化 Codex JSONL 事件、Agent 报告、CIO draft、Risk result、Eval 和终态产物；通过每类终态的允许/必需文件矩阵验证。
- [x] 6.3 对 `COMPLETED` 与 `SAFE_NO_TRADE` 输出同一 `run_id` 的 `decision.json`、`report.md` 和 `decision_trace.json`；对 `FAILED_VALIDATION` 只输出 `decision_trace.json`、`run_error.json` 及失败前审计产物，且通过不存在最终建议文件的负向测试验证。
- [x] 6.4 扩展 Decision Trace，关联 Invocation Manifest、Codex Agent 事件、只读 MCP 工具事件、仓库可控指令 hashes、显式模型、Codex runtime、Evidence/Data/Schema/Policy 版本、输入输出 hashes 和完整 Risk 血缘；通过 Trace Schema 与从输入到终态的遍历测试验证。
- [x] 6.5 在 CIO draft、Risk result 和最终决策边界执行 Schema 与 Evidence Closure 校验；通过注入未知、被过滤和跨 run Evidence ID 验证运行进入 `FAILED_VALIDATION` 且不生成最终建议。
- [x] 6.6 从已验证结构化产物确定性渲染 `report.md`；通过动作、适用 Thesis、Evidence IDs、失效条件、NO_TRADE 原因、Risk 状态和 `advisory_only` 的跨文件一致性测试验证报告没有新增事实。
- [x] 6.7 在 Smoke 前后计算产品代码、Agent、Skill、Schema 和 Risk Policy 的完整性 hash，并限制输出到显式运行目录；通过故意修改受保护文件后的验收失败测试及正常运行零差异验证。

## 7. Replay 与基于实际产物的 Eval

- [x] 7.1 实现 Artifact replay，使用已保存 Evidence、Agent 输出、版本和 Risk policy 重新执行校验、Risk Engine、Trace 关联与报告渲染；通过重放后结构化 hash 和 Risk 结果一致性测试验证。
- [x] 7.2 定义 Native rerun manifest，使相同 fixture、cutoff、Agent/Skill/task prompt/Schema 版本和显式模型可以新 `run_id` 再运行；通过输入与版本 hash 一致、输出通过契约和语义 Eval 验证，不要求自然语言逐字一致。
- [x] 7.3 让 Eval Runner 直接消费真实运行的 Trace、Invocation Manifests、Codex/MCP 事件和终态文件；通过删除任一必需实际产物会使 Eval 失败来验证其不是静态占位报告。
- [x] 7.4 为四类 fixture 定义不依赖固定投资结论的验收不变量：正常场景验证完整链路，未来/过期场景验证精确过滤，冲突场景验证独立来源和 CIO 消费，Risk 场景验证真实风险经过与确定性 boundary veto；通过预期通过/失败样例验证。
- [x] 7.5 将本 Change 的多 Agent Eval 限定为 Skeptic 独立性、非重复反证/缺口和 CIO 显式消费，不声称市场收益、Alpha 或统计预测增益；通过 Eval Schema 和报告措辞门禁验证。

## 8. Codex-native Smoke 与真实 LLM 验收

- [x] 8.1 提供并验证接受 fixture、cutoff、显式模型和全新输出目录的 `codex exec` 或等价命令，启用机器可读事件与严格配置，并完成仓库产品包 discovery preflight；通过复制命令获得正确退出码和终态运行包验证，且不以 `python3 -m product` 作为 LLM 编排入口。
- [x] 8.2 通过 Codex-native 入口执行四类 fixture：正常研究完成完整 Council，未来/过期场景证明 Gate 与安全终态，冲突场景证明独立报告和 CIO 冲突综合，Risk 场景证明真实 draft 经过 Risk Engine；另执行确定性 Risk boundary fixture 证明稳定否决，通过各场景 Trace、终态文件和实际 Eval 验证。
- [x] 8.3 至少成功执行一次非 fake、非 callback 的真实 Codex LLM 正常 fixture 运行，保存 `run_id`、显式模型、Codex runtime、Invocation Manifests、Agent/Skill/task prompt hashes、Codex/MCP 事件、命令、退出状态、完整结构化产物和实际 Eval；通过自动真实性门禁与人工抽查共同验证。
- [x] 8.4 将经过敏感信息检查的真实验收包保存到版本化 Eval 目录，不提交完整原始终端日志或凭据；通过 secret scan、文件清单和从验收包成功执行 Artifact replay 验证。

## 9. 回归、审查与晋升门禁

- [x] 9.1 运行全部确定性单元、集成、Schema、MCP、架构、状态机和 Eval/Regression 测试，保留命令与结果；通过现有 0.1.0 测试无回归且新增门禁全部通过验证。
- [x] 9.2 执行只读运行时就绪复审，逐项核验真实 LLM、仓库 Skill、独立 Agent、只读 MCP、Risk 否决、Evidence 时间字段、Trace 血缘、终态、硬编码/placeholder、Replay 和实际 Eval；通过 PASS/FAIL 矩阵全部 PASS 验证。
- [x] 9.3 运行 OpenSpec 严格校验并完成架构边界、安全、受保护文件完整性和 advisory-only 人工 Review；通过校验成功及人工审批记录验证，审批前不得更新生产版本指针或归档 Change。
