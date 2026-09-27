## Context

归档时状态（2026-09-27）：用户在边界修补完成后批准继续补跑；累计上限为 8 次产品子 Agent 调用，已用 8/8。本次仅以同一冻结 MRVL 输入经既有宿主入口运行 `FUNDAMENTAL_EVENT → RESEARCH_REPORT`，各一次。两项均保存、任务级 `PASSED`；公开 Company 线索 11/11 实际查询，1 条与研究问题相关的原样 Evidence ID 被有效 `SOURCE_LIMITED` claim 引用，仍未获得独立研报正文。Market/Macro 本轮未运行，完整八维报告未生成。最终独立只读复核对本 Change 的定点来源/消费验收给出 PASS，用户随后明确批准同步且归档；以下第 3–7 节的调用计数记录各次决策当时的状态，本次结果不追认旧报告对公开线索的使用。

见 [proposal.md](proposal.md)。现有 `moomoo-opend-quote-manifest.json`、`MoomooOpenDQuoteClient` 与 `research_supplement_collection` 已覆盖 8 个固定美国宏观系列、Economic Calendar、FedWatch、Dot Plot、涨跌分布和全市场期权统计；`MACRO_CONTEXT`/`MARKET_STATE` 已有对应路由和一次 MRVL 实际消费证明。2026-09-26 新来源检查中 OpenD 补充不可达；本次最小试验进一步观察到：OpenD 在 `127.0.0.1:11111` 监听、匹配的 SDK `10.10.7008` 存在，但当前 Codex 沙箱内 SDK import 要写 `/Users/caihaoming/.com.moomoo.OpenD/Log/`，发生 `PermissionError`，随后被客户端归类成 `MOOMOO_OPEND_UNREACHABLE`。这证明本次阻断是 SDK 初始化权限，不能证明 OpenD 服务或数据本身失败；不反推此前所有失败均为同因。

公开 `moomoo-news-search` Skill 通过 `GET https://ai-news-search.moomoo.com/news_search` 返回 `news_id/news_type/title/publish_time/url/img_url`，不返回正文。MRVL 的 `Research` 结果含评级快讯和第三方转引；公司名公告搜索存在同名误命中。个人 Codex Skill 不自动加载到产品 Runtime。现有 Yahoo `market_news_item` 已按 24 小时、`TITLE_ONLY`、PIT 和原始链接冻结；研报准备阶段的 `research_search/fetch` 仍是 OpenAlex，不能把新标题源伪装成可 fetch 的正文候选。

## Goals / Non-Goals

**Goals:**
- 用现有 Quote 路径复验数据集，给出环境权限、接口、Gate、Agent 消费各层的真实状态，并只修确认的最小故障。
- 给 Company 和 Market 添加一个与 OpenD 身份分离的公开标题线索来源，减少无新闻线索时的盲区，但保持正文及官方资料层级。
- 让宿主权限与真实验收需要在执行前可见；用户本次授权可用于发起最小范围只读检查或权限申请，但只有系统实际授予/宿主实测成功才算就绪。

**Non-Goals:**
- 不重新实现已接通的 Moomoo 宏观/市场方法，不升级 SDK/OpenD 锁，不新增 Agent、编排器或任意网页爬虫。
- 不修复独立的 `RESEARCH_MATERIALS_ARTIFACT_REF_INVALID`，不把新闻 Skill 变成研报全文服务；不做历史回测、交易建议、账户或 Trade 接入。

## Decisions

### 1. 权限和可用性采用最小宿主路径

实施先核对已安装 venv 的 SDK 版本、既有 OpenD 监听、SDK 日志目录和 Quote readiness，再对已允许的方法做有界读取。优先从已有宿主 Terminal 以用户当前权限运行，不改 SDK、不重设 `HOME`、不开放整个用户目录；若须 Codex 沙箱授权，只针对 SDK 自身日志目录提出写入权限请求，运行产物仍在仓库外临时目录。实际授权被拒绝就停在 `ENVIRONMENT_BLOCKED`，报告精确的脱敏阶段；不把 SDK import 的 `PermissionError` 合并为网络不可达。既有 `MoomooOpenDQuoteClient` 仍是唯一 Quote 调用边界，不直接绕到任意 SDK 方法。

取舍：临时“改 HOME”或复制 SDK 能让探针通过，但改变环境语义并掩盖运行时真实权限，故不采用。文档中的用户同意不是系统级权限；不得在未获工具/OS 放行时宣称成功。

### 2. 公开新闻搜索只做最小元数据采集

用一条有界、无认证的公开 HTTP 路径复用现有快照缓存、PIT/Gate 和 coverage，不依赖个人 Skill 出现在产品 Agent 会话，也不修改 OpenAlex 正文 fetch。数据源标识使用独立的 `moomoo_public_news`，如现有 provider 枚举要求，做最小枚举/来源政策扩展。保存原始响应 hash、清洗后的标题、原始及规范 URL、`news_type`、`publish_time`、`retrieved_at` 和排除原因；不保存未经许可的文章正文。单证券至多一次 ticker 查询、必要时一次发行人名称查询；每次最多 10 条；Market 至多一次市场主题查询。失败或零相关候选不循环换词；公开 endpoint 的可用性与许可不作为长期 SLA。

候选映射：公司/证券身份明确的公告与评级进入已有 `research_discovery` 线索范围；SEC/IR 仍是事件事实锚点，OpenD Morningstar section 仍是另一个已授权的供应商资料层。Market 仅在 Yahoo 24h 新闻无合格结果时消费相关、时点可证的标题，沿用 `market_news_item` 的 `TITLE_ONLY` 限制。Macro 新闻不取代官方实际值或政策正文。对 `news_type=3` 保留原始类别和“评级新闻/第三方摘录/未验正文”等核验状态，不能因类别名抬升到 `BODY_VERIFIED`。

取舍：直接让产品 Agent 调用用户个人 Skill 会绕过冻结资料与 PIT；另建通用多源新闻框架会扩大职责。本 Change 只接现有采集链中的一个受限来源。

### 3. 验收按层级观察，不以“有数据”代替“有使用”

MRVL 样本分别记录官方宏观、OpenD 补充及公开新闻在本批的尝试、权限、Normalize、Gate、允许列表、工具查询和有效报告引用；已存在的旧 MRVL 消费证明可复用，但新运行的结论只属于其截止点。若需新的模型研究来证明新增线索被实际消费，仅经既有宿主入口、在另行明确的模型次数/预算内运行；预算未获批时保留 `IMPLEMENTED_PENDING_RESEARCH_VALIDATION`，不伪造完成。`RESEARCH_REPORT` 既有材料引用失败独立列为未解决，不用本 Change 的 Source PASS 掩盖。

2026-09-27 的只读复核确认：普通 `COMMON_STOCK_RESEARCH` 有意从启动目录及按字段查询中排除 `research_discovery`，此前一次 Company 草稿也因财务期间引用校验失败而未保存有效报告。因此不得再用普通 Company 补跑验证新增公开线索，也不得人工注入 ID 或放宽其上下文。先零模型冻结同截止点三域 Gate 并确认 `RESEARCH_REPORT` 允许公开 Company 线索、`MARKET_STATE` 允许公开标题；再用现有宿主定点任务入口运行 `FUNDAMENTAL_EVENT → RESEARCH_REPORT`。原获批两次产品子 Agent 调用，用户随后逐次增加上限，目前总上限为 6；四次失败调用已计入，剩余最多两项。不自动重试或运行第三项。新增线索的实际报告消费须同时有成功工具交付、通过闭包/Schema 的报告、至少一条新增公开线索的原样引用，且只作线索/缺口；仅有工具查询或未引用原因时保持待验证。Market 本轮不启动 Agent，必须明确记录“已准入任务、未验证实际引用”；Macro 仅复用适用的历史引用证据，不把旧批次当作新截止点引用。`RESEARCH_MATERIALS_ARTIFACT_REF_INVALID` 继续独立记录，不借标题线索填补正文。

取舍：只做确定性单测无法证明 Agent 实际使用；强制多轮完整组合 Smoke 又超出此处最小来源目标。先复用合法旧证据，再只补确实受影响的 MRVL 专项。

### 4. 一次修复首次定点执行的启动和收尾，不以模型重试排查入口

本次准备包已将 11 条公开 Company 线索交付 `RESEARCH_REPORT`、2 条 Market 标题交付 `MARKET_STATE`。宿主定点启动在模型调用前报 `MULTIDIMENSIONAL_RETRY_BASE_NOT_TERMINAL`：现有入口要求旧 `invocation/process-result.json`。此外定点收尾无条件进入 `_adopt_multidimensional_retry`，即使移除启动检查，新目录仍会因缺少旧 bundle/proof 失败。当前局部 Hook、依赖和 finalizer 测试没有覆盖这条完整入口路径。来源可用与运行可执行必须分开验收。

在现有 launcher/CLI/runtime 中显式区分首次定点执行与终态重试，不另造编排器或通用预算框架：
- 首次执行只接受由标准准备入口生成、版本和冻结输入匹配、尚未使用且未在运行的目录；在创建模型进程前核实任务、依赖闭包和本次两项范围。不得伪造终态、手改封存 packet 或借完整八任务入口绕过限制。
- 依赖解析复用现有机制，本次仅 `FUNDAMENTAL_EVENT → RESEARCH_REPORT`。上游未形成有效报告时下游不得启动；保留失败证据并返回非零退出码，不自动重试或添加第三项。宿主父线程与产品子 Agent 的调用分别记录，两项预算不是“总共只有两个 LLM 进程”。
- 首次收尾复用已有任务级证明与报告校验，记录 `scope=DEPENDENCY_CHAIN_EVIDENCE`、`complete_holding_research_bundle=false`、报告清单及各项真实状态，不调用旧包合并。其余六项明确未运行，不伪造完整 bundle 或 CIO 通过。
- 既有完整运行与终态重试保留原语义和产物保护；已使用目录不得误走首次模式覆盖旧结果。新运行无需旧 bundle，而真正重试仍须验证旧基线。
- 复用已通过的同截止点来源 Gate；若实现变化要求更新运行版本绑定，通过标准准备入口生成匹配的新运行，不反复联网采集或改写原证据。

先做零模型入口贯通测试（替换模型进程返回，不绕过 launcher/CLI 的模式路由），验证首次准备、两项顺序、报告校验、任务证明和退出状态；再覆盖依赖失败、非法任务/范围、重复或活动目录、旧完整运行和旧重试回归。已有来源测试不替代新增入口证明。

新线索消费的确定性样例须证明现有 Schema 可合法表达：在已有 `claims[].evidence_refs` 引用原样 Gate ID，内容仅表示“存在该标题线索、原文论据未核验”，保留正文缺口与适当的 `SOURCE_LIMITED`，不得把线索变成经营事实。不向 gap 添加未支持的引用字段，不新增 Schema，不强迫 LLM 生成正向 Thesis。真实验收仍要求成功查询与有效报告实际引用，查询成功但未引用不算完成。

### 5. 旧 Memory 闭包问题与来源验收分开处理

旧测试 Memory 曾报 `RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE`，隔离外置目录的同截止点采集成功；这不能证明旧根因已修复，也不能归因为来源无数据。补确定性复现/保护测试与诊断记录，验证缺失原始证据时不宣告输入就绪；本 Change 不扩成 Memory 重构或删除旧资料。外层 `FROZEN` 仅证明持久化，真实研究前还必须核实目标条目 `READY`、Gate 非空、截止点正确及引用闭包有效。既有 `RESEARCH_MATERIALS_ARTIFACT_REF_INVALID`、市场宽度或机构持仓来源缺口继续单列，不以本次引用成功掩盖。

2026-09-27 本次定点入口失败发生于模型创建前，新批准的两次产品子 Agent 预算仍为 0/2；更早的失败 Company 运行独立保留，不改写历史。确定性修复与测试通过后才使用这两次预算，再做独立只读复核。之前“复核已执行、结论未通过”不构成完成批准。

首次真实定点运行随后揭示第二层阻断：`FUNDAMENTAL_EVENT` 的完整 Hook packet 序列化约 672 KiB；Hook 记录 `DELIVERED`，但 Luna 子 Agent 回复称未看到上下文并输出非 JSON，终态 `RESEARCH_OUTPUT_JSON_INVALID`。一名产品子 Agent 已真实启动并计入预算（1/2），依赖任务被拒绝、未启动。672 KiB 超过项目现有启动上下文 256 KiB 上限，是应优先验证的交付风险；`DELIVERED` 不能被解释为模型已接收，不断言操作系统或 Codex 的具体截断机制。

在首次定点 Company Hook 响应中对现有冻结 packet 做有界序列化：保留任务身份、精确 Evidence ID 索引、研究指令、查询身份和输出 Schema；合并重复的允许 ID/任务字段，省略冗长的目录元数据和供应商覆盖明细。完整 packet、Gate 和 Schema 仍保存在原有产物并由工具/最终校验使用；模型引用前必须向现有只读工具查询完整事实、期间与来源。实际 Hook 返回的 UTF-8 上下文必须在启动前验证不超过 256 KiB，超限明确失败，不能记录为成功交付。此压缩仅用于本 Change 的首次定点 Company 任务，不改变完整多维运行或旧重试的输入语义。增加真实 MRVL 冻结包的字节数、ID 集合及 Hook 响应测试，再决定是否使用剩余预算。

压缩后的第二次真实调用已生成结构化 `FUNDAMENTAL_EVENT` 草稿，说明此前“无 JSON”阻断不再复现；但 observation condition 引用了不存在的 `mrvl_ai_demand_continuity` claim，确定性校验以 `DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING` 拒绝报告。现有同子 Agent 一次修复机制只为 `RESEARCH_REPORT` 放行这个错误，故本次为 `NOT_ALLOWED`，下游依赖继续正确阻断。该引用确实在草稿中不存在；不能由 Python 删除或补造投资主张。

仅在本 Change 的首次定点 Company 模式，对 `FUNDAMENTAL_EVENT` 的这一结构性错误复用现有“同一子 Agent 内一次自修”机制：给原 Agent 返回缺失引用位置与现有 claim ID，由其提交完整修正草稿；最多两次提交，第二次失败终止，不新增子 Agent、不降低引用校验，不改变完整运行及旧重试的修复范围。用真实失败草稿确定性证明修复请求可定位且小于上下文上限，再以模拟 Hook 测试校验修复成功和用尽失败路径。第二次真实调用计入原预算后累计 2/3，剩余一次不足以完成两项全新依赖链；任何后续真实补跑仍须明确增加两次上限，不从失败运行手改草稿或制造旧基线。

第三次真实调用在同一截止点重新准备的包中形成 `FUNDAMENTAL_EVENT` 草稿，但 `mrvl_valuation_unassessed` 是无任何 Evidence、研究 claim、文档、假设或计算引用的 `INTERPRETATION` claim；它只陈述估值条件不足，该限制同时已在 `data_gaps`。原校验以 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 正确拒绝，依赖任务未启动，累计 3/5。只读诊断在内存里排除该无依据 claim、保留原 gap 后，完整报告封装通过；这不是改写或保存原失败产物。

用户明确批准最小补充：仅在首次定点 `FUNDAMENTAL_EVENT` 中，对 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 复用原子 Agent 同会话一次修正。修复请求标出无依据 claim 的准确位置和 ID；Agent 可基于已经查询且允许的证据补合法引用，或在内容仅为资料缺口时将其留在 `data_gaps`/限制中，不得虚构 Evidence、删除有依据的实质性结论或改变冻结身份。Python 只负责定位和复验，不代写草稿；第二次无效即失败，不增加子 Agent，不改变其他模式。先以真实失败草稿作确定性定位与后续错误检查，再补零模型成功、失败和旧模式隔离测试。剩余两次调用只在上述检查通过后用于全新两项依赖链，不自动超额重试。

### 6. 已批准的后续诊断与合并反馈

用户已批准总调用上限增至 6 次，当前已使用 4 次。先增加轻量诊断，再执行后续真实验证。首次定点研究报告失败时，在现有 Hook output_capture 和 process-result task_outcomes 中记录 REPORT_VALIDATION 阶段、原始首错类别、任务绑定、具体字段路径及同份草稿并存的非法 Evidence ID、无依据 claim、悬空观察条件引用。最多保留 32 个定位项，超出显示截断；这三类检查不代表完整校验或研究语义质量。诊断只保留结构位置及有限长度标识，不复制观点正文、原始工具返回或环境内容；诊断自身异常不得遮盖原始失败或改变门禁结果。不写回历史产物，不做引用模糊匹配或自动修正。先以已有失败草稿证明一次可定位多处问题，并测试诊断不可用和记录有界；合并反馈继续复用原子 Agent 的一次修正，不扩建日志平台。

第五、六次真实调用的两项依赖链均生成有效报告，但 `RESEARCH_REPORT` 只查询并引用 SEC 正文，未查询或引用 11 条已准入的公开 Company 线索；总预算现为 6/6。任务目录包含 402 项，其中 383 项 OpenD 评级与 11 项公开标题混列，`company_material_coverage` 只报告独立正文数为 0，未显式标出这些线索；现有指令正确禁止把标题升级为研报正文，但未要求对已准入线索做最小核验。这是本轮可观察到的输入显著性缺口，不推断模型内部原因。在现有 `RESEARCH_REPORT` 的 `company_material_coverage` 中列出本任务已允许的公开线索原样 ID；其用途与整体报告状态按第 7 节处理。无公开线索时不增加要求；不更改 Schema、工具、材料准备或 Agent 数量。先用零模型包构建、权限与上下文字节测试证明路由，再在新的明确模型预算内做真实消费验收；此前成功报告不能倒算新线索已用。

### 7. 线索层级与报告整体状态分别判断

复核发现上一版提示将“存在公开标题”与“整体 SOURCE_LIMITED”直接绑定，也未要求说明线索的研究用途。本次只修现有研报提示：先遵守材料准备的 BLOCKED_CONFIGURATION/FAILED 失败契约，再依据已核验正文的实际充分性判断报告状态；标题本身保持 LEAD_ONLY，正文与标题并存时不能因标题自动降级，也不能仅凭正文数量自动宣布研究充分。

Agent 至少查询一条已准入线索，在原有“作者依据与假设”等研究问题下核实相关性。采用时通过已有 claim 引用说明其具体核验用途、来源层级与不能支持的结论；不相关、重复或无新增价值时在现有 gap/限制中写清排除原因，不为引用数量拼凑主张。本次 MRVL 正例验收仍须成功工具查询和至少一条相关线索的原样引用，排除记录不能当作报告已消费。

测试覆盖只有标题、正文与标题并存、配置阻断与标题并存，并复用无标题检查；这些确定性检查证明任务输入与原报告契约兼容，不证明模型语义行为。现有 Hook 诊断和 research-consumption-audit 已足够区分未查询、查询未引用与已引用，不新增日志平台。预算 6/6 已用，下一次模型验收仍待明确新额度。

## Risks / Trade-offs

- [OpenD 在宿主可用而 Codex 沙箱阻断 SDK 日志] → 权限阶段单列，优先宿主只读运行；不得扩大到用户目录通配访问。
- [标题误命中或观点当事实] → MRVL/ETF/同名负例、时间与来源核对；正文未取到始终 `LEAD_ONLY`。
- [供应商当前值被回填为历史 vintage] → 继续沿用现有 PIT 保守发布时间规则，当前采集不证明过去已知。
- [外部搜索接口、SDK 权限或内容许可变化] → 有界失败降级，只保存最小元数据和原链接，不绕过软性封锁抓正文。
- [旧能力矩阵把 OpenD 整体写成 PARTIAL，掩盖逐项成功] → 本 Change 的验收以本批逐数据集 coverage 和报告引用为准，必要时仅校正文档过时状态。

## Migration Plan

先做不改行为的权限/状态辨别和现有 OpenD 有界宿主复验；然后增加公开标题线索与聚焦测试；最后以 MRVL 同一新截止点核对 Gate/消费并更新来源说明。新线索源默认失败开放：关闭或失败时 SEC/Yahoo/官方 Macro 和既有 OpenD 路线不变。若新源造成误命中或语义漂移，可撤回该来源政策与采集接线，已冻结的旧运行产物不重写。
