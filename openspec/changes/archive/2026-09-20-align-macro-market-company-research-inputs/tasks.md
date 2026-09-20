## 1. 当前研究拓扑与历史边界

- [x] 1.1 新增版本化 `holding-research-input-topology` 清单及 schema，表达 Company / Macro / Market、capability、Agent、scope、output contract、provider planes 和权威来源引用；以 schema 校验及 fixture 断言三域映射完整作为验证
- [x] 1.2 实现拓扑 loader/validator，并在新多维研究 run manifest 中锁定拓扑及来源引用的版本/hash；以缺文件、hash 漂移、未知 Agent/capability 均在模型调用前 fail closed 的聚焦测试作为验证
- [x] 1.3 将 `live-us-equity/4.0.0` 暴露为 RETIRED/COMPATIBILITY_ONLY 并指向当前拓扑，保留其冻结内容和必要历史读取行为；以 profile hash、历史样本校验和当前 discovery 作为验证，不要求保留旧运行创建路径

## 2. Macro / Market 版本化能力拆分

- [x] 2.1 新增 `research-dimension-report/2.0.0` 与 `holding-research-bundle/2.0.0` schema，使用 `MACRO_CONTEXT` 和 `MARKET_STATE` 并保留 1.1 schema；以两版合法/非法样例的确定性契约测试作为验证
- [x] 2.2 更新多维研究 capability、stage、dispatch、invocation 和 execution proof 版本，使新运行只生成独立 Macro/Market 任务并分别记录状态；以任务索引、依赖、有界并行及单项失败隔离测试作为验证
- [x] 2.3 更新报告归集、coverage、渲染和只读消费路径以支持 2.0，并将历史 `MACRO_MARKET` 只标记为 legacy combined coverage；以历史 1.1 产物可读、新包不把旧报告自动判为两项 PASS 的兼容测试作为验证

## 3. 专业职责与研究输出

- [x] 3.1 更新 Market Catalyst 的 Agent/Skill 协议，使 `MACRO_CONTEXT` 与 `MARKET_STATE` 具有不同最低问题、输入边界和结构化输出，但仍使用同一现有 Agent；以版本/hash 绑定和 capability-specific prompt/Schema 测试作为验证
- [x] 3.2 按研究对象分派研报与新闻：Company Analyst 消费公司材料，Market Catalyst 消费宏观/市场策略正文；更新准备路由与相关权限，以正文身份、观点属性、对应 invocation 的真实引用及边界测试验证
- [x] 3.3 将当前拓扑映射接入材料准备和正式 dispatch，使两个 Market Catalyst invocation 各自锁定输入与 Evidence Gate 且可共享冻结资料；以 dispatch packet、MCP 允许集合和 invocation manifest 一致性测试作为验证

## 4. Provider 视图与状态文档

- [x] 4.1 在当前拓扑中接入既有 base/disclosure、official-macro、research-supplement 来源计划及能力矩阵，明确 Moomoo SG 的 loopback OpenD quote-only 边界；以逐 provider/dataset 状态、区域、限制和引用 hash 可解析测试作为验证
- [x] 4.2 将 provider 状态传递到本次研究 coverage 和缺口，确保 Moomoo 不可达时 SEC/Yahoo 继续工作且不会回退 Cookie/私有接口；以 AVAILABLE/PARTIAL/SOURCE_LIMITED/准确失败状态的聚焦降级测试作为验证
- [x] 4.3 更新 `docs/product/multi-dimensional-holding-research.md` 及相关当前入口说明，移除“延期至 `capture-futu-client-research-data`”的过期文字，改用能力矩阵与实际消费证据说明当前状态；以文档断言和人工对照四份 delta spec 作为验证

## 5. 三域资料获取与消费

- [x] 5.1 在实施新采集器前完成 Design 最低数据集覆盖清单，逐项列已有实现/历史验证/当前待验证、核心或增强、来源和请求预算；以字段、时间、证券范围及消费位置均可核对为完成依据
- [x] 5.2 核实 `wb-finance-skill` 原包，并逐项审计公开第三方归档 `infometa/workbuddyskills` 中的 `westock-data`、`neodata-financial-search`：锁定归档 commit、文件/脚本 hash、精确依赖与完整性、许可、端点、认证、费用和美股字段；逐数据集交付 ACCEPTED/NOT_VERIFIED/SOURCE_LIMITED/REJECTED 结论，可用者以有界真实返回验证，禁止直接执行浮动 `npx -y`/远程脚本、授予通用 shell，或以安装和 README 声明作为 PASS
- [x] 5.3 补齐 Macro 的经济活动、央行政策正文与发布日历，复用 BLS/Treasury；以真实响应、发布/观察/获取时间、修订处理、冻结 Evidence 和缺口记录验证，来源预算遵循 Design
- [x] 5.4 补齐 Market 的相关板块、至少两类跨资产序列、波动/信用指标或明确代理和 24 小时新闻；以真实采集、去重、时效、代理标识和同一 cutoff 的冻结输出验证
- [x] 5.5 为全部确认普通股补充公司公告/IR 和相关公司/行业研究材料的自动发现；issuer/IR 正文必须过滤目录型抽取、按实际正文身份去重并使 hash 对应可查询范围，分别记录指引、预期及外部观点；以逐股覆盖、原文定位、冻结工具可查询正文和独立正文/摘要/IR 分类验证资料准备，Agent 实际消费另由 7.3 验证；独立公开研报正文作为增强项，受限时保留实际尝试与影响
- [x] 5.6 将获准新增来源通过固定版本的确定性 adapter 接入现有资料准备、Gate 和冻结 MCP，保持三源 supplement 契约独立；以当前正式入口自动装配、最小网络 allowlist、查询隔离、时间过滤、冲突不静默覆盖和真实返回引用闭合验证，不依赖手工拼包，Agent 不直接执行第三方 Skill/CLI
- [x] 5.7 验证每个新增来源的故障隔离：超时、限流、认证失败、字段漂移和拒绝访问只降低对应数据集状态，不污染三源冻结包或阻断仍具合格输入的其他域；以故障注入和降级 coverage 聚焦测试验证

## 6. 旧 live 定向退役

- [x] 6.1 重新审计旧 live 代码、专属测试、文档与产物，按当前生产调用、历史只读/Replay、测试专用、零消费者列出精确符号、处置和恢复方式；交付可复核的逐项清单，排除无关目录、私人产物和有效验收证据，并识别被当前流程复用的 `live_*` 符号
- [x] 6.2 对 `prepare-live` 及旧创建/派发分支核实当前与 Replay 规格依赖；先将仍被当前流程复用的共享符号迁移到中性模块或等价实现，再只退役已证实零当前生产调用的部分；以旧入口在取数/模型前拒绝、当前入口前后基线一致、无悬空调用及必要历史读取有效验证
- [x] 6.3 收缩旧专属测试和过期入口说明，保留共享校验与历史兼容测试；以受影响测试、文档引用及实际保留功能对应关系验证，禁止按文件名前缀批量删除
- [x] 6.4 按审定清单处理可恢复且无有效引用的重复日志/中间产物，记录实际目标与恢复 commit 或备份位置；以引用复查、历史样本可读和处置记录验证，无安全候选时记录零删除结论

## 7. 聚焦验收与复核

执行顺序：先完成下列 7.2a–7.2e，再执行 7.3、7.4、7.5。已勾选的历史检查不覆盖新增行为；本次仅更新需求，新增项均待实施验证。

- [x] 7.1 在更改默认指针或删除旧分支前保存当前 Handoff 准备、采集/时间过滤、Gate/MCP、正式 dispatch、SEC/Yahoo/Moomoo 降级、1.1 历史读取和退役入口拒绝基线；变更后重跑 topology、2.0 stage、材料路由、浏览器兼容、provider supplement 与上述基线并对比结果，不自动启动 Eval/Regression
- [x] 7.2 运行受影响的聚焦确定性测试及 `check-multidimensional-consumption` 专项 validator，保存裸 `self-check` 被控制面拒绝的真实结果，并核对当前采集、共享校验和历史读取仍有效；不得把不适用命令记为 PASS
- [x] 7.2a 核实当前子 Agent 输出约束的实际生效边界，统一当前草稿/报告的嵌套结构定义并锁定版本/hash；以缺 question、额外顶层字段、limitations 类型错误、gap 缺 impact 的确定性样例和历史兼容验证，确保结构错误在渲染/正式保存前返回字段路径而非 KeyError
- [x] 7.2b 在既有执行链路实现原 Agent/原会话最多一次纠正，保留原始提交、反馈与纠正输出并完整重验；以一次成功、耗尽、不可续接/超时、重派不能重置预算、身份/越权引用拒绝及无静默补写验证
- [x] 7.2c 验证纠正中不提前解锁下游，上游有效报告保存后才推进，最终失败形成 dependency-blocked 且独立域继续；以确定性调度/Hook 检查证明终态齐全、报告有效与核心消费分别判断，父流程无缺失报告等待死锁
- [x] 7.2d 核对 v18 INDUSTRY_COMPARISON 引用失败归因，本次引入的回归修复并验证；既有且无关须保存可比基线、影响分析和准确失败状态，不豁免核心项或把全包失败声明为通过
- [x] 7.2e 在上述确定性检查通过后，按宿主 launcher 验证当前版本的 FUNDAMENTAL_EVENT → RESEARCH_REPORT 正式依赖链；若现有定点入口不支持，仅补该链所需最小选择能力；保持同一 Handoff/Gate/cutoff 与正式执行证明，禁止跨批次注入报告
- [x] 7.3 在已有授权适用范围内按宿主 launcher 执行一次当前版本的同批三域真实研究验收，证明同一 Handoff/Gate/cutoff 的 Company、Macro、Market 消费与新增资料引用；全部确认普通股的 Company 证据必须来自当前实现 hash，RESEARCH_REPORT 成功查询并引用去重后的 issuer/IR 正文及定位，独立研报保留已接受的 SOURCE_LIMITED；未运行或核心缺证据保持未完成，Demo、单任务成功、仅结构可解析不替代闭环，一次成功不宣称长期稳定，失败先归因不自动重复整批模型调用
- [x] 7.4 对变更规格、数据增量、免费来源观测、Skill 核实结论、退役清单及当前/历史兼容证据执行独立复核，确认无未闭合核心项、误删或新增无用基础设施
- [x] 7.5 汇总逐数据集完成/受限结果及退役结果，请求人工完成批准；独立研报等受限增强须明确接受，核心缺证据不得默认豁免，批准后才进入 sync/archive，Change 完成不代表 Promotion PASS
