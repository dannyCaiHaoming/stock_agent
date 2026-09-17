## Context

见 Proposal 与 Specs。用户将数据源调整为 SEC + Yahoo + Moomoo Singapore；补齐普通股研究缺口的目标保持不变，因此保留当前 Change 与 capability 路径。原多维研究 Change 已于 2026-09-16 归档，新增数据只建立后续证据映射。

现有系统已有 SEC/Yahoo 获取、期权尝试、追加缓存和 Evidence Gate。用户已在本机启动 Moomoo OpenD，并完成首次 API 问卷与协议。Moomoo 官方 v10.10 文档已明确 OpenD 是 API 网关，未开户平台账号可登录获取行情；实际 OpenD/SDK 版本、Quote 登录状态和逐数据集权限仍须真实验证。

## Goals / Non-Goals

**Goals:** 用明确分工的三源组合交付可引用的研究增量；各来源独立失败；通过官方 Moomoo OpenAPI/OpenD 的只读 Quote API 复用现有研究流程。

**Non-Goals:** 不要求开户、不采购收费 API，不接交易接口、账户查询或远程 OpenD；不接收登录凭据，不使用 Cookie/Charles/私有 HTTP 端点，不新增投资 Agent、自动登录或通用 SDK 代理；不将 UI/OCR 作为自动获取完成证据；不重写历史研究包。

## Decisions

### 1. 按数据集分工并记录回退

| 数据集 | 主来源 | 补充与边界 |
|---|---|---|
| 财报、公告、公司事件 | SEC | Yahoo/Moomoo SG 摘要只作二级交叉核对 |
| 价格、OHLCV、公司行动、基准 | Yahoo | Moomoo SG 仅在已验证同口径后显式回退；不得拼接不同复权序列 |
| 机构两期与内部人 | SEC 13F/3/4/5 原始申报 | Moomoo SG 可发现候选或提供二级资料；不得把供应商汇总当完整 SEC 覆盖 |
| 期权静态链与动态快照 | Yahoo | 受限时可用已验证的 Moomoo SG 端点；每个来源独立记录时点、字段和权限 |
| 供应商资金流 | Moomoo SG | SEC 13F、Yahoo 成交量均不能替代或伪装为资金流 |
| 研报候选、评级与可读正文 | Moomoo SG，Yahoo 补充候选 | 新闻、公告、评级摘要不等于研报正文；未读正文不生成正文 Evidence |

选择记录保存 primary、attempted、selected、fallback_reason、字段覆盖与证据 ID。回退仅限预先批准的同语义数据集，限一次；双方失败保留缺口。独立快照不拼为一个同时点期权面。

### 2. 三个适配器与一个研究补充快照

采用 `HoldingResearchRequest → DatasetSourcePlan → SEC/Yahoo/MoomooOpenD Adapters → CaptureBatch → Normalize → Evidence Gate → frozen MCP → existing Skill`。

优先复用 SEC、Yahoo 实现；新增 `MoomooOpenDResearchAdapter`。组合模型使用 `ResearchSourceCapabilityInventory`、`ResearchCaptureBatch`、`MoomooQuoteCapabilityManifest`，数据模型按语义而非品牌分离：OptionSnapshot、VendorFlowSnapshot、OwnershipDisclosureSnapshot、ResearchCandidate/ResearchDocument。

Input 包含证券、数据集、cutoff 和预算；Tool/Data 为三源适配与冻结查询；Skill/Reasoning 复用既有专业 Skill；Structured Output 为快照、Evidence 与专业报告；Eval 为确定性负例和一次限定真实消费检查。

不直接改变基础 `live-snapshot/4.0.0` 或 `live-source-access/4.0.0` 的 provider 枚举。先核对 `common_stock_data.py`、`options.py`、`evidence_gate.py` 和多维研究接缝，采用有独立契约、能通过 Gate 的补充快照；若必须修改基础契约，先显式更新版本与迁移规划。

### 3. SEC 公共数据路径独立运行

SEC 使用公共 EDGAR 数据读取接口与 Archives 原始申报，不使用提交申报 API。复用联系方式标识、限速、缓存及有界请求策略。

Companyfacts/公司 submissions 不被当作发行人全部机构股东数据库。13F 以申报机构和信息表为单位，保留 manager CIK、accession、证券标识、报告期、提交/公开时间、修订关系、shares/value/unit 与覆盖集合；未解决的 CUSIP/证券映射必须隔离。部分管理人样本不能声称完整市场持仓。

比较两期需同机构、同证券、同口径并核对修订及公司行动；Form 3/4/5 保留交易日期、申报日期、交易代码、衍生/非衍生表、直接/间接持有与修订。公开披露中的机构/内部人身份是研究事实，不应被私人账号字段扫描误删。

### 4. Yahoo 复用与字段级能力

复用既有 transport/session 机制，不要求用户为 SEC/Yahoo 提供 Moomoo Cookie。先验证历史行情/公司行动，再独立验证期权。明确区分页面可见、程序响应有效与条款允许；历史 CSV 下载或期权动态字段不被假定免费可得。

保存复权方式、币种、市场时区、盘前/盘后、行情延迟与各字段时点。缺 Greeks 不自动判整条期权链失败，也不补零；可支持的研究用途按实际字段判断。OI 的观察日期与报价时间分开；last trade time 不冒充所有字段时间。

### 5. Moomoo SG 通过官方 OpenD 扩展数据集

服务区域固定 `SG`，记录证券市场 `US`，两者不可混淆。Runtime 使用官方 `moomoo-api` SDK 连接用户已登录的本机 OpenD；连接 host 必须解析为 loopback，默认端口为 `11111`，可配置端口仍不得放宽为远程地址。

认证、问卷和协议完全留在 OpenD。适配器不读取 Moomoo App/OpenD 私有文件、Keychain、Cookie、Token、账号密码或交易解锁信息。OpenD 可连接后先读取全局状态与版本，证明 quote service 已登录，再以 `US.AAPL` 对一个批准的研究方法执行最小真实查询。App 已登录或端口开放均不足以证明可行。

只实例化官方 `OpenQuoteContext`；生产模块和测试负例禁止实例化或接受 Trade Context。能力从版本化方法 allowlist 暴露，不提供任意 `getattr`、任意 proto 或 SDK 透传。官方方法存在但当前账号无权限时记录 `ENTITLEMENT_REQUIRED` 或实际错误；不回退到 Cookie、Charles 或私有 HTTP 接口。

首批候选方法按用户目标有界验证：全局状态、公司档案/高管、财务报表、收入分部、分析师一致预期/评级、Morningstar 研究资料、股东/机构/内部人、公司行动、资金流、空头资料和期权。方法逐项通过后才绑定标准化器，不能由一个成功方法推断其他方法可用。

### 6. OpenD allowlist、认证边界与失败隔离

`MoomooQuoteCapabilityManifest` 锁定 provider/region、SDK import、最低与实测 OpenD/SDK 版本、Quote API 方法、参数名和值域、证券市场、响应字段、验证日期、频率/页数/总时长及批准记录。调用层仅接收结构化数据集请求；遇到未知方法、额外参数、非美股证券、远程 host、Trade Context 或账户/订单/持仓/资金/解锁语义时在连接前拒绝。

SDK 返回的 DataFrame/dict 经确定性 JSON 转换后保存 raw hash，同时保留 dtype、列名、分页 token、OpenD/SDK/方法版本和调用时间。只读响应仍执行证券身份、大小、分页和私人账户字段检查；OpenD 日志与认证状态不进入 Evidence 或模型上下文。

统一状态：`NOT_ATTEMPTED`、`AVAILABLE`、`PARTIAL`、`SOURCE_LIMITED`、`UNSUPPORTED`、`OPEND_UNREACHABLE`、`QUOTE_NOT_LOGGED_IN`、`OPEND_VERSION_UNSUPPORTED`、`SDK_VERSION_UNSUPPORTED`、`ENTITLEMENT_REQUIRED`、`RATE_LIMITED`、`API_UNAVAILABLE`、`CONTRACT_MISMATCH`、`BLOCKED_BY_POLICY`。矩阵逐 provider/region/dataset/security/field 记录，不把未尝试写成受限。

### 7. Evidence、时点与语义

CaptureBatch 记录请求计划、各源状态、来源版本、预算、raw hash 与 Evidence ID；Moomoo 来源版本包含 OpenD、SDK 与 Quote API 方法。原始资料先经大小/响应类型、身份、私密字段与分页检查，再标准化。日志不记录认证材料。受限原件留 quarantine；合格缓存追加写，key 包含来源、区域、版本、证券、数据集和参数。

事实含 `source_id`、`as_of`、`retrieved_at`，另保留 `published_at/accepted_at`、source_locator、security_id、source_type、raw hash、batch 和 endpoint 版本。13F 报告期不是市场知悉时间；历史 cutoff 必须核对当时公开版本。时间不明不可用 retrieved_at 补造。跨源时间差超预算分别展示，禁止静默混合。

SEC 原文为原始披露；Yahoo 为市场供应商；Moomoo SG 保留 SECONDARY_VENDOR 或 VENDOR_CALCULATED_FLOW。转载声明的原来源不升级为直接原文证据。资金流保留供应商大小单、期间、币种、单位、定义，不能推导真实机构流入。研报标题/摘要/全文分层，单份正文不能证明对比完成。

MCP 仅接收证券、数据集、cutoff、batch ID 并返回冻结合格 Evidence。Agent 无凭据、Bootstrap、通用 HTTP 或原始隔离区权限。计算与校验由确定性组件完成，判断仍由现有 Skill 完成。

### 8. 分阶段验收

先形成 SEC 原始披露与 Yahoo 行情的真实基线，再验证 Moomoo SG；各源可独立交付。原缺口的核心增量限定动态期权、供应商资金流或可比两期机构持仓，普通行情复用本身不能抵扣。

整个 Change 完成需 SEC、Yahoo 的真实接入证据，Moomoo SG 至少一个研究数据集通过 Capture → Normalize → PIT → MCP，并至少一个核心增量得到现有专业 Skill 的正确消费；所有其他目标逐项有成功、部分或实证限制说明。至多一次 GPT-5.6 Terra 专项消费检查，仅在显式 apply/宿主授权下运行，不运行 Council 或晋升工作流。

### 9. 个股背景资料对照与补齐设计（2026-09-16）

参考仓库固定在 `gsaini/financial-research-analyst-agent@d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d`。本次只读检查代码，不执行其程序；参考实现和 README 均不是当前项目或真实来源可用性的验收证据。

| 资料方向 | 本仓库已核对状态 | 本 Change 补齐与来源 |
|---|---|---|
| 公司身份与档案 | 已有证券绑定与报告 security 字段，未见独立完整背景包 | SEC 法定名称/CIK/申报主体；Yahoo 档案，Moomoo SG 补充行业、简介、官网定位、总部国家/城市、员工数及日期；保留分类体系与来源冲突 |
| 业务、产品与地区分部 | company-research 有方法；disclosure.py 有有限 business/MD&A 文本；collection.py 明示缺维度数据 | SEC 原始申报分部注释、iXBRL/XBRL context；主要业务、收入驱动、产品/地区分部及已披露运营 KPI；Yahoo/Moomoo SG 只作二级补充 |
| 管理层、治理、控制权 | 方法提及治理，未见专门治理采集/契约 | SEC 年报、DEF 14A 及相关 8-K；重要高管/董事角色、任免、生效日期、控制权、股权激励和重大关联交易；两供应商补充公开摘要 |
| 客户、供应商与竞争 | 有公司/同行研究方法，同行候选来自 NASDAQ 目录，非关系事实 | SEC 集中度/依赖披露，Yahoo/Moomoo SG 提供线索；实名关系须有直接证据，匿名客户保留匿名，不以同行或相关性推断上下游 |
| 财务历史与资本配置 | 已有收入、利润、现金流、债务期限、Capex、稀释等；当前筛选为 800 天且各组最多 8 条 | SEC 补资产/负债/权益、营运资本、R&D、利息、税项、分红/回购与承诺；Yahoo/Moomoo SG 同口径交叉核对与估值快照 |
| 业绩、指引与预期差 | 有 8-K 业绩附件节选，未见一致预期/指引专门数据集 | SEC 实际业绩和管理层指引；Yahoo/Moomoo SG 预期、财报日历、评级/目标价及修订，按预测期间和发布时间独立保留 |
| 新闻与事件资料 | catalyst-analysis 有方法与公司事件范围 | 三源内合格事件/新闻，记录发布/发生时间、实体关联、更新与转载；电话会全文仅当三源合法提供时读取 |
| 股本与空头背景 | 有 SEC 股本/稀释及行情，未见专门 short-interest 契约 | SEC 股本/发行/回购，Yahoo/Moomoo SG 流通盘、short interest、days-to-cover；保留统计日，不推算借券费用或挤空评分 |

依据文件：`product/mcp/live/collection.py` 的 FINANCIAL_TAGS/research_financials、`disclosure.py` 的 SECTION_NAMES/截断标记、`peer_candidates.py` 的候选语义、`product/skills/company-research/SKILL.md`、`catalyst-analysis/SKILL.md`、`industry-comparison/SKILL.md` 与 `product/schemas/runtime/equity-research-report.schema.json`。这里的“未见”限定于本次核对的现有数据入口和契约，不表示历史自然语言报告完全没有提到相关事实。

参考源码定位（固定 commit）：[公司档案](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/market_data.py)、[业绩资料](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/earnings_data.py)、[分析师预期](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/analyst_tracker.py)、[供应链](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/supply_chain.py)、[空头背景](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/short_interest.py)。借鉴资料类别，不复用其默认补零、规则评分、硬编码关系、推算借券费率或将 forward EPS 作为下次财报预期的处理。

#### 背景包契约与事实提取

`CompanyBackgroundSnapshot` 按 security_id/cutoff/batch 绑定，包含 identity_profile、business_segments、management_governance、relationships、financial_history、capital_allocation、earnings_guidance、analyst_expectations、event_context、share_short_context 十组。每组均有 coverage、evidence_refs、gaps、source_attempt_refs；事实仍保留 source_id/as_of/retrieved_at 和原文定位，不创建无来源的第二份事实库。中文展示与 JSON 同源，事实、公司声明、供应商预测与研究解释分开。

基础必备是核实的证券/公司身份、带直接披露依据的商业模式与主营业务、已公开最新适用财务期及同比基线、股本/现金/债务的可得风险背景；至少身份、业务和核心财务须形成真实事实，其余未知均有具体影响。管理层、分部、客户供应商、资本配置、业绩日历/指引等必须检查，未披露/来源受限/不适用逐项记录；一致预期历史、电话会全文、空头数据为可得增强，不能承诺三源始终可得。

财务历史默认目标为最近 3 个完整财年和 8 个独立季度，可通过有界参数缩小；3 年窗口不能沿用 800 天硬截断，8 条披露记录不等于 8 个季度。去除重复展示但保留所有 accession/重述链；累计流量拆季度须有可比期间、同主体和同会计基础，经确定性计算并保存父 Evidence；上市不足、重组、IFRS 或扩展 taxonomy 不支持时保留准确覆盖，禁止强行年化、拼接或补零。

分部读取保留 axis/member、单位、期间、合并抵销、重分类和重述；总数不能复制到分部。原始披露定位按 section/table/row 或字符范围保留截断状态；SEC 治理/分部路径和必要表单仅按用途有界扩展。非结构化的业务、指引、管理层关系由既有 Company Analyst 在冻结文档上提取为带引文的候选事实，再做引用与身份/时间校验，解释仍由 Skill 承担；不以关键词规则判断护城河、管理层质量或主题价值，不新增 RAG 平台或专属 Agent。

#### 预期与时点规则

实际业绩、管理层指引、分析师一致预期分别保留来源、目标财政期、GAAP/non-GAAP、单位、样本数和 vintage。预期差只在取得结果公布前的预测版本且口径一致时计算；无法证明历史 vintage 的当前供应商“历史预期”不能回填成当时已知。年度 forward EPS 不能当下一季度 EPS。零/负基数保留绝对差，百分比不可解释时为 null 并说明原因。

财报日历区分公司确认、供应商估计、时间窗口和取消/变更，事件发生日不能取代可知时间。新闻仅保留三源实际提供的内容和定位；指向第四方的链接只作候选定位，不自动新增抓取来源。当前档案无法证明历史有效日期时标为当前观察并限制历史用途，不能臆造生效时间。供应商目标价是其观点，不是系统目标价。

#### 背景包接入与验收增量

新增背景数据集与既有三源 sidecar/Gate/MCP 共用流程，先 SEC/Yahoo 背景最小闭环，再完成 Moomoo SG 补充。既有 NASDAQ 候选目录仍仅用于原路径；新背景关系事实与新候选补充限定三源，不为本 Change 删除旧目录或宏观来源。

完成条件在原三源与核心增量门槛上增加：一只真实普通股的基础背景可直接回答“公司做什么、收入来自哪里、当前财务基线是什么、已知重要依赖和未知项是什么”，十组覆盖逐项可追溯；至少一个新增背景类别（例如可核实分部、治理或指引）含真实 Evidence，不能只包装旧报表。背景资料在同一次既定专业消费检查中被引用并验证，不额外自动启动模型批次。其余持仓可在相同有界流程按字段可得性扩展。

#### 截图持仓消费与父线程终态屏障

截图持仓 v3/v4 已证明基础数据准备和三个 `runtime_company_analyst` 启动，但没有终态或报告；父线程提前返回，finalizer 正确失败。这只是首次可观测分歧，不能由此认定完整根因，更不能排除研究输入、上下文交付、MCP 或子任务执行故障。

普通股 launcher 增加同步、run-scoped `Stop` Hook。父线程准备结束时，Hook 从冻结 dispatch index、允许派发记录及最小化生命周期日志重算预期、已完成和缺失 task_name；只接受同一父会话中 start/stop 配对且 output binding 匹配冻结 invocation 的终态。缺失终态时返回 `decision=block` 和简短继续等待指令，全部齐备时允许结束。`SubagentStop` 继续负责捕获原始结构化报告，父 `Stop` Hook 不读取研究正文、不生成或修补报告。

父停止检查写入独立 JSONL 审计，只含 run_id、parent session、turn、时间、预期/已完成/缺失 task_name、decision 和 event hash；不保存 Prompt、研究正文、最终消息或 transcript 路径。launcher 的批次超时仍是硬边界；若子任务无终态，屏障持续阻止提前结束直至宿主超时并保留失败证据。

2026-09-17 复盘发现 v3/v8 Gate 的 6,035 条 Evidence 没有 Moomoo，preparation 没有 research_supplement。故原计划“仅复用 v3 重跑即验收三源持仓接入”不成立。v8 的 Stop 审计已多次 BLOCK，但仍为 3 Start、0 Stop、0 报告，已按用户要求中止；无 process-result 的中止运行不得标记超时或成功。Hook 仅证明提前退出被阻止，未证明子任务推进或真实消费。

#### 阻塞与最小闭环方案

| 阻塞 | 已有证据与未知项 | 需求内解决方式 | 解除证据 |
|---|---|---|---|
| 截图持仓缺三源补充输入 | v3/v8 无 Moomoo Evidence、无补充包索引；AAPL 样本不是持仓输入 | 复用既有适配器，以 ALB/MRVL/WOLF 为范围组织逐证券补充包并接入宿主数据准备；支持多包索引，记录每股十组覆盖及来源尝试 | 同一 Handoff 下逐股包→Gate→MCP 的身份、cutoff、Evidence 闭合；至少一只持仓有真实 Moomoo 研究数据及本 Change 核心增量 |
| 子任务无终态 | Start/DELIVERED 是 Hook 发出上下文的证据，不证明模型成功使用；没有报告；真实原因未知 | 先读取现有运行的派发、上下文体量、MCP 启动/调用/错误和退出证据，定位最早失败步骤；只修改直接阻塞报告交付的接缝 | 故障假设有支持及排除证据；最小修复后实际查询新增 Evidence 并生成合法报告 |
| 完成口径冲突 | 旧 AAPL Reviewer PASS 排除截图持仓；现行规格包含它 | 保留旧评审作为限定范围历史证据，新评审覆盖当前完整需求与实际差异 | 当前验收矩阵逐项判定，旧 PASS 不外推新增接线或 Hook |

2026-09-17 最新状态：三项阻塞均已在需求范围内解除。v5 完成三只持仓逐股包、同一 cutoff、Gate/MCP 与 source bundle 重建；用户授权后的 ALB 单股先行运行和 ALB/MRVL/WOLF 三股并发批次都通过。完整批次产出 3/3 有效报告，每份都引用 SEC、Yahoo 和 Moomoo SG 资金流，并保留 ETF/期权能力缺口。失败运行作为历史证据保留，不被改写为 PASS；当前仅等待独立只读复核与人工完成批准。

多证券接入优先扩展既有补充包索引与数据准备流程，不新增服务、Agent、调度后端或治理平台。每只股票基础背景必备；增强字段可按真实尝试保留限制，不强制每股每源全部可得。所有持仓均无 Moomoo 研究增量时，不能用 AAPL 成功替代截图接入验收。

正式入口继续使用 `scripts/run-product-smoke.sh --stage common-stock-research --handoff ...`。用户只提供确认 Handoff、既有来源配置并管理本机 OpenD；入口依次组织有界采集、逐证券补充包挂接、共同 cutoff 冻结、研究派发和中文/JSON 输出。显式冻结包参数继续用于诊断与复用，但临时脚本手工拼包跑通不能替代正式入口验收。

接入同时覆盖现有模块的五处接缝：逐证券补充包保存、preparation 索引、source bundle 的重建校验、HoldingResearchRequest/冻结 MCP 的证券范围与可查询 Evidence、最终报告引用。`common_stock_data.py` 的挂接与重建读取须一致支持多包；`cli.py` 和宿主入口负责调用；现有研究请求、MCP 与报告契约能复用则不修改。采用最小兼容演进保留旧单股包读取；混合多个证券、重复挂接、缺包或错 cutoff 不得静默覆盖或通过校验。

Moomoo 不可达、权限不足或单股数据受限时，记录具体缺口，继续处理其余来源与证券；缺失三源增量只使本 Change 的三源验收未通过，不将所有 SEC/Yahoo 研究判为失败。身份、PIT 或报告契约错误仍按原门禁失败，不因部分可用而放宽。

先核实是否有符合证券与 cutoff 的现成补充包。有则复用；没有则在已授权三源范围内有界采集，建立新 cutoff、新 run_id 与新包，保留原 Handoff 和旧包，不把当前数据塞回 v3。仅诊断旧冻结运行时保留原 run_id、使用新的尝试目录。采集和包校验完成后才能启动研究消费。

研究重跑前必须有输入覆盖矩阵、最早失败步骤、修复与故障的对应关系、预期解除信号和现有预算。优先验证一只持仓的端到端接入，再完成三只报告集合；复用已有有效结果，失败先检查证据再重试。最终核对实际 MCP 返回与报告引用，不能仅以 3 个 Stop 或文件数验收。SOXL ETF/期权缺口继续保留，不启动完整 Council 或晋升。

旧日志不足时，不要求凭空先得出根因。先写明最早未证实的执行边界、具体假设和区分它们所需的信号；优先用确定性检查，必要时仅在既有宿主入口增加最小诊断并做有界运行。每次运行前声明验证对象、次数/时长预算及停止条件，沿用已有授权和预算；没有新证据不原样重复。诊断出口是确认阻塞并实施最小修复，或报告明确的外部依赖和解除条件，不是建设通用可观测平台。

#### 归档停止标准

正式入口完成三只普通股的合法中文/JSON 报告；每股基础背景与缺口可追溯；至少一只实际持仓消费新增背景类别和核心增量，并具备实际 Moomoo 研究数据消费证据；查询、引用、证券与时间闭合；受影响检查和当前差异独立复核通过后，交用户人工完成批准。十组增强资料允许准确受限，不追加全部填满、完整 Council、新 Agent、通用编排或发布级 Eval/Promotion 门槛。满足上述标准即停止扩展，进入既有归档流程。

## Risks / Trade-offs

- [OpenD 已登录不代表所有 Quote API 可用] → 逐方法验证版本、行情登录与 entitlement，不从 App 或单一成功接口外推。
- [官方 API 权限与 App 权限不同] → 按方法和字段记录真实返回；无权限时保留缺口，不自动购买或回退私有端点。
- [三源不能覆盖宏观或完整研报] → 不删除既有外部维度，不宣称三源完成所有投研信息。
- [13F 覆盖与证券映射不完整] → 报告管理人集合和映射缺口，不制造全市场趋势。
- [旧名称令人误解] → 四份文档声明新含义，保留已归档责任引用，不做无关重命名迁移。
- [子任务永久无终态导致父线程反复继续] → launcher 既有批次超时终止，父停止审计记录缺失 task；最终仍由 fail-closed finalizer 判定。
- [报告已输出但终态事件尚未落盘] → 屏障保守地再继续一次，文件锁保证下一次检查读取完整事件。

## Migration Plan

1. 实施时先盘点既有 SEC/Yahoo 路径和兼容接缝，建立三源计划与能力矩阵。
2. 用合成 fixture 验证 loopback、Quote-only allowlist、契约与失败隔离，再显式触发有限真实 OpenD 验证。
3. SEC/Yahoo 基线与 Moomoo OpenD feasibility 独立推进，成功方法按矩阵扩展。
4. 完成核心增量、冻结查询和限定消费后更新新收尾映射；不改历史 cutoff。
5. 回滚仅禁用 Moomoo OpenD adapter/allowlist；用户可独立停止 OpenD，既有来源与历史合格证据继续可读。
6. 截图持仓多证券三源包、实际新增 Evidence 消费和三份普通股报告已经验证；旧失败运行保留，冻结重试保持原身份，新采集使用新 cutoff/run_id。

## Open Questions

Moomoo SG 的实测 OpenD/SDK 版本、逐方法 entitlement、字段覆盖和研究内容可读性由上述固定验证步骤回答；未知值不填写为已验证能力。若官方 Quote API 路线受限，记录阻断，不扩大为抓包、私有端点、破解或购买方案。

## Reference Checks

2026-09-16 核对以下官方说明，仅证明产品/数据说明存在，不证明当前账号权限、自动化许可或实际连通性：
- SEC 公共 submissions/XBRL：[EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)。
- SEC 13F 数据结构：[Form 13F Data Sets](https://www.sec.gov/files/form_13f.pdf)。
- Yahoo 行情来源与延迟：[Exchanges and data providers](https://help.yahoo.com/kb/SLN2310.html)。
- Yahoo 历史数据下载限制：[Download historical data](https://help.yahoo.com/kb/sln2311.html)。
- Moomoo SG 机构展示：[Institutional Tracker](https://www.moomoo.com/sg/support/topic3_908)。
- Moomoo SG 资金流定义：[Trade Overview](https://www.moomoo.com/sg/support/topic3_458)。
- Moomoo OpenD 与账号：[OpenD Overview](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-intro.html)、[Authorities and Quota](https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html)。
- Moomoo Quote API 方法：[Quote API Overview](https://openapi.moomoo.com/moomoo-api-doc/en/quote/overview.html)。
