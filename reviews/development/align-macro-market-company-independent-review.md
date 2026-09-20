# Macro / Market / Company Change 独立复核记录

日期：2026-09-20
Change：`align-macro-market-company-research-inputs`
结论：`CHANGE_REVIEW: PASS`
候选晋升：`CANDIDATE_PROMOTION: NOT_PROMOTABLE`

本文记录 Change 级只读独立复核及复核后补证，不构成 Runtime Eval、Regression、Promotion 或人工完成批准。

## 用户已接受的受限增强

用户明确接受公开独立研报正文维持 `SOURCE_LIMITED`。该接受只覆盖独立公开研报全文这一增强项，不豁免 issuer/IR 正文、三域真实消费、Evidence Closure、provider 隔离、历史兼容或旧 live 退役。

## 首轮独立复核发现

1. v9/v11 的 `RESEARCH_REPORT` 均未形成合法报告；v11 只证明 `STRUCTURALLY_CONSUMABLE`，且 `downstream_models_started=[]`，不能证明修复后的 Company 正文被正式消费。
2. SEC issuer material 投影把同一 filing 的目录标题和真实 MD&A 都标为独立 `BODY_VERIFIED`，并以整份 filing raw hash 作为正文 hash，虚增正文覆盖。
3. Task 7.2 勾选了裸 `self-check`，但控制面实际返回 `SELF_CHECK_COMMAND_NOT_ALLOWED`；任务文字与证据不一致。
4. 数据集清单把公开独立研报发现/全文列为 CORE，与可接受受限增强的边界不一致。
5. Market 实时 snapshot cutoff 只覆盖 Evidence `retrieved_at`，未覆盖零结果新闻请求的完成时刻。

复核同时确认：provider 聚合、Moomoo OpenD quote-only 与 Cookie/私有 API 禁止边界、v1.1 兼容、旧 `prepare-live` fail-closed、WorkBuddy 候选未误接入、无凭据或交易写能力等项目没有发现阻断问题。

## 已完成修复

- issuer 正文投影过滤短目录型抽取；同一 filing/semantic field 只保留最长的实际正文范围；`body_hash` 改为绑定实际可查询正文文本与定位范围。基于原 v5 Gate 的零模型 v13 准备结果从 4 份虚增文档收敛为 2 份真实 MD&A，raw filing hash 与正文 hash 分开保存。
- Market 实时 snapshot cutoff 现在同时覆盖 Evidence 获取时间和全部请求事件完成时间；显式历史 cutoff 仍保持严格不变。
- OpenSpec Proposal、Specs、Design、Tasks 及数据集清单已把 issuer/IR 正文列为 Company 核心，把公开独立研报发现/全文列为 ENHANCEMENT；5.5、7.3 已退回未完成，7.2 改为实际适用的专项 validator。
- 多维输出校验新增明确的 claim `question`/`statement`/`kind` 和 data gap `reason_code`/`description`/`impact` 检查；冻结任务指令明确顶层字段、字符串 limitation 与 gap 对象边界，不再让缺字段以原始 `KeyError` 进入渲染阶段。

## 补证结果与已关闭阻塞

- v13 首次宿主启动因受限沙箱内 app-server `Operation not permitted` 失败；v14 起使用获准宿主 launcher，失败证据均保留且未覆盖。
- v16 对 `dimension_research_2` 的定点宿主运行通过，`FUNDAMENTAL_EVENT` 为合法 `LOW_CONFIDENCE`，Gate hash 为 `e9c9c2a03c3f51eaf78e4a1ba8199d1fdbf36fca13fa9e22be90c6347b9be557`。该结果只证明单任务 Company 基础研究，不证明依赖的 `RESEARCH_REPORT`。
- v18 使用同一 Handoff、Gate 和当前 issuer 投影形成合法 Macro 与 Market 报告；Company draft 的一个 `data_gaps` 项缺少 `impact`，因此 `FUNDAMENTAL_EVENT` 被拒绝，`RESEARCH_REPORT` 以 `MULTIDIMENSIONAL_UPSTREAM_DEPENDENCY_FAILED` fail-closed。v18 `all_reports_valid=false`，不能作为 Task 7.3 完成证据。
- 运行器当前不支持把 v16 的独立任务报告跨批次注入 v18 依赖链；为通过验收临时复制报告、伪造 Hook 或放宽 schema 都会破坏正式证据，未采用。连续完整模型重试也已停止，避免用随机成功掩盖输出契约不稳定。

### v18 Industry 失败归因与收敛

v18 的 `INDUSTRY_COMPARISON` 只有 NASDAQ 目录形成的 `UNVERIFIED` 候选，没有完成身份核验、资料取得和 PIT 冻结的 `selected_peer_candidates`，因此任务输入中没有任何同行 Evidence。模型仍基于目标公司 Evidence 生成比较主张，确定性校验以 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 正确拒绝。该失败不是 SEC issuer 投影或同行去重回归，而是“没有冻结同行时不得产生比较主张”的边界此前只写在提示词、没有进入输出契约。

当前实现把这条边界收敛为动态 schema：没有冻结同行时 `claims.maxItems=0`，同时要求用 `data_gaps` 记录缺少可比较同行 Evidence 的原因与影响。若模型首次违反，仍只允许原 Agent、原 session 依据同一 schema 做一次有界结构修复；若同行已物化，则恢复正常 claims 契约，不压缩正式比较能力。

### 确定性收敛结果

- 当前 v2 最终报告契约、子 Agent 草稿 schema 版本及 hash 已在拓扑、invocation、dispatch packet 中一致锁定；缺 `question`、额外顶层字段、错误 `limitations` 类型和 gap 缺 `impact` 均在保存前返回字段路径。
- 结构失败只允许原子 Agent 会话纠正一次；原始提交、反馈、第二次输出和终态均进入追加式审计。重复派发同一任务不能重置预算，身份/引用越权不进入纠正通道；纠正不可续接时最终证明保留非终态失败，不解锁依赖。
- 新增的定点入口选择目标任务及其最小依赖闭包。确定性测试证明 `RESEARCH_REPORT` 提前派发会被拒绝，只有同一批次保存合法 `FUNDAMENTAL_EVENT` 后才解锁；该入口不生成完整三域研究包，也不允许跨批次注入报告。
- 在无符号链接的 `/private/tmp` 下执行受影响的 155 项测试全部通过；默认 macOS 临时路径下曾有 1 项旧 launcher 测试因 `/var` 祖先符号链接被既有安全规则拒绝，换用等价真实路径后通过，未放宽路径规则。OpenSpec strict validation 与 `git diff --check` 通过。

### v19/v20 Company 正式依赖链

- v19 在受限进程内启动宿主 app-server 时以 `Operation not permitted` 失败；`process-result.json` 记录 `MULTIDIMENSIONAL_CODEX_PROCESS_FAILED`，源码完整性未变化且没有子 Agent 派发。该失败作为环境证据保留，未覆盖或改写。
- v20 使用 v18 相同的 Handoff、Gate、`decision_cutoff` 和 Gate hash `e9c9c2a03c3f51eaf78e4a1ba8199d1fdbf36fca13fa9e22be90c6347b9be557`，通过宿主 launcher 只运行 `dimension_research_3` 的最小闭包。`FUNDAMENTAL_EVENT` 首稿因 `$.data_gaps[0].claim_refs` 额外字段被拒绝，同一 child session 在唯一一次纠正中保存合法 `LOW_CONFIDENCE` 报告；随后 `RESEARCH_REPORT` 才启动并保存合法 `SOURCE_LIMITED` 报告。
- `research/task-execution-proof.json` 为 `PASSED / DEPENDENCY_CHAIN_EVIDENCE`，`dependency_chain_complete=true`，同时明确 `complete_holding_research_bundle=false`、`downstream_models_started=[]`，没有把定点链证明冒充三域闭环。
- `RESEARCH_REPORT` 实际引用两份去重后的 `BODY_VERIFIED` SEC issuer 正文，保留各自 `body_hash`、SEC URL、`management_discussion` 与 `gate-evidence:<evidence_id>` 定位，并通过 `research_relationships` 连接到同批上游 claim。独立研究正文为零，报告保留具体 `SOURCE_LIMITED` gap；这符合用户已接受的增强边界。由此 5.5 的逐股资料准备与 7.2e 的正式依赖链已有当前实现证据，但完整同批三域验收仍待 7.3。

### v21 同批三域真实验收

- v21 通过宿主 launcher 在同一 Handoff、Gate hash `e9c9c2a03c3f51eaf78e4a1ba8199d1fdbf36fca13fa9e22be90c6347b9be557` 和 `decision_cutoff=2026-09-19T16:51:56.453074Z` 下完成 8/8 调度终态，Finalizer 返回 `PASSED`，`all_reports_valid=true`、`coverage_complete=true`、`failed_tasks=[]`。
- Company 的 `FUNDAMENTAL_EVENT` 首稿缺少 gap `reason_code/impact`，同一 child session 一次纠正后保存；`RESEARCH_REPORT` 只在其后启动，并实际引用两份去重后的 issuer 正文、正文 hash、SEC URL、Gate 定位及同批上游 claim。独立研报保持具体 `SOURCE_LIMITED`，没有被冒充为已读正文。
- `MACRO_CONTEXT` 与 `MARKET_STATE` 分别形成独立报告，使用同一 cutoff 且 Evidence 集合、最低问题、缺口和执行 hash 分离。Macro 使用官方宏观事实和 MRVL 公司事实；Market 使用冻结的广泛市场计算、市场/公司 Evidence 并保留信用代理与新闻正文缺口。
- v18 Industry 失败的收敛在真实批次得到验证：没有冻结同行时 `INDUSTRY_COMPARISON` 一次通过、`claims=[]`，并以具体 data gaps 表达未物化同行资料，没有再产生未落地比较主张。
- `check-multidimensional-consumption` 返回 `PASSED / STRUCTURALLY_CONSUMABLE`，实际解析 8 份报告的 claims、Evidence、calculations、data gaps、research relationships 和 observation conditions；`complete_portfolio_decision=false`、`downstream_models_started=[]`，本次验收不冒充 CIO 决策、Eval、Regression 或长期稳定性证明。

### v22 当前版本复核

- 最终静态复核发现 `product/version-manifest.json` 已声明 `runtime-market-catalyst=1.2.0`，运行时常量仍为 `1.1.0`。当前实现已统一为 `1.2.0`；v22 的 run manifest 锁定该版本，Agent content hash `e73f91a7...f3d7`、Options Skill content hash `77c3e6fe...b456c` 和 topology lock hash `9671b076...dcd9` 与 v21 一致，没有用版本号漂移掩盖内容变化。
- v22 通过宿主 launcher 在同一 Handoff、Gate hash 和 cutoff 下重新执行当前实现。Company 的 `FUNDAMENTAL_EVENT` 与 `RESEARCH_REPORT` 均一次形成合法报告；后者只在上游保存后启动，引用两份去重的 `BODY_VERIFIED` issuer 正文并保留 SEC URL、正文 hash、Gate locator 和同批上游关系。Macro 与 Market 各自形成合法报告；无冻结同行的 Industry 报告继续保持 `claims=[]` 和明确 gap。
- 本批最后一个 `OPTIONS_FLOW` 子任务在父进程退出前缺少 Stop Hook，Finalizer 准确记录 `MULTIDIMENSIONAL_SUBAGENT_TERMINAL_EVENT_MISSING / START_WITHOUT_STOP_AFTER_PARENT_EXIT`。因此 v22 为 7 份有效报告、`all_reports_valid=false`，不得声明为 8/8 或全包成功。定向恢复被既有一次启动保护以 `MULTIDIMENSIONAL_ALREADY_LAUNCHED` 拒绝；没有复制报告、改写 Hook、放宽门禁或重复整批模型调用。
- 该期权失败不属于本 Change 的 Macro / Market / Company 核心资料，也不是本次改动引入的引用失败。v21 已在相同 Handoff/Gate/cutoff、相同 Agent/Skill content hash、相同 topology/schema 下形成合法 Options 报告和 8/8 全包证明；依照“实现版本及契约仍适用时可复用已有证据”的规格，复用该项历史成功证据。v22 仍保留当前失败状态，不把启动器 `PASSED` 覆盖为报告全有效。
- v22 的只读消费检查返回 `PASSED / STRUCTURALLY_CONSUMABLE`，解析 7 份有效报告并保留 Options `FAILED` coverage；`complete_portfolio_decision=false`、`downstream_models_started=[]`。这证明当前三域核心包可消费，不构成 CIO 决策或全包成功声明。

## 最终独立复核结论

- 规格、Design、Tasks、数据集清单和实现对 Company / Macro / Market 的核心与增强边界一致；三域核心均有实际获取、PIT/Gate、冻结查询与正式引用证据。公开独立研报正文按用户已接受范围维持 `SOURCE_LIMITED`，没有被 issuer/IR 正文替代。
- `wb-finance-skill` 原包未取得；`westock-data` 与 `neodata-financial-search` 只完成锁定归档候选审计，结论为 `NOT_VERIFIED`、`SOURCE_LIMITED` 或 `REJECTED`。产品代码没有直接执行第三方 Skill/CLI、浮动 `npx -y` 或远程脚本，也没有把候选说明当成取数成功。
- Moomoo Singapore 仍限 loopback OpenD quote-only；不可用只降低补充层，不阻断 SEC、Yahoo 或官方宏观来源，也未回退 Cookie、私有接口、账户或交易能力。
- 旧 `live-us-equity` 新运行入口在任何取数、网络或模型调用前 fail closed；共享采集、Gate、历史 schema/Replay 读取仍保留。审计未发现可安全删除而又不影响当前或历史消费者的额外实现，本 Change 没有删除文件，也没有新增第二套编排器或通用重试基础设施。
- 最终代码执行两组聚焦与兼容检查共 286 项（124 + 162）全部通过，覆盖多维 stage、拓扑、Macro/Market、资料准备、当前配置、普通股历史契约、旧 profile、Portfolio Skill、嵌套 launcher、fixture MCP 与 Evidence Gate。此前全仓 1,061 项运行结果为 12 failures、24 errors、22 skipped；其中本 Change 直接暴露的工具面和历史错误码兼容问题已修复并在上述集合通过，剩余为既有 demo 配置、缺依赖、归档样本、候选版本/assurance hash、promotion 与 research-memory 环境问题，未伪装为全仓 PASS，也不纳入本 Change 扩围修复。
- 凭据扫描未发现提交的 key、token、Cookie、私人会话数据库或联系邮箱；差异中无删除文件。OpenSpec strict validation、配置引用/hash 校验和 `git diff --check` 均作为最终静态门禁执行。

综上，未发现未闭合的本 Change 核心项、误删、无用基础设施或历史兼容回归，独立复核结论更新为 `CHANGE_REVIEW: PASS`。该结论不改变 `CANDIDATE_PROMOTION: NOT_PROMOTABLE`，也不替代人工完成批准。

## 剩余归档门槛

1. Company Agent 在当前代码 hash 下稳定形成合法 `FUNDAMENTAL_EVENT`，并在同一 Handoff/Gate/cutoff 的正式依赖链中解锁 `RESEARCH_REPORT`。
2. `RESEARCH_REPORT` 必须真实引用去重后的 issuer 正文，复制锁定的 document metadata，并保留独立研报 `SOURCE_LIMITED` 边界。
3. 已重新执行独立复核并取得 `CHANGE_REVIEW: PASS`。
4. 仍须请求完整人工完成批准；在此之前不得 sync、archive、commit 或 push。
