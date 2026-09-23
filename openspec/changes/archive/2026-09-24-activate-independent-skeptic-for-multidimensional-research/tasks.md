## 当前执行边界

本 Change 已完成范围内实现、聚焦确定性验证、MRVL 真实纵向验收和只读 Change 复核；失败运行与最终通过运行均保留在仓库外验收目录。2026-09-24 已获得人工同步归档批准；不新增补查询再提交、自动研究重试、CIO、Risk、回测或 Promotion。

## 1. 阶段与交接契约

- [x] 1.1 在 `CouncilRequest v2`、规划器和产品入口中增加显式 `INDEPENDENT_COUNTER_THESIS_RESEARCH` stage，保持既有 common-stock 与 multidimensional stage 行为不变；以请求 Schema/绑定/阶段枚举聚焦测试验证合法选择和未知阶段 fail closed。
- [x] 1.2 定义并版本锁定 `PreDecisionResearchPackage/1.0.0` Schema，覆盖 run、Handoff、Portfolio、Request、cutoff、Gate、正向 bundle、逐证券 Counter Thesis、全持仓 coverage、consumability、artifact refs 和 package hash；以正常、缺报告、跨 run/cutoff、hash 漂移和多资产样例测试验证。
- [x] 1.3 实现正反研究交接包验证与同源中文渲染，只引用原报告而不复制或综合观点；以渲染一致性、悬空引用、历史 bundle 不改写和越界 CIO/Risk 产物测试验证。
- [x] 1.4 更新 `portfolio-council` Skill、Agent Package/version manifest 和必要产品说明，使新阶段、输入隔离、停止点及“`DOWNSTREAM_READY` 不代表研究质量通过”可被发现；以产品配置和 Skill 契约测试验证旧 `live-us-equity` 入口未恢复。
- [x] 1.5 将新阶段报告最小升级为 `CounterThesisReport/2.1.0`，增加报告内 assumptions 定义并验证 ID 唯一及 challenge 引用闭合，保留旧 2.0.0 版本读取；用未定义假设、重复 ID、纯假设情景及旧报告验证测试阻止空造 ID 绕过依据要求，Agent/Skill 对齐事实引用、假设说明及系统失败边界。

## 2. 同一运行的正向研究门禁

- [x] 2.1 让新 stage 在一个全新 run 中复用既有资料准备、多维任务规划、派发和 `HoldingResearchBundle` finalizer，并保存实际 phase 进度；以新旧 stage 对照测试验证 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 仍不会启动 Skeptic。
- [x] 2.2 增加独立反证前置验证，要求本次 bundle 为 `DOWNSTREAM_READY`，且适用的 Company、Technical、Fundamental/Event、Industry、Macro、Market 核心 coverage 不得为 `FAILED`、`TIMEOUT`、`NOT_RESEARCHED` 或依赖阻塞；以 MRVL 形状 fixture、核心失败和专项 `SOURCE_LIMITED` 样例验证门禁不会混淆结构可读与研究就绪。
- [x] 2.3 对正向 bundle、Gate、Handoff、CouncilRequest 和证券身份执行同 run/cutoff/hash 复核，禁止从 Research Memory、历史运行或不同临时目录补齐；以当前 v2/v4 类跨运行反例测试验证 Skeptic 在派发前即被阻止。

## 3. Independent Skeptic 逐证券阶段

- [x] 3.1 实现逐普通股 Skeptic Evidence scoping，从本次 Gate 选择目标证券、共享 Macro/Market、冻结关系中相关同行公开事实及来源闭合的身份/计算资料，不查看正向报告引用集合，也不泄露成本、浮亏、数量或现金；保留资料选择限制，缺资料仅记录 gap。以单股、多股、同行同时为持仓、共享 Evidence 和计算附件测试验证边界。
- [x] 3.2 建立精确字段白名单的 `INDEPENDENT_FIRST_PASS` 输入、逐证券 run-scoped output schema 和 Invocation Manifest，扩展隔离校验以拒绝报告/bundle 内容、摘要、未解决问题、hash、Artifact References 和 Agent/CIO 结论；以嵌套污染和合法非结论性上下文测试验证派发前 fail closed。
- [x] 3.3 生成全量逐证券 dispatch index、稳定 task 映射、prompt 和有界并发宿主调度，复用 `runtime_skeptic` 与现有 Hook/只读 MCP，不新增 Agent 或 Python LLM 编排器；以多证券生命周期、并发补位、错误 agent/task 和未终止子任务测试验证。
- [x] 3.4 按逐证券路径原样保存 `CounterThesisReport` 草案和中文报告，复用 Schema、身份、Skill、PIT、Evidence Closure 及一次纯格式修复；以 `COMPLETE`、`LOW_CONFIDENCE`、`INSUFFICIENT_EVIDENCE`、`TIMEOUT`、悬空 Evidence 和非法结构测试验证领域状态与系统失败分离。
- [x] 3.5 生成 Skeptic execution proof 和最终 `PreDecisionResearchPackage`，验证每只适用普通股的 Invocation、非空 Evidence 工具调用、输入隔离、报告 hash 与全持仓 coverage，并确认 manifest 持续为 `complete_portfolio_decision=false`；以缺证券、伪造工具事件、跨 run 输出和完整正反包测试验证。
- [x] 3.6 扩展现有只读 MCP 的单 focus/固定文件绑定，按可信 dispatch index 解析 run/task/invocation/security 并在服务端限制本次允许集合；复用现有计算读取接缝，以同角色两证券越权、Invocation 冒用、任意路径和有效共享/同行/计算查询验证真实权限，而非仅校验输入 JSON。派发使用不继承父会话的独立上下文。
- [x] 3.7 对齐交接状态：COMPLETE 和已完成研究的 LOW_CONFIDENCE 可进入普通股 DOWNSTREAM_READY；INSUFFICIENT_EVIDENCE、TIMEOUT、未返回报告和系统失败只作部分交接，非普通股缺口独立展示。以状态组合测试验证没有报告时不补写、超时不冒充完成；中文正文忠实呈现原挑战、依据、假设和推翻条件，交接摘要链接原报告，不增加自动评分、LLM 综合或网页扩建。

## 4. 宿主入口与聚焦验证

- [x] 4.1 扩展 `scripts/council-dev.py` 和 `scripts/run-product-smoke.sh` 的显式 stage/恢复入口，使新阶段只能通过宿主 launcher 运行并使用新的外置目录；以参数、目录保护、准备、恢复和旧 stage 回归测试验证。
- [x] 4.1a 明确首次运行新建目录，同一冻结运行恢复仅续跑未完成/失败任务；每次恢复每个目标最多一个新研究尝试，保存独立 attempt/Invocation 和输出，保留原始失败及成功产物并显式登记采用结果。以成功 hash 不变、重复恢复、输入/版本漂移、未终止任务和尝试引用测试验证，输入或版本变化必须新运行，不新增重试调度器。
- [x] 4.2 运行受影响的确定性测试（至少覆盖 intake planning、multidimensional stage/contracts、Invocation 隔离、Hook/launcher、Schema/渲染及产品配置），保存实际命令与结果；任何失败修复后重跑对应聚焦集合，不隐式启动 Runtime Eval、Replay、Regression、Ablation 或 Promotion。
- [x] 4.3 运行 `openspec validate activate-independent-skeptic-for-multidimensional-research --strict` 与适用于本阶段的聚焦版本锁、产品发现和确定性安全检查，记录实际命令及结果。当前 `self-check` 只支持需既有运行的 check-run/trace-check，不调用无参数 self-check，也不为通过检查启动完整 Council 或新增通用检查框架。

- [x] 4.4 优先修复终止识别与身份封装：用可信派发、Start 子会话映射和最终 Stop/执行结果区分结束与成功；唯一绑定时封装缺失技术身份，冲突或多义必须拒绝。覆盖漏身份、伪造/跨任务身份、格式修复尚未结束、失败释放槽位、依赖失败及所有任务已结束但报告部分失败，验证父流程有限收尾而非等到总超时；保留原始草案、成功产物及失败清单。
- [x] 4.5 修正 Macro/Market 的单股与多股 Prompt/Skill 契约：单股解释自身敏感性、假设及反向情景，多股才比较持仓差异；同行只用既有授权资料。以单股 MRVL、多股和真实资料缺口样例验证，不因缺第二持仓判不足，不自动补入公司或改领域状态。
- [x] 4.6 统一精确 Evidence 引用交付：优先复用工具返回完整 ID，对齐 schema/提示/工具输出；若采用短引用，仅允许预先冻结的 Invocation 内一对一映射并验证还原后闭合。覆盖错拼、截断、未知、歧义、跨 Invocation 和有效引用；不得模糊修复或删主张，区分 closure 与实际查询检查，不增加补查询重试。
- [x] 4.7 将本次失败草案和事件形状脱敏为确定性测试，覆盖 4.4–4.6 的组合；至少增加一个不 mock `validate_forward_gate` 的正向包到 Skeptic 准备/交接验证集成样例，覆盖合法同源输入和不合法核心报告被阻止。重跑受影响聚焦测试、旧阶段回归及版本锁/OpenSpec 校验；记录新结果而不沿用 257 项通过声称新增修复通过。不调用模型，不运行 Execution Replay；同步更正验收说明中的错误根因推断，保留历史原始证据。

## 5. MRVL 真实纵向验收与复核

前置条件：4.4–4.7 完成且获得实施/运行授权。已有失败运行仅作为诊断依据，不因文档更新而成为通过证据。

- [x] 5.1 通过宿主 `scripts/run-product-smoke.sh` 在新的外置目录对已确认 MRVL Handoff 执行首个 `INDEPENDENT_COUNTER_THESIS_RESEARCH` 样本，重新冻结同一 cutoff 的资料并保留命令、模型、数据来源和工具事件；不拼接既有 v2/v4 报告。失败允许显式有界修复/续跑，输入或版本变更则新运行，不自动扩张样本集，不以“一次运行”接受未完成结果。
- [x] 5.2 对 MRVL 运行执行确定性阶段验收，确认正向核心报告合法、Skeptic 输入不含正向结论且发生非空 Gate-scoped 查询、Counter Thesis 引用闭合、交接包为 `DOWNSTREAM_READY`，并确认不存在 CIO、Risk、`decision.json`、Outcome 或回测产物；保存产物路径和完整 hash。
- [x] 5.3 开展一次独立只读 Change 复核，逐项核对实际差异、三个 delta spec、MRVL 底层产物、隔离证明、失败分类和旧 stage 回归；将发现的问题在原范围内修复并重跑受影响检查，形成明确 `CHANGE_REVIEW` 结论而不声明 Candidate Promotion。
- [x] 5.3a 对 MRVL 反证正文作独立人工内容复核，逐项对照原始 Evidence 检查公司特定性、事实支持、假设标注、传导逻辑、待补证据及可观察推翻条件；允许充分核验后未发现强反证，不强制挑战数量、不同观点或固定结论。非空查询和合法 Schema 不替代此复核；TIMEOUT/INSUFFICIENT_EVIDENCE 不满足首次真实研究完成验收，不新增自动语义评分或 Runtime Eval。
- [x] 5.4 更新本 Change 的任务勾选、验收记录和必要运行手册说明，检查工作区只包含已审阅源码/需求增量且不包含凭据、私人会话数据库或未脱敏持仓截图；达到人工完成批准前保持 Change 未归档、未推送。

  已确认范围内文件不含凭据、私人会话数据库或未脱敏持仓截图；暂停中的 `integrate-tiger-hk-readonly-portfolio-and-trade-review` 改动按独立 Change 保留，并在本次提交中按路径及差异范围隔离。
