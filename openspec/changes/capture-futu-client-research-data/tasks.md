## 1. P0 范围、来源准入与能力契约

- [ ] 1.1 盘点 `expand-free-data-holding-research`、暂停的 `us-equity-live-advisory-slice`、现有 Yahoo/东方财富行情、Yahoo 期权、SEC 所有权、公开研报、缓存、PIT 与 MCP 接缝，形成复用点和本 Change 文件归属清单；通过 Git 差异与清单核对证明不修改其他 Change 的任务状态、不覆盖用户已有修改。
- [ ] 1.2 核对当前富途服务条款、隐私/会话说明、客户端研究数据权限和自动化限制，建立带 URL、核对日期、允许用途、禁止用途和 `BLOCKED_BY_POLICY` 条件的来源准入记录；由人工确认该记录后才允许发布 endpoint manifest，不以技术可调用替代上游许可。
- [ ] 1.3 定义 `FutuCapabilityInventory` 与状态转换，覆盖 `option_static`、`option_dynamic`、`capital_flow`、`institutional_two_period`、`insider`、`research_index`、`research_body`；用会话缺失/过期、权限不足、CSRF、签名、设备、挑战、限频、漂移、契约不匹配和可用样例验证状态互斥且未知情况 fail closed。
- [ ] 1.4 定义客户端版本、endpoint manifest、数据集、证券、Capture Session、Evidence 与 `expand-free-data-holding-research` 责任映射关系；用错证券、错 cutoff、不同 run、未来数据和悬空引用样例验证不能因端点可用就宣称研究缺口已补齐。
- [ ] 1.5 更新中文本地操作文档，明确未开户可运行边界、首版不使用 OpenD/OpenAPI/收费 API、用户需自行提供本人会话样本与 secret、禁止自动登录/抓包/破解/设备伪造及失败后的最小用户动作；以文档审查证明不包含真实 host/path/Cookie、个人身份或绕过步骤。

## 2. 会话 Secret、端点清单与 Bootstrap

- [ ] 2.1 定义仓库外本地 session bundle 和 credential reference 契约，支持 Cookie、必要 CSRF、domain/path/secure/expiry 与格式版本；用合法 0600 文件、仓库内路径、组/其他用户可读、缺字段、过期值和符号链接逃逸样例验证只有安全外部路径可被引用。
- [ ] 2.2 实现短生命周期 `FutuSecretLease`，仅在单个批准请求发送边界解析会话材料，完成或失败后释放；用日志、异常、事件、进程参数、环境快照、对象序列化和内存可见接口测试证明其他组件只能得到不可逆 credential reference ID。
- [ ] 2.3 定义 `FutuClientEndpointManifest` Schema，锁定 manifest ID/version、客户端版本、精确 HTTPS host/port/method/path、query/body/header Schema、值域、只读语义、响应类型/大小/Schema/身份锚点、数据集、速率、重试、分页、缓存和批准记录；用缺字段、宽泛域名、任意 URL、未界定 POST 和无身份锚点样例验证拒绝。
- [ ] 2.4 实现仓库外 Bootstrap importer，只接受用户提供的本人客户端只读请求/响应样本，先隔离原件再删除 Cookie、Authorization、token、账号、设备标识和无关字段；用合格行情样本及含账户、交易、认证、互动、未知副作用和秘密回显的样例验证只生成脱敏 manifest candidate。
- [ ] 2.5 建立 manifest candidate → 人工批准 → 锁定版本的发布流程，保存脱敏样本 hash、批准人/时间、条款准入引用和适用客户端版本；用未批准、被拒绝、批准后篡改、hash 漂移和版本回退样例验证 Runtime 只能加载当前明确批准版本。
- [ ] 2.6 建立可提交内容扫描，覆盖 Cookie/token 模式、富途 ID、账号/设备字段、本机绝对路径、完整私有响应和受限研报正文；以包含每类敏感内容的合成差异验证扫描失败会阻止生成可提交摘要，不删除用户原始秘密文件。

## 3. 有界客户端会话 Transport 与真实可行性门槛

- [ ] 3.1 在 `product/mcp/live/` 增加富途专用 session transport，复用现有 TLS 信任、有界流式读取、稳定错误和事件模式；验证非 HTTPS、用户信息 URL、非标准端口、fragment、重定向、非精确 host/path/method 及超大响应均在扩散正文前失败。
- [ ] 3.2 实现 endpoint manifest request guard，只允许由已验证证券、日期、分页、到期日和筛选输入生成清单字段；用额外 header/query/body、重复参数、超长列表、越界日期、账户 ID、任意 POST body 和未批准 endpoint 样例验证网络调用前确定性拒绝。
- [ ] 3.3 实现 Cookie domain/path/secure/expiry 约束及单请求 Secret Lease 注入，禁止跨域/重定向转发和异常回显；用错误域、非安全 Cookie、过期 Cookie、服务端 401/403、重定向及 transport 异常验证秘密不会进入事件、缓存或错误文本。
- [ ] 3.4 实现 Capture Session 共享的请求数、频率、并发、分页、重试和总时长预算；用 429、短暂 5xx、超时、挑战页、权限页和未知异常验证只有清单声明的短暂错误有限重试，安全/身份/契约/会话失败立即锁住受影响 endpoint。
- [ ] 3.5 实现稳定错误分类和端点级熔断，覆盖 `SESSION_MISSING`、`SESSION_SECRET_UNSAFE`、`SESSION_EXPIRED`、`CSRF_REQUIRED`、`SIGNATURE_REQUIRED`、`DEVICE_BINDING_REQUIRED`、`CHALLENGE_REQUIRED`、`ENTITLEMENT_REQUIRED`、`RATE_LIMITED`、`ENDPOINT_DRIFT`、`CONTRACT_MISMATCH` 与 `BLOCKED_BY_POLICY`；用逐类响应 fixture 验证一个端点熔断不会放宽清单、轮换未知接口或关闭无关公开来源。
- [ ] 3.6 在宿主入口增加默认关闭的 Futu session profile 与显式 feasibility 命令，只接收仓库外 secret reference 和已批准 manifest ID，不把秘密交给 Agent；通过聚焦测试证明旧入口与现有来源不变、未显式启用不加载会话或发出请求。
- [ ] 3.7 用户完成本人会话 bundle 和只读样本准备后，以一个批准的证券身份或公开行情 endpoint 执行一次真实无副作用 feasibility；保存实际命令、客户端/manifest 版本、Capture Session、脱敏事件、原始响应 hash、证券身份和结果，不能用合成 fixture 代替。
- [ ] 3.8 对真实 feasibility 作硬门槛判定：成功则记录 `SESSION_REPLAY_FEASIBLE` 并允许进入第 5–7 组；会话过期只在用户人工更新后按既定预算补试，若需破解签名、伪造设备、绕过挑战或违反来源准入则记录真实限制并停止后续数据集实现，不把受限报告写成 Change 完成。

## 4. Capture Session、响应隔离与标准化基础

- [ ] 4.1 定义 `FutuCaptureSession`、请求事件、原始响应记录、能力清单和数据集快照 JSON Schema，统一 session/security/dataset/endpoint/manifest/client/credential-reference、时间、预算、状态、raw hash、Evidence IDs 与失败原因；用合法、错身份、未来时间、重复 ID、缺 raw、hash 漂移和秘密值样例验证。
- [ ] 4.2 实现仓库外 run-scoped `quarantine`、`accepted-raw`、`normalized`、`evidence` 和报告目录及权限检查；用仓库内路径、目录穿越、权限过宽、符号链接、覆盖旧 run 和跨 session 引用样例验证原始响应不能进入 Git 或错误目录。
- [ ] 4.3 实现响应验证流水线，依次检查 HTTP/content type、登录/挑战/权限页面、大小/Schema、证券/市场/数据集/时间身份、禁止账户/设备/PII 字段和分页连续性；用每个阶段的负例证明失败响应停留在 quarantine 且不得生成 Evidence。
- [ ] 4.4 只将完全通过验证的响应写入追加式缓存和 Capture Session manifest，缓存 key 包含 provider、endpoint manifest、客户端版本、security ID、数据集和参数窗口；用错 key、raw bytes 篡改、跨版本复用、过期缓存和不同证券碰撞样例验证 hash 与身份闭合。
- [ ] 4.5 生成不含 header、Cookie、完整 query 和异常正文的脱敏事件及 capability report；用会话秘密、账号、设备、资产、订单和私人消息混入样例验证可提交报告只保留 endpoint ID、状态、字节数、时间、hash 和精确限制原因。

## 5. 首个核心切片、资金流与动态期权

- [ ] 5.1 在 feasibility 通过后，用当前真实 `FutuCapabilityInventory` 选择首个核心数据集；默认选择 `capital_flow`，只有其真实受限而 `option_dynamic` 可用时才改选动态期权，并在选择记录中列出 endpoint、字段、权限、请求预算和能为投资研究新增的信息。
- [ ] 5.2 定义并实现 `FutuVendorFlowSnapshot` Normalizer，保留整体及特大/大/中/小单等实际字段、周期、币种、适用市场、最后有效时间、定义版本和 `VENDOR_CALCULATED_FLOW`；用正负值、缺单位、缺时间、不同周期、图形无数值和字段漂移样例验证不猜单位、不合并口径、不生成机构买卖或未来方向结论。
- [ ] 5.3 对一个真实普通股完成资金流 `CLIENT_SESSION_HTTP → quarantine/validate → Normalize → Cache → Evidence`，保存 Capture Session 与 raw hash；若当前会话不可得则记录精确状态和影响，不用模拟或 UI/OCR 数据替代真实结果。
- [ ] 5.4 定义并实现 `FutuOptionSnapshot`，分离 `option_static` 与 `option_dynamic`，限制到期日、合约数、分页和时间差，保留合约身份、bid/ask、last、volume、open interest、IV、Greeks、行情级别和最后有效时间；用静态链、过期报价、倒挂价差、缺字段、重复合约、不同快照时间和错误乘数样例验证。
- [ ] 5.5 对一个真实普通股采集多个到期日/行权价的期权数据；动态字段完整时生成冻结 Evidence，只有静态链时输出 `STATIC_CHAIN_ONLY` 并列出缺口，不生成价差、活跃度、波动结构或资金方向研究已完成的声明。
- [ ] 5.6 将首个真实可用核心数据集接入现有 PIT Gate 和冻结 MCP Query，以同一标的证明 `Capture → Normalize → PIT → MCP` 全链路；验证未来/缺时点/错证券/错误 session/未冻结/悬空 Evidence 被拒绝，只有合格结果可标记 `RESEARCH_INPUT_VALIDATED`。

## 6. 两期机构、内部人与研报资料

- [ ] 6.1 定义并实现 `FutuSecondaryOwnershipSnapshot`，分别表达机构两期和内部人资料，保留机构/人员身份、证券、报告期、公开/更新时间、原值、变化、交易类型、分页完整性、显示来源和 `SECONDARY_VENDOR`；用单期、不可比口径、修订、拆股、分页缺失和未来公开样例验证。
- [ ] 6.2 将富途所有权 Evidence 与 SEC 原始披露并列接入现有 `ownership-disclosure` 输入；用数值冲突、报告期不同、富途显示 SEC 来源但未读取原文和只有供应商排名样例验证不会覆盖 SEC、升级来源层级或声称机构趋势。
- [ ] 6.3 定义并实现 `FutuResearchCandidate` 与 `FutuResearchDocument`，保留标题、作者/机构、发布日期、文档定位、访问状态、修订/转载关系、正文 hash 与必要片段；用完整正文、仅标题、仅摘要、转载、修订版、缺日期、登录/权限页及临时 URL 失效样例验证候选不冒充正文。
- [ ] 6.4 对当前账号合法可读的真实研报执行列表发现和至多一个正文样本采集，全文仅保存在权限受限本地目录；正文不可得时保存候选及准确访问缺口，不绕过订阅、不把完整正文或临时访问参数写入 Git/Agent 上下文。
- [ ] 6.5 将合格正文 Evidence 接入现有 `research-report-analysis` 输入，验证事实/转引/观点/预测/假设、发布日期和来源定位仍由现有 Skill 解释；无正文、单份正文或不可比版本时不得宣称完成多研报对比。

## 7. 冻结 MCP、专业 Skill 与 Agent 安全边界

- [ ] 7.1 增加或扩展数据集级只读 MCP 契约，只接受 `security_id`、`dataset`、`decision_cutoff` 和 `capture_session_id`，返回版本化能力清单、冻结快照或 Evidence；用任意 URL/header/body、secret reference、Bootstrap、quarantine、账户字段和新网络请求参数验证 Schema 及实现均拒绝。
- [ ] 7.2 将合格富途 Evidence 映射到现有 `options-market-structure`、`ownership-disclosure`、`research-report-analysis` 及适用市场研究输入；验证采集层不生成 thesis、action、confidence、统一评分或硬编码投资判断，也不新增 Futu 专属投资 Agent。
- [ ] 7.3 验证 Agent 运行时权限只包含冻结 Evidence 查询，无法加载 session bundle、endpoint importer/transport、原始响应或客户端控制；用越权 Tool 请求、错误 Capture Session、Gate 外 ID 和过期 Evidence 样例证明在秘密/网络访问前确定性拒绝。
- [ ] 7.4 验证多 Agent 查询同一 Capture Session 获得相同冻结快照和引用，新的到期日、报告期或正文请求必须先由宿主生成新 Capture Session；用并发查询、缓存命中、跨 session 混用和 decision cutoff 差异样例证明不会在推理期间临时采集。

## 8. 真实有限纵向验收与原 Change 映射

- [ ] 8.1 在当前 Mac 生成真实 `FutuCapabilityInventory`，记录客户端和 endpoint manifest 版本、匿名会话状态及七类数据集的 route/status/fields/last_success/reason；逐项以真实响应或权限状态核对，不能用未尝试、客户端页面存在或合成 fixture 代替。
- [ ] 8.2 以一个当前普通股持仓和全新 Capture Session 完成至少一个动态期权或资金流核心数据集的真实 `CLIENT_SESSION_HTTP → Normalize → PIT Gate → MCP Query`；保存实际命令、run/session ID、输入/输出、raw 与 artifact 完整 hash、加载版本和结果，缺少该链路则任务与 Change 保持未完成。
- [ ] 8.3 对期权、资金流、机构/内部人和研报四组目标分别形成真实成功证据或精确限制状态；只有成功数据集才按同一入口扩展至当前普通股持仓，受限项列出账号权限、endpoint、字段、研究影响和最小外部前置条件，不循环猜源或购买权限。
- [ ] 8.4 只对真实可得数据运行至多一次受影响的 GPT-5.6 Terra 专业 Skill 消费检查，生成中文与 JSON 产物且不启动 Skeptic/CIO/Risk；评价是否新增具体研究信息、引用是否闭合、是否误解供应商资金流/单次期权/二级机构/研报层级，失败时保留原始产物不重复调用粉饰。
- [ ] 8.5 将合格产物与 `expand-free-data-holding-research` 收尾材料建立显式证据映射，逐项核对证券、基础 run、PortfolioHandoff/请求、decision cutoff、Evidence Gate、来源、报告 Schema 和实际研究内容；晚于历史 cutoff 的当前快照只形成新时点产物，不静默拼入旧 canonical 包。
- [ ] 8.6 生成目标矩阵与 capability report，分别标记 `IMPLEMENTED`、`SESSION_REPLAY_FEASIBLE`、`RESEARCH_INPUT_VALIDATED`、`STATIC_CHAIN_ONLY`、`SOURCE_LIMITED` 和 `BLOCKED_BY_POLICY`；验证一个成功数据集、有效 Cookie 或本 Change 存在不会把其他数据集及原多维研究 Change 写成完成。

## 9. 聚焦检查、独立复核与人工收尾

- [ ] 9.1 运行受影响的 secret、manifest、Bootstrap、transport、quarantine、Schema、Normalizer、缓存、PIT、MCP、权限和来源路由聚焦测试及 OpenSpec strict validate；记录实际命令、测试数量、结果和源码快照，不运行完整 Council、Regression、Replay、Calibration、Ablation 或 Promotion Gate。
- [ ] 9.2 对仓库差异、run 产物和可提交评审材料执行敏感信息检查，覆盖 Cookie/token、富途 ID、账号、设备、账户/订单字段、本机路径、完整私有响应和受限研报正文；发现疑似秘密、未经批准 endpoint 或 hash/权限失败时停止相关收尾，不提交或推送。
- [ ] 9.3 由未参与实现的 Reviewer 只读核对实际差异、条款准入、manifest 批准记录、真实 feasibility、能力清单、Capture Session、原始 hash、Evidence、PIT/MCP 产物、专业报告和安全负例，逐项对照 Specs/Tasks 给出 PASS/FAIL；缺证据时提出具体宿主补跑需求，不自行启动产品或扩大测试。
- [ ] 9.4 汇总已验证数据集、真实限制、外部前置条件、端点漂移/会话/版权残余风险、未实现范围及对 `expand-free-data-holding-research` 的实际增量，取得人工完成批准；若 feasibility/核心真实链路缺失、全部 `SOURCE_LIMITED` 或敏感信息未处理，不得申请完成、归档、提交或推送。
