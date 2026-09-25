## Context

动机见 proposal.md。已检查的具体接缝如下：

- `product/runtime/independent_skeptic_stage.py` 验证、归集正反报告并生成交接包，同时禁止原目录出现 CIO/Risk/decision；该限制继续有效。
- `product/schemas/runtime/pre-decision-research-package.schema.json` 已绑定 Handoff、Request、portfolio、Gate、cutoff、报告文件/内容哈希和执行证明；`complete_portfolio_decision` 固定为 false。
- `product/runtime/run_package.py:prepare_cio` 使用按 Agent 名称索引的旧报告，不能直接承载多个股票/维度，也依赖旧 fixture/live 输入形状。
- `product/.codex/agents/runtime_cio.toml` 仍要求固定两份报告及旧模式查询工具；新阶段需要显式分支，避免主线程重新派发已完成的 Specialist。
- `product/runtime/risk_runtime.py` 已提供 Risk 快照与前后置计算接缝，但 fixture 默认 Mandate、旧 live 焦点输入不应被当作新 Handoff 的账户事实。
- 可复用测试集中在 `test_independent_skeptic_stage.py`、`test_multidimensional_stage.py`、`test_live_cio_final_response.py`、`test_native_risk_runtime.py` 和 `test_risk.py`。不要求重建整个运行框架。

## Goals / Non-Goals

**Goals:** 以最小阶段适配实现“已验证 MRVL 研究包 → 主线程 CIO → 非动作研究综合”，并确保本阶段尚未验收的建议入口不可调用；保留旧消费者的版本兼容。

**Non-Goals:** 不实现当前组合建议、重新建仓建议、Risk 通过、全新通用工作流、回测引擎、交易执行、ETF/期权研究、多证券联合目标优化、自动补证循环、全站展示改版或泛化历史 Replay。未来建议/回测另行定义，不把本阶段报告冒充决策产物。

本轮收尾不新增全进程 OS 强制只读保证、权限探针平台或第二层沙箱；沿用原生沙箱及现有产品文件完整性检查。MD&A 冲突、估值、同行及公开研报等来源限制按现有内容验收解释，不要求补齐全部上游资料才能完成 CIO 接入。

## Decisions

### 1. 独立决策运行，显式引用研究来源

使用 `PREDECISION_CIO_SYNTHESIS` 阶段，通过现有宿主 launcher 暴露 `--stage predecision-cio-synthesis`，接收源研究运行目录、MRVL security_id、模型标识和新的外置运行目录。确定性 prepare/校验通过后才启动主线程模型。本 Change 只允许 `RESEARCH_SYNTHESIS`；`PORTFOLIO_ADVICE` 在宿主和直接准备入口均模型前拒绝，不能静默降级。只进行一次 CIO 综合，不增加第二个 Agent 或默认二次调用。

研究产物保留源 run_id；新 CIO 和 Trace 使用新 run_id。新 manifest 记录源 package/hash、源 Request、新研究 Request 与版本锁。冻结引用按原内容物化在新运行允许访问的输入区；验证器重验并建立显式跨阶段绑定，不全局放宽跨 run 校验，也不改写上游报告 run_id。源研究目录仍不允许写入 CIO 产物。

选择独立运行是为保持已归档研究契约和可恢复性。放宽原目录禁止规则会改变历史阶段语义，因而不采用。本次只实现显式消费已完成包；用户需要新资料时沿用现有上游研究入口。

### 2. 冻结研究上下文，不重新采集当前账户

准备输入仍绑定来源 Handoff/portfolio hash、MRVL 报告、Gate 与 cutoff，以证明研究包身份，而不把该历史 Handoff 解释为当前持仓。当前截图不作为本阶段 Risk 输入；用户无需补 SOXL 期权、现金、Mandate 或持有期限以运行原时点 MRVL 综合。研究期限由 CIO 标为分析假设，不能冒充当前用户持有期限。

研究报告仍区分已验证公司/市场事实、LLM 推断和未评估的账户适配。CIO 不从行情推断个人用款或风险承受力，也不使用 NO_TRADE 代替非动作研究。当前账户是否持有 MRVL 的变化不改写冻结历史来源。

默认以源研究 cutoff 输出该时点综合，实际生成时间另记。若用户另行要求当前行情研究，需要新上游包；CIO 不自动联网刷新，也不能把今天取得的新事实回填到历史 cutoff。

此前为持仓建议实现的 24 小时账户事实时效与可选 Mandate 校验不作为研究级完成前提；收敛建议代码时不得误删研究来源包的 PIT、hash 和 Evidence Gate 校验。旧建议逻辑若仅服务本阶段，应在 apply 中禁用并清理，不能以“未在 MRVL 调用”作为正式安全边界。

研究综合保留来源 coverage，不裁剪历史或当前资产来制造完整组合建议。现有包的 DOWNSTREAM_READY 条件原样复用，不新增从失败整包中提取单股的恢复系统。适用 Skeptic 为 INSUFFICIENT_EVIDENCE/TIMEOUT/失败时仍须先完成上游；合法辅助维度资料不足交给 CIO 解释，必需任务执行失败则停止。

### 3. CIO 消费目录按报告身份组织

输入保留完整 coverage 和实际报告清单：report_id、角色、security_id 或共享维度、invocation_id、content_hash、允许的 claim/challenge 标识、artifact_ref。读取源报告真实结构，不重新合成两份“兼容报告”。共享 Macro/Market 报告只保存一份，通过关联目标说明影响。

复用现有 frozen-gate Evidence MCP，为 CIO Invocation 授权该 Gate 允许集合；必要时可核实报告遗漏的同 Gate 事实。不得让适配层通过回退旧 live 模式访问 Provider、私人缓存或其他运行。CIO 可见组合私有上下文不反向注入 Analyst/Skeptic；本阶段不重跑或修订独立反证。

采用新阶段的版本化研究综合输出，复用现有 thesis、counter_thesis、conflicts、confidence_rationale、invalidation_conditions、reevaluation_conditions 等字段语义，补充报告身份和 challenge disposition。研究 Schema 不含动作字段；本阶段不扩展 canonical action contract，也不为六类内容问题各建独立 Schema 或新引擎。旧 fixture 按原 Schema 路由，不做历史迁移。消费目录由程序验证身份和引用；反证重要性及取舍理由由 LLM 和内容复核判断，不转成 Python 主观评分。

报告组织围绕六类问题：综合判断与期限；关键事实如何支持判断；正反核心分歧的取舍；宏观/市场到证券的具体传导；可观察的改变判断条件；优先观察项与重评事件。业务前景、价格吸引力、账户适配分开表达。资料不足时说明无法判断及其影响，不编造价格阈值或目标价，不强制凑条目。只是复述“增长良好但存在风险”不能通过内容验收。观察计划为静态文字，不创建后台监控。

### 4. 研究级隔离与建议入口退役

`RESEARCH_SYNTHESIS` 无 action、目标仓位、现金安排、金额或交易数量，标记 complete_portfolio_decision=false 和 Risk NOT_RUN，不使用 NO_TRADE 代表账户资料不足。研究判断可以偏积极，不能由程序映射为 HOLD、买回或加仓指令。当前代码已存在未完成真实验收的建议分支；仅把文档改成研究级不够，必须在宿主参数、直接 prepare/finalizer 和产品指令上共同关闭，并清理本阶段专用的无效代码/Schema，保留与其他入口共享的 Risk Engine。

研究级 finalizer 仅验证原报告、引用闭包、查询事件与模型证明，并生成研究结构/报告/Trace。来源 Handoff 的 hash 作为来源绑定，不转换成当前 PortfolioSnapshot；没有前后置 Risk 或模拟交易金额。关闭建议分支前需解析历史 advice run 的只读检查策略：历史产物可保留原样供审计，但本阶段新运行不能再生成 advice 终态，不能以重新解释旧 advice 文件为研究产物来迁移。

旧 fixture Council 的 Risk 依然是独立硬检查，本次不修改其投资风险政策。研究级报告可以解释经营/市场风险，但不得调用该引擎为 MRVL 当前账户适配背书。任何仍可从内层 CLI 直接启动的 advice finalizer 都是未关闭入口，需在实施和回归中捕捉。

选择显式关闭而不是只在当前 MRVL 请求中选择研究级别，是为了防止其他调用者误把合成 Advice 测试当作产品能力。避免建立通用“实验性建议模式”；需要时另起 Change，并重新定义支持资产、账户边界与真实验收。

旧固定两报告/fixture 路径保持原样。新阶段只复用研究报告、Evidence Closure、研究终态和中文渲染；系统失败不得伪装成合格研究报告。

### 5. 执行证明和最终产物

源包携带上游实际执行证明，新运行保存主线程 CIO 模型调用、有效模型标识、实际加载指令/Skill/Schema、查询事件及输出血缘。两个运行分别锁版本，不要求历史研究代码与新 CIO 代码相同，但源版本必须可核验、Schema 被明确支持。准备后输入或新运行代码发生漂移即停止。

研究综合使用结构化 `cio-research-synthesis.json`、同源 `report.md` 和带交付级别的 Trace，不生成 decision.json 或虚构 Risk。产物绑定来源包和每份消费报告。Trace 校验不要求新运行再次产生 Specialist 生命周期，也不伪造上游执行为本次执行。CIO 前阻断不生成虚构草案/Risk，CIO 后失败记录到达阶段和已有产物；系统错误不能降级成看似成功的研究综合。

宿主最终回复读取验证报告，直接展示判断、关键依据、主要反证取舍、观察条件和原时点/非持仓限制，并附报告链接；不展示 Risk 动作。不另行调用模型写第二份结论，不要求网页改版。最小实现为一个阶段适配加既有验证/渲染扩展，不增加通用工作流、消费登记服务或报告数据库。

失败后的重新执行使用新 CIO run_id，可复用仍有效的上游包；不新增自动模型重试、补证闭环或通用 checkpoint。

本轮证据闭环只扩展既有 `check-predecision-cio`：成功判定必须读取同一运行的 `invocation/process-result.json`，核对 `run_id`、进程退出码为整数 0、`timed_out=false`、`failure_code=null`、`stage_status=COMPLETED_RESEARCH_SYNTHESIS` 及 `source_integrity_unchanged=true`，字段缺失、类型非法或与 Trace 矛盾均拒绝 PASS。原有模型事件、指令锁、查询、引用及报告校验继续独立成立；进程结果不能替代这些证据。失败运行沿用既有失败语义，缺证据不得补造成成功。

沿用启动器在发布前检查退出、超时及受保护产品文件前后 hash 的顺序；进程结果在启动器完成后写出，事后检查在其后执行，不要求 finalizer 等待尚未生成的进程结果，不引入额外生命周期或事务框架。复用现有进程结果文件，不新增通用证明 Schema、服务或签名系统。

源码保护的验收口径为：保留原生沙箱，模型工作区位于仓库外，源码目录不被授予可写根，现有受保护产品文件清单在执行前后完整性一致，发现变化即拒绝成功发布。实际命令、执行事件和宿主完整性结果分别记录；命令配置与 hash 不被描述成操作系统强制只读实证。该保证不覆盖运行期间短暂修改后恢复、全部宿主进程或受保护清单之外的文件；全进程 OS 强制只读明确为 `UNVERIFIED`。本轮将原先含混的“源码权限证据”收敛到这一有限保证，验收记录须注明调整，不能将旧权限缺口改写成已获得 OS 证明。

### 6. 验收规模和模型选择

先聚焦测试关闭 advice 后的研究级入口及旧 fixture 回归，再对受影响版本通过宿主完成一次 MRVL CIO 研究综合 Smoke。开发测试默认 `gpt-6-luna`；若当前 CLI 不支持，仅用用户此前明确批准的 `gpt-5.6-terra` 做此冻结 MRVL 包的显式验收，不静默回退。记录实际模型身份、版本锁、外置工作区和上述有限源码保护证据；私有输入、完整输出均保存在仓库外。

真实样本必须展示关键反证的明确处置及对研究信心或结论的影响，不为满足测试编造冲突。独立复核逐项引用报告检查六类内容问题、遗漏的重大反证和虚假精确性，允许有依据的未知；字段非空或查询次数不代替内容验收。旧 MRVL Terra 研究报告与独立复核可作为历史证据，但阶段代码/指令锁更新后须补一次新宿主真实研究级 Smoke。测试需覆盖当前非持仓、旧来源 cutoff、无动作/decision.json/Risk、混合资产不影响研究，以及直接建议入口模型前拒绝。不重跑至预设观点，也不声称当前价格判断。

验收包括独立只读复核实际报告取舍和底层事件。无需启动 Runtime Eval、Regression、Ablation、Promotion 或历史回测；如后续明确需要这些，另行授权。通过本 Change 只证明真实研究综合链路，不证明持仓决策或盈利能力。

运行 `predecision-cio-298ab3e4-d4cc-4b42-b35e-35ea651ae7fb` 已有真实研究、Trace 和独立内容 PASS，作为检查器修复前的有效证据保留；不能因本次改文档而失效，也不能覆盖未来修改后的资源锁。新增确定性检查只覆盖进程结果正常、缺失、类型错误、失败及与 Trace 矛盾，以及既有有效产物仍可通过；复用未受影响的回归证据。实施若改变锁定的阶段代码，聚焦测试通过后补一次新版本宿主 MRVL Smoke，并对新进程证明及报告做独立复核；文档更新本身不触发模型。失败先定位原因，不自动重试或重跑至预设观点。

## Risks / Trade-offs

- [历史研究与当前账户分离] → 报告同时展示原 cutoff 与生成时间，当前 MRVL 非持仓适配标记未评估；不索取新账户来给旧研究补血缘。
- [用户未提供个人限制] → 研究级无需 Mandate；CIO 不推断个人偏好或自设仓位比例。
- [混合资产未被研究或风险模型支持] → 不运行完整组合建议或裁剪 ETF/期权；MRVL 研究继续使用已验证来源包。
- [旧 CIO 报告索引和 Trace 隐含固定两角色] → 按阶段引入报告身份映射与来源证明，测试旧 fixture 不回归。
- [正反报告很长或存在严重分歧] → 通过现有受限文件/工具读取结构化目录和原报告，允许按需读取，保留消费记录；超出能力时明确失败，不以机械摘要或截断伪装已消费。
- [研究截止点与发布时点相隔较久] → 报告突出两个时间和历史研究性质；需要当前研究时重做上游。
- [代码中残留未验收 advice 分支] → 宿主和直接 CLI 模型前拒绝并清理专用分支，聚焦回归旧 fixture Risk；不能只靠用户本次没有点选该参数。

## Migration Plan

1. 以新显式阶段和版本化契约接入，保留旧 fixture、研究阶段及源包 Schema。
2. 聚焦验证新阶段与受影响旧路径，更新 Skill、CIO 指令、宿主帮助与运行手册。
3. 禁用本阶段建议入口并清理仅服务该分支的代码/Schema/文档，聚焦测试和真实宿主 MRVL 研究级 Smoke 后独立复核，再申请人工同步归档批准。
4. 回退时停止使用新阶段即可；不迁移或重写历史研究包，不修改候选生产指针。
5. 收尾提交前识别 CIO 对共享模型路由函数的必要依赖，按已审阅范围纳入并核对导入完整性；保留 Tiger 等无关修改。主规格同步、最终人工批准、归档及提交推送沿用现有开发流程，不新建发布系统。
