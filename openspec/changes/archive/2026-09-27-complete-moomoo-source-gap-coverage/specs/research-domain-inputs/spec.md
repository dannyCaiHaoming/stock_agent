## ADDED Requirements

### Requirement: Moomoo 公开搜索仅作为独立的有界线索来源
系统 MUST 将 `moomoo-news-search` 对应的公开新闻、公告和 `Research` 搜索结果与 `moomoo_sg` loopback OpenD 分别标识。候选 MUST 保留原始链接、标题、来源类别、`source_id`、发布时间或明确缺失、`retrieved_at` 和研究截止点，并按证券身份、相关性、重复和 PIT 规则筛选。仅有搜索元数据时内容层级 MUST 为 `LEAD_ONLY` 或标题线索；`Research` 类别、评级快讯、二次转引或公告索引 MUST NOT 自动成为独立研报 `BODY_VERIFIED`、发行人原始披露或 Company Thesis 事实。

#### Scenario: MRVL 搜索混入其他公司或相关 ETF
- **WHEN** 搜索命中名称相近的非 Marvell 公司、杠杆 MRVL ETF 或无法核对发行人身份的项目
- **THEN** 该项目不得作为 `US:COMMON_STOCK:MRVL` 的公司事实或研报正文交付，并记录排除原因

#### Scenario: 评级新闻被归入 Research 类别
- **WHEN** 返回标题、时间和 URL，但未取得可核验正文及正文出处
- **THEN** 系统最多将其作为 Company `RESEARCH_REPORT` 发现线索，保留观点/转引身份与正文缺口，不将该维度或整个研究链标为研报正文完成

### Requirement: 公开新闻线索必须按 Company、Macro、Market 语义消费
Company 的合格线索进入现有多维 `RESEARCH_REPORT`，只提示后续核验；普通 `COMMON_STOCK_RESEARCH` 的 Company 首版上下文继续排除专门能力的 `research_discovery`，不得为验收而扩大。发行人事件以 SEC/IR 原文为事实锚点；Market 仅可在标题确属本批截止点前、设定时窗内且与市场研究问题相关时，将其作为有限新闻背景。Macro 官方观察和政策正文仍由既有官方来源承担；Moomoo OpenD 宏观实际/供应商共识是二级补充，公开新闻标题不能替代数值 Evidence。系统 MUST 在单一 MRVL 样本中分别报告来源尝试、Gate 准入、研究工具交付、有效报告引用或未引用原因；不得只凭适配器存在、Gate 准入或 JSON 保存称为 Agent 已使用。

#### Scenario: 公开 Company 线索的实际消费验收
- **WHEN** 同一截止点的 MRVL Gate 已准入公开 `research_discovery` 线索，需要证明其被研究 Agent 实际使用
- **THEN** 验收走现有多维 `FUNDAMENTAL_EVENT → RESEARCH_REPORT` 依赖链，核对 `RESEARCH_REPORT` 的允许 ID、成功工具查询，以及通过 Schema/引用闭包的报告对至少一条新增公开线索的原样引用；报告只可把它作为线索或缺口，不得提升成正文或公司事实。若只有工具查询或有依据的未引用原因，必须如实记录但不得称新增线索已被报告消费，继续保持待研究验证

#### Scenario: 公开线索在混合研究目录中可辨认
- **WHEN** `RESEARCH_REPORT` 的允许目录同时含大量 OpenD 评级快照和已准入的公开标题线索
- **THEN** 同一任务输入明确列出公开线索的原样 Evidence ID，并要求 Agent 至少查询一条，核实其与当前研究问题的关系；采用时在已有 claim 引用中解释用途、标题/链接层级及核验限制。不相关、重复或无新增价值的线索允许排除并记录原因，不为引用数量拼凑主张；未引用仍不得标为报告已消费。本次 MRVL 正例的真实查询及至少一条合法引用验收不变。没有公开线索时不施加此要求，其他研究维度不变

#### Scenario: 标题线索与已核验正文并存
- **WHEN** 公开线索与可用的独立研报正文同时进入 RESEARCH_REPORT
- **THEN** 线索自身保持 LEAD_ONLY，报告整体状态依据已核验正文与研究问题的实际覆盖判断；不得因存在标题自动输出 SOURCE_LIMITED，不得仅因有一份正文就自动宣布充分。没有足够正文时仍保留真实正文缺口

#### Scenario: 配置阻断优先于线索可用
- **WHEN** material_preparation.status 为 BLOCKED_CONFIGURATION，且公开线索可用
- **THEN** 原有 FAILED / evaluation_status=FAIL 与配置缺口要求优先；线索可用不得将配置失败改写成 SOURCE_LIMITED。既有 FAILED 准备状态也按原失败契约处理

#### Scenario: Market 24 小时窗口得到相关标题
- **WHEN** 现有新闻源在本次时窗内无合格项目，而 Moomoo 公开搜索在有界请求内取得身份、时间和相关性均合格的市场标题
- **THEN** Market 可消费明确标为标题线索的项目，保留原链接和来源限制；不得推断正文事件、市场宽度、信用利差或确定性行情方向

#### Scenario: 线索引用沿用现有报告契约
- **WHEN** 验证 Agent 对公开标题线索的实际消费
- **THEN** 报告通过已有 Schema，在已有 claim 引用字段保留原样 Gate ID，只陈述线索存在及核验限制，保留正文缺口；不得向 gap 添加未支持字段、将标题升级为经营事实或为验收强制投资结论，合法保存也不代表独立研报正文完整

#### Scenario: 搜索结果不相关或超过截止点
- **WHEN** 仅有无关标题、未来发布时间或无法证明 24 小时窗口的项目
- **THEN** Market 新闻缺口保持，Macro/Company 不借用这些项目填满各自覆盖；系统记录实际尝试而不制造 `AVAILABLE`

#### Scenario: 既有 OpenD 宏观数据通过 Gate 但报告未引用
- **WHEN** Moomoo Macro History、Economic Calendar、FedWatch 或 Dot Plot 已采集并通过 Gate，但目标任务没有查询或没有形成有效引用
- **THEN** 覆盖报告分开呈现采集成功与未消费，并保持官方/二级供应商、实际/共识/市场预期的语义边界

### Requirement: 首次定点研究须经现有宿主入口完整执行与收尾
系统 MUST 在现有宿主入口区分首次定点执行与终态重试。首次执行 MUST 在模型启动前校验标准准备产物、版本绑定、冻结输入和依赖范围，不要求旧终态或旧研究包；本次仅允许 `FUNDAMENTAL_EVENT → RESEARCH_REPORT` 两项产品子 Agent 调用，不自动重试或扩展其他研究任务。系统 MUST 保留原有完整运行及终态重试行为，不新增编排器、伪造失败基线或降低 Evidence/PIT/Gate/Schema 门禁。

#### Scenario: 全新准备包执行两项依赖研究
- **WHEN** 匹配冻结输入与版本的未使用准备包通过校验，并经宿主启动本次定点研究
- **THEN** 按依赖顺序执行两项，首次收尾不进入旧包合并；生成有效报告、进程结果和已有任务级证明，明确 `scope=DEPENDENCY_CHAIN_EVIDENCE` 与 `complete_holding_research_bundle=false`，其余任务标明未运行，不宣称完整多维研究或 CIO 完成

#### Scenario: 范围或准备状态不合法
- **WHEN** 指定任务或依赖范围不合法、输入未就绪、版本绑定失配，或首次执行目录已使用/正在运行
- **THEN** 在创建模型进程前拒绝启动并返回非零退出码，保留原有产物；真正终态重试继续验证其旧基线，不得误走首次模式

#### Scenario: 上游研究失败
- **WHEN** FUNDAMENTAL_EVENT 执行失败或未通过报告校验
- **THEN** 不启动 RESEARCH_REPORT，不自动补跑；保留已执行调用、失败记录和下游未执行状态，宿主返回失败而非成功

#### Scenario: 冻结记录不等于输入就绪
- **WHEN** 数据准备外层显示 FROZEN，但目标条目失败、Gate 为空、截止点不符或原始证据闭包缺失
- **THEN** 不启动研究，不把持久化状态当作来源或研究成功；准确记录阻断，旧 Memory 问题不得因隔离目录成功而被标记已修复

#### Scenario: 首次定点 Hook 上下文过大或模型未形成结构化报告
- **WHEN** 同一冻结任务的完整 Hook packet 过大，或 Hook 声称交付但子 Agent 未形成可校验的结构化输出
- **THEN** 首次定点 Company 上下文采用不超过 256 KiB 的有界序列化，保留全部原样允许 Evidence ID、任务/工具身份及输出 Schema，完整事实仍须通过现有只读工具查询；超限在模型启动前失败，实际非结构化输出保留失败证据、禁止下游派发，`DELIVERED` 不单独证明模型已收到或研究成功

#### Scenario: 首次定点基本面草稿存在悬空观察条件引用
- **WHEN** FUNDAMENTAL_EVENT 的 observation condition 引用不存在的 claim ID，且该 Agent 正在本次首次定点 Company 研究中
- **THEN** 现有 Hook 只允许原子 Agent 在同一会话内按明确位置与合法 claim ID 清单提交一次完整修正草稿；Python 不补写或删除研究主张，最终报告仍须通过原 Schema/引用闭包。第二次无效即失败并阻断 RESEARCH_REPORT；完整多维运行及旧重试的修复范围不因本场景改变

#### Scenario: 首次定点基本面草稿含无依据 claim
- **WHEN** FUNDAMENTAL_EVENT 的 claim 没有 Evidence、研究 claim、文档、假设或计算引用，且该 Agent 正在本次首次定点 Company 研究中
- **THEN** Hook 仅给同一子 Agent 一次按准确位置和 claim ID 修正的机会；Agent 必须补充真实允许的引用，或在内容仅是资料不足时保留对应 gap/限制并移去无依据 claim。Python 不自动编辑草稿，不放宽原 Schema/引用闭包；第二次仍无效则失败并阻断 RESEARCH_REPORT，其他运行模式不扩大此修复范围

#### Scenario: 首次定点失败草稿含多个结构问题
- **WHEN** 首次定点研究报告被校验拒绝，草稿同时存在非法 Evidence ID、无依据 claim 或悬空观察条件引用
- **THEN** 现有 Hook 和进程结果同时保留原始首错与这些问题的字段位置，最多记录 32 项并标记截断；输出不复制正文或工具载荷，诊断异常不得遮盖原始失败，诊断没有发现这三类错误也不代表报告通过。历史草稿与终态不被改写

#### Scenario: 首次定点基本面草稿的引用错误自修
- **WHEN** 首次定点 `FUNDAMENTAL_EVENT` 首次提交因非法 Evidence 引用、无依据 claim 或悬空观察条件引用被拒，且有界诊断完整定位这些问题
- **THEN** Hook 可把同份草稿中已定位的全部问题一次交回原子 Agent，并要求其重新查询或核实原样允许 ID、合法 claim/假设引用，或把纯资料缺口留在 gap；不得对截短 ID 做模糊匹配或由 Python 改写草稿。仅同一子 Agent 再提交一次，完整 Schema/Evidence/PIT 门禁照常执行；诊断不可用、被截断或第二次失败时保留原错并阻断下游，其他模式的修复范围不扩大
