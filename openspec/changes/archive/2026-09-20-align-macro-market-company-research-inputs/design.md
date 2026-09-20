## Context

参见 [proposal.md](proposal.md) 的 Why。当前真实执行已经由 `runtime_company_analyst` 与 `runtime_market_catalyst` 承担 capability-first 研究，三源补充链路也已有独立 source plan 和 capability matrix；问题主要来自三套表达未闭合：退役 Council profile、当前多维 stage 绑定、产品/规格状态文字。

现有 `research-dimension-report/1.1.0`、`holding-research-bundle/1.1.0`、stage/dispatch 1.x 均把 `MACRO_MARKET` 作为单项枚举。`live-us-equity/4.0.0` 又被历史 package 和确定性校验锁定，原地增加 Agent/provider 会破坏兼容语义，也会误把旧全 Council profile 恢复为当前入口。

## Goals / Non-Goals

**Goals:**

- 用一个机器可读入口表达当前研究域、capability、Agent、provider plane 和状态来源，并让新运行实际锁定它。
- 在不增加 Agent 的前提下，把宏观环境和市场状态变成可独立派发、验收和降级的报告。
- 让新旧产物通过 schema version 明确共存，不重写历史 hash。
- 让产品说明只描述当前事实和数据集限制，不用已归档 Change 充当未来状态。

**Non-Goals:**

- 不恢复已退役的 full live Council 入口，不改变 CIO、Skeptic 或风险决策流程。
- 不新增 Research Editor、Macro Agent、Market Agent 或 provider-specific Agent。
- 新来源仅服务三域清单中的具体缺口，优先免费官方 API、RSS 和公开正文；不扩大 OpenD allowlist，不接入 Cookie、交易或账户能力。
- 不改变本地研究浏览器的信息架构；浏览器只消费新版 capability 映射并保持历史展示兼容。
- 只审计和收缩旧 live 相关代码、测试与产物；不开展全仓库清理，不启动 Promotion、Regression、Ablation 或完整 Runtime Eval。

## Decisions

### 1. 新增当前研究拓扑清单，而不修改退役 profile

新增一个版本化 `holding-research-input-topology` 清单，建议位于 `product/profiles/holding-research-inputs.json`。它是当前研究输入发现与运行准备的唯一入口，至少包含：

- `profile_id`、`schema_version`、`lifecycle_status=CURRENT`；
- Company / Macro / Market 域到 capability、Agent、Skill、scope 和 output contract 的映射；
- base/disclosure、official-macro、research-supplement 三类 provider plane；
- `research-source-policy.json`、`research-supplement-source-plan.json`、Moomoo OpenD manifest 与 capability matrix 的路径、版本和内容 hash；
- `live-us-equity/4.0.0` 的 `RETIRED/COMPATIBILITY_ONLY` 引用及 successor 指向。

多维 stage 在准备新运行时解析该清单，并把解析后的版本/hash及受影响来源文件 hash 写入 run manifest。配置中的 Agent/capability 若与代码支持集合不一致，必须在模型调用前失败。历史重放继续直接使用历史 package 锁定的 `live-us-equity/4.0.0`，不要求它通过当前拓扑校验。

选择该方案而不是直接给 `live-us-equity.json` 增加 Market Catalyst/Moomoo，是因为后者既改变冻结历史语义，又把已退役 full Council profile 错当成当前多维研究 profile。选择一个小型引用清单而不是复制全部 provider 配置，可避免形成第二份来源真相。

### 2. 新版契约拆分为 `MACRO_CONTEXT` 和 `MARKET_STATE`

新增 `research-dimension-report/2.0.0` 与 `holding-research-bundle/2.0.0`，并同步提升多维 stage、dispatch、invocation 和 execution proof 版本。新枚举移除写入侧的 `MACRO_MARKET`，加入：

- `MACRO_CONTEXT`：利率、通胀、经济活动、政策环境、发布时间与修订；
- `MARKET_STATE`：大盘、风格、波动、信用/流动性、市场结构与风险状态。

两者均使用 `SHARED_MARKET` scope，首期绑定同一个 `runtime_market_catalyst`，但生成不同 task、invocation manifest、输入问题、报告和 coverage。每只证券的传导解释仍放在各自共享报告中，以 `security_ids` 和显式 claim/assumption 关联，不拆成重复逐股采集。

选择版本化拆分而不是在 `MACRO_MARKET` 内增加子字段，是因为独立完成状态、失败隔离和展示需要稳定 capability identity。选择复用 Market Catalyst 而不是新增两个 Agent，是因为职责仍属于相邻的跨市场解释，当前没有消融证据支持扩大 Agent 拓扑。

### 3. 旧产物只读兼容，不自动升级语义

保留 1.1 schema、validator 与渲染路径。读取器按 `schema_version` 路由：

- 1.1 继续接受历史 `MACRO_MARKET`；
- 2.0 只接受 `MACRO_CONTEXT` 与 `MARKET_STATE`；
- 将历史 1.1 报告展示在新界面时标为 `LEGACY_COMBINED_COVERAGE` 或等价兼容标签，不能自动生成两个 2.0 PASS。

若显式把旧报告作为新包的补充材料，package provenance 必须记录旧版本、原 hash 和“未拆分”限制；新版两个 capability 的 coverage 仍根据各自真实报告或具体缺口决定。回滚时停止创建 2.0 新运行即可，1.1 读取能力不受影响。

### 4. Provider 拓扑引用权威来源政策

拓扑清单不复制 endpoint、字段 allowlist 或权限状态，而是引用现有 source policy、supplement source plan、OpenD quote manifest 和能力矩阵。运行准备器验证引用文件存在、版本/hash 匹配，并把 provider plane 的解析快照写入 run manifest：

- 基础身份/行情/披露层继续表达 Nasdaq、Yahoo、Eastmoney、SEC 等现有职责；
- 官方宏观层引用当前受批准的官方宏观来源政策；
- 研究补充层表达 SEC + Yahoo + Moomoo SG 的逐数据集职责与真实状态。

Moomoo 始终标记 `service_region=SG`、`access=loopback_opend_quote_only`。能力矩阵中的 AVAILABLE/PARTIAL/SOURCE_LIMITED 等状态传到本次 coverage，不把历史成功固化成永久可用，也不因 OpenD 失败阻断 SEC/Yahoo。

### 5. 文档状态从 Change 名称改为能力证据

更新产品说明和主规格时，以当前能力矩阵、真实消费证明和批次 coverage 描述状态。归档 Change 只作为历史实现 provenance，不再出现在“未来延期至”措辞中。文档校验增加聚焦断言：

- 当前入口能找到 Company Analyst、Market Catalyst 和 Moomoo supplement；
- 退役 profile 明确可辨；
- 当前文档不再把 `capture-futu-client-research-data` 当未来事项；
- 不出现 Cookie、Trade Context 或账户能力扩张。

## Risks / Trade-offs

- [多维输出契约不一致或纠正循环失控] → 按下述输出交付闭环统一结构定义，单任务最多一次纠正；用确定性失败样例验证上限及终态后才运行真实模型，不以一次成功宣称长期稳定。

- [候选 Skill 依赖 WorkBuddy 专属服务，或免费接口覆盖不足] → 实施前核实原包与真实返回；保持官方公开来源路径，来源不足不以配置、安装或空报告冒充完成。
- [移除旧创建链路影响共享模块或历史读取] → 逐符号核对生产调用方和历史读取样本，先验证替代读取路径再退役；不为保留一个旧命令而保留全部旧编排。

- [能力拆分增加一次 Market Catalyst 调用及等待成本] → 两项任务共享冻结资料并允许有界并行；验收记录时延和实际调用数，不再追加 Agent。
- [新旧 schema 双轨增加校验复杂度] → 仅按显式 `schema_version` 路由，禁止猜测升级；保留聚焦历史 fixture 测试。
- [拓扑清单与代码绑定再次漂移] → 新运行必须同时校验清单版本/hash与代码支持集合，且 run manifest 保存解析快照。
- [provider 视图被误读为实时健康检查] → 状态携带 `as_of`/观测时间和能力矩阵引用；拓扑表达职责，运行 coverage 表达本次可用性。
- [Market 与证券技术结构边界重叠] → `MARKET_STATE` 只处理共享市场环境；单只证券的趋势、量价、相对强弱继续属于 `TECHNICAL_STRUCTURE`。
- [文档改正被误解为所有数据已完成] → 明确区分“链路已实现/历史已验证”和“当前证券、权限、cutoff 可用”。

## Migration Plan

1. 增加当前拓扑清单及确定性 loader/validator，先验证它能表达现状且不改变旧入口。
2. 增加 2.0 schemas 与双版本读取；用 fixture 证明 1.1 历史包仍可校验。
3. 更新 capability 常量、stage/dispatch、Agent/Skill 输出协议和 bundle 聚合，使新运行分别派发 Macro/Market。
4. 将拓扑及 provider plane 快照写入新运行 manifest，增加漂移和降级测试。
5. 更新产品说明、主规格映射和只读展示兼容层，移除过期延期文字。
6. 执行聚焦确定性测试及当前控制面允许的专项 validator；仅当实现实际改变模型分派/输出后，在获得显式授权的情况下按宿主 launcher 运行最小必要真实 Smoke。裸 `self-check` 若被控制面拒绝，不得记为 PASS。

以上结构迁移还 MUST 完成下述数据交付和退役切片；仅完成 1–6 的配置/契约迁移不能申请归档。

## 数据获取与消费交付

### 最低覆盖与来源选择

三域是研究分类，来源可跨域复用。沿用既有准备、缓存、PIT、冻结 MCP、研究和报告入口，不另建新闻平台或编排器。每个数据集登记字段、证券/市场范围、主备来源、费用/认证、观察/发布/获取时间、时效、修订、请求预算、原文定位和消费报告。静态来源政策与每批实际能力观测分开锁定，不把运行观测状态写成永久能力。

| 域 | 本次核心交付 | 复用与新增候选 | 受限增强 |
| --- | --- | --- | --- |
| Macro | CPI/就业、收益率、经济活动指标、最新适用央行政策原文及已公布发布日历 | 复用 BLS/Treasury；优先 Federal Reserve 公开发布、BEA GDP/PCE，必要时 FRED | 全球央行广覆盖、地缘报道、无法还原的历史 vintage |
| Market | 大盘与明确板块基准、跨资产代表序列、波动/信用代理、限定窗口市场新闻 | 复用 Yahoo 与确定性计算；候选 FRED 信用指标、EIA 能源、官方/发行方公开新闻或允许访问的新闻服务 | 专有资金仓位、实时全市场宽度、私募信贷、商业指数与付费新闻全文 |
| Company | 全部确认普通股的已有财务/披露基础、去重且可定位的 issuer/IR 正文、指引与预期分类、公司/行业研究材料发现 | 复用三源；补充公司 IR 公开资料 | 公开独立研报全文、完整投行全文库、全市场一致预期历史、付费电话会全文 |

Market 的初始样本范围为美国大盘、持仓相关板块，以及债券、美元、能源或贵金属中的至少两类代表序列；ETF 代理明确标注，不能冒充现货、指数原值或资金流。波动至少具有确定性历史波动，信用至少一种明确口径的信用指标或代理，禁止以股票波动替代信用。新闻默认过去 24 小时，按规范 URL/原始来源与内容去重，保留原文、发布时间、证券/主题关联及纠错版本；窗口内零结果必须保留实际请求和覆盖范围。日历只表示已公布事件，不以模型预测补全。

新来源先完成有限可行性验证：默认每个数据集最多两个候选，每个候选一次正常流程、最多一次失败重试；正常分页独立声明上限。候选选择与预算在调用前记录。没有可靠时点或只有摘要的结果按线索处理，不进入正文 Evidence。新增普通来源包与已有三源 supplement 包分别保存，统一经现有 Gate 准入，不扩写三源包为任意 provider 容器。

### wb-finance-skill 可移植性核实

优先取得原始分发地址或用户提供的目录，读取完整 Skill、脚本和依赖；记录版本/hash、许可、宿主专属工具、认证方式、免费额度和美股字段。当前未取得原包，不能把第三方介绍当作认证或可用性证据。公开第三方归档 `https://github.com/infometa/workbuddyskills` 仅用于发现和审阅候选，首批明确核实：

- `wb-finance-skill`：若能取得原始分发或用户提供副本，优先检查其真实工具绑定和数据集映射；
- `westock-data`：核实归档 Skill、调用脚本及其声明的 npm/CLI 依赖，重点验证美股行情、财务、公告/研报及市场数据的真实字段、来源、时间语义和使用条件；
- `neodata-financial-search`：核实归档内容实际调用的服务、认证和检索结果来源，重点验证新闻、市场宽度、宏观/公司材料的可取得性和正文定位。

归档出现、README 描述或一次安装成功均不构成准入。每个候选必须锁定归档 commit、相对路径、Skill/脚本 hash、依赖包精确版本及完整性信息，确认许可和网络端点，并以相关美股数据集的有界真实返回闭合字段、`source_id`、`as_of`、`retrieved_at` 和原文定位。含 `npx -y`、浮动 latest、远程脚本执行或通用 shell 权限的候选不得原样进入产品运行；必须先完成代码审阅，再以固定依赖、最小网络 allowlist 和确定性 adapter 封装，Agent 只读取冻结 MCP，不直接执行第三方 Skill/CLI。

候选按数据集而不是按整包准入。`westock-data` 预期主要候选于 Market 行情/板块/跨资产和 Company 财务/材料发现，`neodata-financial-search` 预期主要候选于 Macro/Market 新闻与 Company 公开材料检索；这些只是待验证映射，不预先认定覆盖。允许复用经验证的独立工具，经受限适配器接入；不复制另一宿主的私人会话或假定其登录权限通用。未取得原包或验证失败时明确 `NOT_VERIFIED`/`REJECTED`，继续官方公开来源方案，不将任一候选设为整个 Change 的前置条件。

### 材料归属与完成边界

公司研报由 Company Analyst 消费；宏观、市场策略正文分别进入 `MACRO_CONTEXT`、`MARKET_STATE` 的输入，并由 Market Catalyst 解释。沿用现有文档引用结构，更新受影响的准备路由和工具权限，不能仅修改名称。研报与新闻都是材料类型；新闻转载不能算多份独立证据，机构预测不能提升为公司事实。

核心项须有真实获取 → 标准化 → PIT/Gate → 冻结 MCP → 对应研究引用的证据。三域使用同一确认 Handoff 和 cutoff，保留每股覆盖。验收至少包括新增政策正文、市场新闻/跨资产输入和一份自动发现、去重且可定位的 issuer/IR 正文；同一 filing 的目录标题不得作为独立正文，正文 hash 必须对应实际可查询范围。公司 IR 只能证明公司材料，不能冒充独立投行研报。公开独立研报作为增强项确实受限时记录候选、全文尝试及影响，须人工明确接受该受限项，不能默认以空结果收尾。其他核心输入缺失保持未完成，增强项允许准确受限。用户无需手工找新闻或拼包。

## 当前阻塞的输出交付与验收闭环

本节补充 Company 消费验收所需的最小执行修复；下文旧 live 退役边界继续适用。

### 统一草稿、报告与校验的结构契约

当前草稿从 1.1 Schema 派生，2.0 报告的若干嵌套字段仅声明为 object，额外约束分散在 Python。实施须为当前版本确定一份权威嵌套结构定义，使草稿和最终报告使用相同的 claims、limitations、data_gaps、documents 等字段结构；允许确定性封装器添加冻结身份与执行元数据。不得修改历史冻结的 1.1 产物。当前运行锁定草稿、报告及其实际依赖的契约版本/hash；保留证据闭合、时间与身份等语义校验，不把 Schema 通过等同于研究有效。

先核实子 Agent 实际输出入口是否支持原生结构约束以及约束是否真正生效；仅将 output_schema 写入 invocation 或提示词不算强制约束证明。优先使用现有入口能力，无原生支持时通过现有 Hook/校验边界闭合，不为此新增执行后端。嵌套结构校验必须在封装后的派生计算、渲染和正式持久化之前完成，错误返回稳定错误码、字段路径和预期结构，不泄露正文或凭据，不再以原始 KeyError 表示契约失败。

### 每任务最多一次原 Agent 纠正

在既有多维执行链路内向原 Agent/原会话返回原草稿、锁定契约与具体校验错误；纠正期间任务仍未成功，不能启动下游。每任务初次提交后最多允许一次纠正，跨 Hook 或父线程重派不能重置预算。格式错误由 Agent 按契约纠正；缺少 impact 等实质内容时只能由原 Agent 根据本次冻结资料补充，必须保留修改前后输出与关联记录，并重新执行完整结构、来源、身份、PIT 和证据校验。Python 与父线程不能代填研究判断、删主张以掩盖失败、伪造引用或放宽门禁。

身份错配、越权引用、来源或时点违规不能作为纯格式错误进入该纠正路径，必须记录准确失败；普通研究证据不足仍使用合法缺口报告。原会话无法续接、超时或纠正后仍非法时形成明确失败终态，不自动另起 Agent 重新研究。只保存通过全部校验的正式报告，原始失败尝试不可覆盖；不新增通用重试服务或跨运行报告导入能力。

### 依赖推进与失败归集

沿用现有调度器：FUNDAMENTAL_EVENT 通过结构与证据校验并保存正式报告后，才解锁 RESEARCH_REPORT。初次拒绝进入纠正时不提前登记终态；预算耗尽或不可纠正失败后，其下游形成 dependency-blocked 终态，保留既有 Hook 拒绝证明，无须等待不存在的报告。独立的 Macro/Market 继续执行。父流程须区分调度终态齐全、报告有效、核心资料消费完成；结构可读取或启动器返回 PASSED 均不能覆盖失败任务。

### 验证顺序与完成边界

1. 确定性验证已出现的缺 question、额外顶层字段、limitations 类型错误和 gap 缺 impact，以及错误反馈、一次纠正成功/耗尽、身份与引用违规拒绝、依赖推进及失败终态。用这些样例检验完整结构约束，避免每出现一个字段才追加检查。
2. 按既有宿主 launcher 验证当前实现下的 Company FUNDAMENTAL_EVENT → RESEARCH_REPORT 正式依赖链。现有定点入口若不支持依赖任务，仅增加该链所需的最小选择能力，锁定同一 Handoff、Gate、cutoff 与版本，保持正式 dispatch/Hook/finalizer；不手工拼包或注入其他批次报告。
3. Company 链通过后完成一次当前实现版本的同批三域验收，逐股证明 issuer 正文查询、实际引用、原文定位与去重身份；独立研报正文保持用户已接受的 SOURCE_LIMITED。合法 LOW_CONFIDENCE 不自动阻塞，但不能替代缺失的核心材料消费。若实际覆盖不足，准确记录未完成。
4. 核对 v18 INDUSTRY_COMPARISON 引用失败：本次改动引入的回归必须修复并补证；既有且无关问题须提供可比基线与不影响核心验收的证据，单独披露，不能据此把全包失败改记为全包通过。既有核心要求仍适用，不因归因而自动豁免。
5. 重新独立复核，再取得人工完成批准。一次真实成功仅证明本次交付闭环，不构成长周期可靠性、Eval 或 Promotion 证明；本轮需求更新不启动模型或追加无限重试预算。

Task 5.5 负责正文获取、分类、去重和可查询准备证据；Task 7.3 负责正式 Agent 的实际消费证据。前者完成不能替代后者，既有独立复核 FAIL 保留为历史记录，待补证后重新出具结论。

## 旧 live 定向退役

以 `us-equity-live-advisory-slice-cleanup-inventory.md` 为历史基线，重新核对当前调用关系。清单必须逐文件/符号记录当前消费者、历史消费者、处置、验证及恢复方式：

- 已退役：旧 batch 与宿主 `--profile`，验证拒绝行为继续存在。
- 重点候选：内部 `prepare-live`、旧 full live Council 创建/派发、专属 prompt、测试和文档；无现行用途者删除或明确拒绝新运行，而非只加 retired 标签。
- 共享保留：采集、冻结、原始数据验证、Gate、当前 MCP；混合文件只移除旧分支，不按 `live_*` 名称整文件删除。
- 历史保留：冻结报告、profile/schema hash 和必要只读校验/渲染；历史可读取不要求恢复已退役模型调用能力，仍在规格中承诺的显式 Replay 路径必须核对并保留或先调整相应规格。
- 产物候选：重复或被取代的日志、缓存和中间结果。未跟踪私人研究、有效验收证据、归档主记录、存在引用或无法恢复的文件不删除。Git 内目标确认恢复 commit，外置产物先建立明确备份/迁移清单；本轮只授权需求设计，实际删除属于后续 apply 的审定清单。

先验证当前三域路径与保留的历史样本，再移除无用旧创建分支；重跑受影响聚焦检查，确认无悬空引用。审计必须把符号分成“当前生产调用”“历史只读/Replay”“测试专用”“零消费者”四类；当前代码仍调用的 `live_*` 共享符号必须先迁移到中性模块或由当前等价实现替代，不能因文件名含 live 就删除。只有零当前生产调用、必要历史样本可读、旧入口 fail closed、当前入口前后基线一致四项同时成立，才允许删除旧创建/派发实现及其专属测试。文档体积小，优先减少运行与维护复杂度，不设删除数量或空间指标，也不新增通用兼容平台。

回滚时停止选择 2.0 作为新运行默认版本，保留所有已生成 2.0 产物与其 validator；不得删除或重写 1.1/2.0 历史产物。若 2.0 尚未产生真实运行，可回退默认指针但保留测试 fixture 作为迁移证据。

## 当前运行安全与分阶段启用

本 Change 同时触及来源、能力枚举和旧 live 代码，实施不得一次性替换默认链路。按以下顺序推进：

1. 先冻结当前 Handoff → 资料准备 → Gate/MCP → dispatch、SEC/Yahoo/Moomoo 降级、1.1 历史读取和退役入口拒绝行为的聚焦基线；
2. 以非默认配置加入新 provider registry、adapter 和 2.0 双版本读取，只运行确定性 fixture 与限定真实取数，不改变当前默认指针；
3. 分别证明 Macro、Market、Company 核心数据集闭环，并验证任一新候选超时、限流、字段漂移或拒绝访问时只降低对应数据集状态，不使既有三源或其他域失败；
4. 通过显式 topology/schema 版本选择将新运行切换到 2.0；若准备或校验失败则 fail closed，并允许运维回退默认指针，不得把无效 2.0 运行静默改写为 1.1；
5. 新链路稳定且调用审计证明无当前消费者后，再退役旧 live 创建/派发分支。历史读取/Replay 与新运行创建必须使用不同的显式入口，避免兼容路径重新启用旧模型调用。

来源合并遵循逐数据集优先级和冲突保留：官方披露/统计原文优先作为事实锚点，Yahoo/Moomoo/经验证候选按已声明职责补充；同字段冲突不得静默覆盖，必须保留来源、时点、口径和选择理由。第三方来源包、缓存和错误不得写入或改变既有三源冻结包。
