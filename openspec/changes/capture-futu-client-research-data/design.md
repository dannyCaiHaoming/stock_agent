## Context

见 [proposal.md](proposal.md) 与 [specs/futu-readonly-research-data/spec.md](specs/futu-readonly-research-data/spec.md)。仓库已有 Yahoo/东方财富行情、Yahoo 期权尝试、SEC/宏观/研报资料、`LiveFact`、追加式缓存、PIT Gate、run-scoped 产物和 `live_evidence.query`，但现有免费来源未稳定补齐动态期权、供应商资金流、两期机构持仓与部分研报正文。

用户当前只有未开户的富途牛牛账号，已明确首版不采用 OpenD/OpenAPI、不购买收费 API，而希望复用本人已登录客户端的 Cookie 会话执行只读研究查询。该路径依赖未公开且可能变化的客户端端点；Cookie 还可能不足以独立认证，请求可能同时依赖 CSRF、动态签名、设备绑定或挑战状态。因此设计必须先证明一个无副作用请求可安全重放，再决定是否继续构建数据集适配，不能在未知可行性上预先承诺全部字段。

现有 `product/mcp/live/` 已采用锁定域名/路径、禁止重定向、有界读取、请求预算、来源准入、身份校验和外部缓存路径等模式。本 Change 复用这些边界并扩展会话秘密与端点 manifest，不另造通用爬虫、浏览器自动化平台或投资 Agent。

## Goals / Non-Goals

**Goals:**

- 以用户本人显式导出的客户端会话材料，在 macOS 宿主上形成实验性、显式启用、严格只读且可版本化的富途研究资料入口。
- 在任何数据集实现前，以一个公开行情或证券身份查询完成无副作用可行性证明，并准确区分 Cookie、CSRF、签名、设备绑定、权限、限频和端点漂移问题。
- 将端点 Bootstrap、人工批准和运行时采集分开，使 Runtime 只能执行已锁定查询，不能动态探测私有接口。
- 让动态期权、富途口径资金流、两期机构/内部人资料和合法可读研报按各自语义进入现有 Evidence、PIT、MCP 与专业 Skill 接缝。
- 确保秘密、账号/设备字段和受限制正文不进入 Git、日志、Agent 上下文或可提交评审材料；出现意外敏感响应时先隔离再失败。
- 允许端点按数据集独立熔断与回滚，不覆盖或破坏 Yahoo、东方财富、SEC、宏观和公开研报等既有来源。

**Non-Goals:**

- 不实现 OpenD/OpenAPI、`futu-api` SDK、收费行情采购或开户流程；这些路线只可在未来新授权下另行规划。
- 不自动读取、解密、复制或导出富途客户端 Cookie 数据库、Keychain、登录密码、设备认证或刷新凭据；会话材料必须由用户本人显式提供。
- 不实现 TLS 中间人、客户端注入、二进制反编译、动态签名破解、设备伪造、验证码/风控/反自动化绕过或端点扫描。
- 不通过 Accessibility、截图或 OCR 作为首版数据来源，也不让 LLM 操作富途客户端或浏览器。
- 不访问账户、持仓、资产、订单、交易、入金、转账、消息、社区互动、订阅购买或设置修改接口；未开户状态不会放宽此边界。
- 不把供应商指标升级为原始披露，不把单次期权快照解释为历史变化或买卖方向，不把研报列表/摘要冒充正文。
- 不新增 Options Agent、Flow Agent 或 Futu Agent；不启动 Skeptic、CIO、Risk、完整 Council、Regression、Replay、Calibration、Ablation 或 Promotion。

## Decisions

### 1. 采用单一客户端会话适配器与现有 Evidence 主干

数据流固定为：

```text
HoldingResearchRequest
  → FutuCapabilityInventory
  → FutuClientSessionAdapter
      → FutuSecretLease
      → FutuClientEndpointManifest Guard
      → Bounded HTTPS Transport
      → Response Contract + Security Identity Check
  → Quarantined Raw Response + FutuCaptureSession
  → Dataset Normalizer
  → LiveFact / ResearchDocument
  → Existing PIT Gate
  → Frozen read-only MCP Query
  → Existing Specialist Skill
```

`FutuClientSessionAdapter` 只负责批准端点的请求与响应验证；Dataset Normalizer 负责证券身份、单位、时间和供应商语义；现有 Gate/MCP/Skill 继续负责截止点、引用闭合与研究解释。所有上层事实保留 `capture_method=CLIENT_SESSION_HTTP` 和 endpoint manifest 版本。

备选方案是保留原设计的 OpenD + UI 双适配器。未采用，因为它违反用户当前不使用 OpenAPI、希望复用客户端会话的明确约束，也会同时引入三套权限模型。另一个备选是把 Cookie 注入通用 HTTP client 交给 Agent；未采用，因为任意 URL、header/body 和凭据暴露无法满足只读与最小权限要求。

### 2. 把无副作用 feasibility spike 设为硬实现门槛

P0 先选择一个不涉及账户、设置或互动的证券身份/公开行情查询。只有以下条件全部满足才允许进入数据集实现：

- 请求来自用户本人显式提供的客户端样本；
- 目标为已核对的富途官方 HTTPS host；
- Cookie/必要 CSRF 由 secret reference 注入，日志和产物不含秘密值；
- 响应能绑定请求证券与数据集，并符合有限 Schema；
- 重放不会改变服务端或客户端状态；
- 不依赖破解签名、伪造设备、验证码、挑战绕过或付费权限规避。

若失败来自会话过期，允许用户人工更新会话后在既定一次补试预算内重试；若失败来自 `SIGNATURE_REQUIRED`、`DEVICE_BINDING_REQUIRED`、`CHALLENGE_REQUIRED` 或 `BLOCKED_BY_POLICY`，停止当前路线并保留受限结果，不继续搭建空壳数据集适配。

备选方案是先实现所有 Schema 与解析器再测试真实 Cookie。未采用，因为私有端点可行性是整个路线的外部前置条件，失败时大量实现不会增加产品信息。

### 3. 会话秘密通过短生命周期 Secret Lease 使用

首版支持一个仓库外的本地会话 bundle，由宿主配置引用而非把路径或值传给 Agent。bundle 至少声明格式版本、Cookie 集合及端点明确需要的 CSRF header；实际秘密值只在 transport 发出一个批准请求前读取为 `FutuSecretLease`，请求完成或失败后立即释放引用。实现不得把 bundle path、Cookie 名值对、token、富途 ID 或设备字段复制到 run manifest。

本地会话 bundle 必须满足：

- 位于仓库和可提交目录之外；
- 仅当前用户可读写，拒绝组/其他用户可读权限；
- 不接受命令行直接传值，也不采集整个环境快照；
- Cookie 必须具有允许的 domain/path、`Secure` 属性和可解析有效期；
- credential reference ID 由规范化引用元数据计算，不能反推出路径或秘密；
- 不支持 refresh token 或自动登录，过期后由用户重新导出并替换。

未来可以在单独 Change 中增加 macOS Keychain-backed provider，但本次不自动访问 Keychain。备选方案是把 Cookie 存进 run 目录或缓存记录；未采用，因为 run 需要被工具、测试和 Reviewer 读取，扩大了凭据暴露面。

### 4. Endpoint Manifest 是私有端点唯一运行时授权面

`FutuClientEndpointManifest` 对每个 endpoint 锁定：

- manifest ID/version、状态、验证日期和适用客户端版本；
- 精确 HTTPS host、port、method 和 path template；
- 允许的 query/body/header 字段、类型、必填性、枚举、长度与数值范围；
- 证券、时间、分页、到期日等参数如何从已验证研究请求生成；
- `GET`、`HEAD` 或 `READ_ONLY_QUERY_POST` 幂等语义；
- 响应 content type、最大字节数、Schema、证券/数据集/时间身份锚点；
- 数据集、来源层级、缓存策略、请求速率、重试和页数预算；
- 已知登录页、挑战页、权限页和漂移响应的识别规则；
- 脱敏 Bootstrap 样本 hash 与人工批准记录。

host 使用精确列表而非宽泛后缀；禁止非 HTTPS、用户信息 URL、非标准端口、fragment 和自动重定向。Cookie jar 只向 manifest 当前 endpoint 所需域发送匹配 Cookie，不能因服务器重定向或响应引用扩展域名。POST 必须逐端点证明请求仅包含查询字段，不能把 method 本身当作安全证据。

备选方案是把端点直接硬编码在 transport 中。未采用，因为端点、响应 Schema 与客户端版本需要作为可审计配置一起版本化和熔断；但 manifest 也不是动态配置后门，运行时只读取已批准版本。

### 5. Bootstrap 只导入用户提供样本，不负责抓包或端点探测

Bootstrap 输入是用户本人提供的本地请求/响应样本，例如从客户端可用调试能力导出的 HAR 或等价结构化记录。Importer 先在仓库外隔离原件，验证来源文件权限和大小，再完成：

1. 识别并拒绝账户、交易、认证、互动或副作用未知的请求；
2. 移除 Cookie、Authorization、token、账号、设备标识和无关 header/query/body 字段；
3. 将证券、时间、分页等实例值抽象为有界参数；
4. 从响应中仅选择目标数据字段与身份/时间锚点；
5. 生成 manifest candidate、脱敏样本及原件 hash；
6. 由人工逐端点确认 host、只读语义、数据用途和可提交内容后发布新版本。

Runtime 不加载 HAR、不观察客户端网络、不枚举接口、不用错误消息猜参数，也不自动提升 candidate。若用户无法提供足以验证端点的样本，清单记录 `UNSUPPORTED`，而不是由实现自行发现私有协议。

### 6. Transport 复用现有有界网络边界但单独处理会话

在 `product/mcp/live/` 增加富途专用 session transport，复用现有 transport 的以下模式：

- 来源准入与版本锁在网络调用前验证；
- 禁止重定向并使用系统信任链校验 TLS；
- 在流式读取过程中执行字节上限，不先完整下载再截断；
- 以 Capture Session 共享总请求、速率、分页、重试与截止时间预算；
- 未知异常统一为稳定错误码，不持久化异常正文或请求头；
- transport 一旦触发安全、身份或契约硬失败，本 session 不继续换端点猜测；
- 缓存 key 包含 provider、endpoint manifest、客户端版本、security ID、数据集与参数窗口。

富途 transport 与 Yahoo 等公开来源不同：它必须在单次发送边界取得 Secret Lease，并在事件记录前删除所有敏感 header。响应状态按登录/过期、权限、挑战、限频、漂移与服务失败分别分类；只有明确可重试的短暂服务错误允许有限重试，401/403、挑战、契约漂移和安全失败不自动重试。

### 7. 原始响应先隔离，验证后才进入缓存和 Evidence

每个 HTTP 响应先写入仓库外、权限受限的 Capture Session quarantine；事件只记录 endpoint ID、参数摘要、状态、字节数、时间和原始 bytes hash，不记录完整 URL query、请求 header 或异常正文。随后按以下顺序验证：

1. HTTP status 与 content type；
2. 登录/挑战/权限页面识别；
3. 最大大小、JSON/文档形状和响应 Schema；
4. 证券、市场、数据集、报告期/观察时间身份；
5. 禁止字段扫描：账号、设备、资产、订单、消息及未批准 PII；
6. 页码/游标连续性、重复和预算；
7. 数据集 Normalizer 的字段、单位、时间与来源语义。

任何身份或禁止字段失败都不生成 Evidence。若原件含敏感字段，只保留在本地 quarantine 供用户决定删除，评审材料仅记录 hash、大小和错误码；不把敏感内容复制到普通追加式缓存。通过全部检查的响应才进入标准缓存和 Capture Session manifest。

备选方案是先保存所有响应再由下游清洗。未采用，因为一次意外的账户响应会把敏感内容扩散到缓存、日志和 Agent 可读路径。

### 8. 数据集采用独立契约与递进实现顺序

统一 `FutuCaptureSession` 关联请求、manifest、raw hash、标准化对象和 Evidence IDs，但不创建“万能富途 JSON”。数据对象为：

- `FutuOptionSnapshot`：`option_static` 与 `option_dynamic` 分层，保留行情级别、最后有效时间和同批快照时间差；
- `FutuVendorFlowSnapshot`：保留富途原始分类、期间、币种、定义版本和 `VENDOR_CALCULATED_FLOW`；
- `FutuSecondaryOwnershipSnapshot`：分别表达机构两期和内部人资料，记录报告期、公开/更新时间、分页与二级来源；
- `FutuResearchCandidate` / `FutuResearchDocument`：候选元数据与实际可读正文分开，正文只在本地保存，进入研究包的是合规片段、结构化 Claim、hash 和定位。

feasibility 通过后，默认先实现资金流最小纵向切片，因为响应规模和分页通常小于完整期权面；若真实清单显示资金流不可得而动态期权可得，可以依据清单改选动态期权作为首个核心数据集，不改变 Spec。之后按动态期权、两期机构/内部人、研报顺序推进。静态期权链、单期机构汇总或研报候选可以保存，但不满足核心实质 Evidence 完成条件。

### 9. 能力状态由观测分类，不由登录成功推导

`FutuCapabilityInventory` 分开记录：

- `client`: 富途牛牛版本及观察方式，不含安装绝对路径；
- `session`: `MISSING`、`UNSAFE`、`EXPIRED`、`USABLE` 或 `UNKNOWN`，不含身份；
- `endpoint_manifest`: 当前批准版本及各 endpoint 健康状态；
- `dataset_matrix`: 七类目标数据集的 route/status/fields/last_success/reason；
- `constraints`: CSRF、签名、设备、挑战、行情权限、正文权限、限频与漂移；
- `completion_effect`: 是否仅发现、已采集、已过 Gate 或已形成研究输入。

能力探测只调用 feasibility endpoint 和本轮目标数据集已批准端点，不以扫描方式探测全部能力。一个数据集成功不提升其他数据集；Cookie 有效也不提升数据权限。

### 10. Manifest 与客户端版本漂移触发端点级熔断

每次采集核对客户端版本、manifest version、响应结构指纹和身份锚点。发生以下任一情况时，当前 endpoint 立即进入熔断：

- 当前客户端版本超出 manifest 允许范围；
- host/path/method 或必需 header 形状变化；
- 响应 content type、顶层类型、字段类型或枚举漂移；
- 证券、市场、数据集或时间锚点缺失/冲突；
- 登录、挑战、权限或账户响应替代数据响应；
- 连续短暂错误超过 manifest 的有限预算。

熔断仅影响对应 endpoint 与依赖数据集，不自动切换到未批准端点，也不影响其他公开来源。恢复必须重新进入 Bootstrap、生成新 candidate、完成人工批准和聚焦契约测试；不得直接编辑生产 manifest 绕过。

### 11. MCP 只查询冻结结果，采集与分析分阶段

真实采集由宿主入口显式触发，完成后先冻结并通过 PIT Gate。运行时 Agent 只获得数据集级 Evidence 查询权限；MCP 输入限定 `security_id`、`dataset`、`decision_cutoff` 和 `capture_session_id`。MCP 不加载 secret reference、不发网络请求、不读 quarantine、不执行 Bootstrap，也不暴露 endpoint、header、Cookie 或通用 HTTP 参数。

若研究需要新的到期日、报告期或研报正文，先由宿主产生新的 Capture Session，再显式纳入研究输入。多个 Agent 因此读取同一冻结快照，不会在推理期间造成时间、权限或响应漂移。

### 12. 富途数据保持供应商与二级来源语义

`source_id` 使用 `futu-client-session:<endpoint-id>:<capture-session-id>`，`source_type=SECONDARY_VENDOR` 或数据集明确的 vendor 类型。若响应显示 SEC、交易所或研报机构作为底层来源，只记录 `reported_original_source`；未直接读取原文时不能提升来源层级。

同一字段出现富途与 SEC/Yahoo/其他来源冲突时全部保留，由现有 Skill 解释差异，Normalizer 不投票、不覆盖、不生成投资判断。资金流固定为供应商计算口径；期权买卖方向默认不可得；机构两期必须口径可比；研报标题、摘要和转载不能转成完整正文。

### 13. 真实产物分为秘密、隔离、合格证据和可提交摘要四层

建议目录结构：

```text
<external_secret_root>/futu/
└── session-bundle.json                 # 0600，高敏，不属于 run

<run_dir>/futu/
├── capability-inventory.json
├── sessions/<capture_session_id>/
│   ├── capture-manifest.json
│   ├── quarantine/                     # 0700，原始响应/Bootstrap 原件
│   ├── accepted-raw/                   # 已通过禁止字段与身份检查
│   ├── normalized/
│   └── events.jsonl                    # 无 header/Cookie/完整 query
├── evidence/futu-evidence.json
└── reports/capability-report.md

<repo>/product/mcp/live/
├── futu-client-endpoint-manifest.json  # 仅脱敏、已批准定义
└── personal-research-approval.json     # 复用/扩展操作者批准记录
```

具体文件名可在实现时随既有模块布局调整，但四层权限和信息边界不能合并。可提交端点 manifest 不含真实 Cookie、账号、设备 ID、完整私有响应或受限研报正文；只保存必要路径模板、字段契约、脱敏样本 hash 和批准信息。

### 14. 完成证据按 feasibility、核心闭环和目标矩阵递进

验收分为：

1. **静态安全与合成契约**：secret 权限、泄密脱敏、manifest 偏离、重定向、禁止请求、过大响应、未来事实、悬空 Evidence。
2. **真实 feasibility**：当前会话的一个无副作用证券身份/公开行情请求，保存实际 manifest、Capture Session 和响应 hash。
3. **真实能力清单**：七类数据集逐项 route/status/fields/reason，不用未尝试冒充受限。
4. **核心纵向链路**：至少一个动态期权或资金流数据集完成 `CLIENT_SESSION_HTTP → Normalize → PIT → MCP Query`。
5. **目标矩阵**：期权、资金流、机构/内部人、研报分别有真实成功或准确限制；成功项才扩展到当前普通股持仓。
6. **研究消费**：至多一次现有专项 Skill 消费检查，报告必须增加具体研究信息并正确限定供应商语义。
7. **原 Change 映射**：只把证券、cutoff、Evidence closure 和实际研究内容均兼容的产物映射到 `expand-free-data-holding-research` 收尾材料。

若 feasibility 不通过，第 3–7 项不继续执行；若核心纵向链路缺失，则即使能力限制记录完整也不能申请本 Change 完成。完成本 Change 也不自动表示富途全部数据集、原多维研究 Change 或用户期权持仓能力完成。

## Risks / Trade-offs

- [Cookie 不是完整客户端认证，可能还需动态签名或设备状态] → feasibility 先行；只允许可安全复现的静态会话/CSRF 材料，遇到不可复现机制即停止。
- [私有端点可能违反服务条款或上游使用限制] → P0 必须保存当前条款/权限核对与操作者批准；发现明确禁止或收到上游拒绝时标记 `BLOCKED_BY_POLICY` 并熔断，不以技术可用替代许可。
- [Cookie 泄漏可能导致账号被冒用] → 仓库外 0600 secret、短生命周期 lease、日志/header 清除、异常正文脱敏、提交扫描；不自动读取客户端存储或刷新会话。
- [端点或响应随客户端版本变化] → manifest 锁客户端版本和响应 Schema/指纹；端点级熔断并要求重新 Bootstrap/人工批准。
- [查询型 POST 的副作用难以证明] → 默认不允许；只有请求字段、响应和重复调用语义均已核对的 endpoint 才标记 `READ_ONLY_QUERY_POST`，无法确认则拒绝。
- [研究端点意外返回账户或 PII] → 先进入 quarantine，禁止字段检查早于缓存/标准化；命中后不生成 Evidence，评审只保留脱敏错误和 hash。
- [未开户账号的数据权限有限] → 能力矩阵逐数据集记录；不购买、不开户、不绕过，核心数据全部受限时 Change 保持未完成。
- [富途资金流或机构数据被过度解释] → 固定 vendor/secondary 语义，与 SEC 等原始来源并列不覆盖，解释继续由现有专业 Skill 完成。
- [研报正文涉及版权和访问限制] → 只处理当前账号合法可读正文；全文留本地，研究包和 Git 仅保留必要片段、Claim、hash 和定位。
- [当前工作区有多个未归档 Change 和用户修改] → 本 Change 只修改自身规划与获批实现文件；应用阶段先建立文件归属清单，禁止全目录暂存或改写其他 Change 历史状态。

## Migration Plan

1. 用现有公开来源保持默认生产路径不变；新增 Futu profile 默认为关闭。
2. 加入 Schema、secret reference 验证、endpoint manifest importer/validator 和合成负向测试，不进行真实数据采集。
3. 用户在本人本机准备仓库外会话 bundle 与只读请求/响应样本；生成 candidate，经人工批准后只启用 feasibility endpoint。
4. 通过宿主入口执行一次真实 feasibility；若触发签名、设备、挑战或政策硬阻断，关闭 profile 并以限制报告结束，不继续数据集实现。
5. feasibility 通过后按能力清单选择资金流或动态期权作为第一个核心纵向切片，接入标准化、PIT 和冻结 MCP。
6. 核心切片通过后依次扩展其余目标数据集；每个 endpoint 单独 manifest、测试、预算和熔断状态。
7. 完成限定研究消费和证据映射后，再由人工决定是否批准 Change 完成；不自动归档或修改原 Change 状态。

回滚时禁用 Futu session profile、撤销或删除外部 secret reference，并熔断全部 Futu endpoint manifest。既有合格 Evidence 保留原 provenance/hash 供历史读取，但不能继续采集或证明当前会话仍有效；Yahoo、东方财富、SEC 等现有路径无需迁移。

## Open Questions

- 当前富途牛牛客户端版本、实际官方 host、Cookie 名称、CSRF header、只读 endpoint path 和响应 Schema 尚未知，必须由 P0 用户提供的本人客户端样本确定；规划和 Runtime 不猜测这些值。
- 当前未开户账号能取得哪些动态期权、资金流、两期机构/内部人和研报字段尚未知；这只影响能力矩阵和实现顺序，不改变安全边界。
- Cookie 是否可独立重放、是否存在允许静态复用的请求签名将在 feasibility 中判定；若必须破解动态签名或伪造设备，本路线按既定门槛停止。
- 研报正文 endpoint 是否返回全文、片段、临时 URL 或仅元数据尚未知；无论形态如何，只有当前账号合法读取且通过版权/PIT 检查的内容才能进入 `FutuResearchDocument`。
