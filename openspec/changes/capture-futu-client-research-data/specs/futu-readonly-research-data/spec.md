## Purpose

为现有美股普通股持仓研究提供一个受约束、可追溯、严格只读的富途客户端会话资料入口，在不依赖开户、OpenD/OpenAPI 或收费 API 的前提下，将用户本人客户端中合法可得的研究数据转换为现有 Agent Package 可消费的 point-in-time Evidence，并对私有端点、会话凭据、接口漂移和权限限制保持 fail closed。

## ADDED Requirements

### Requirement: 客户端会话路线必须先通过无副作用可行性门槛
系统 MUST 在实现或宣称任何研究数据集可用前，以用户显式授权的客户端会话材料，对一个已批准的公开行情或证券身份查询完成真实只读重放。可行性证明 MUST 核实请求目标、证券身份、响应契约、会话权限和无副作用边界；不得用客户端页面可见、合成响应或未实际发送的请求代替。

#### Scenario: Cookie 足以完成批准查询
- **WHEN** 用户提供的当前客户端会话能够调用已批准的证券身份查询，响应符合锁定契约且没有账户状态变化
- **THEN** 系统记录 `SESSION_REPLAY_FEASIBLE`、端点清单版本、脱敏请求定位、响应 hash 和核实结果，并允许继续实现目标数据集

#### Scenario: 请求依赖不可安全复现的客户端机制
- **WHEN** 查询还要求破解动态签名、伪造设备、绕过验证码或反自动化挑战才能成功
- **THEN** 系统返回对应的 `SIGNATURE_REQUIRED`、`DEVICE_BINDING_REQUIRED`、`CHALLENGE_REQUIRED` 或 `BLOCKED_BY_POLICY`，停止该路线且不得继续构建或宣称完整适配

### Requirement: 会话材料必须由用户显式授权并保持秘密
系统 MUST 只通过本地 secret reference 接收用户本人显式导出的 Cookie、CSRF token 或必要会话材料。系统 MUST NOT 自动读取、解密或复制富途客户端私有 Cookie 数据库、macOS Keychain、设备认证数据或登录凭据，也不得把秘密值放入命令参数、环境快照、日志、错误、Schema、Capture Session、原始响应、Evidence、评审材料或 Git。

#### Scenario: 用户提供有效 secret reference
- **WHEN** 用户以受支持的本地秘密载体提供当前会话且文件权限与内容格式满足要求
- **THEN** transport 仅在请求发送边界解析秘密，其他组件只能获得不可逆的 credential reference ID 和会话状态

#### Scenario: 会话材料缺失、过期或被撤销
- **WHEN** secret reference 不存在、权限过宽、Cookie 过期或服务器拒绝当前会话
- **THEN** 系统分别返回 `SESSION_MISSING`、`SESSION_SECRET_UNSAFE` 或 `SESSION_EXPIRED`，不自动登录、刷新凭据或回退到其他身份

#### Scenario: 响应或异常回显会话秘密
- **WHEN** HTTP 库、服务端响应或异常文本包含 Cookie、token 或可识别会话片段
- **THEN** 系统在任何持久化或展示前确定性拒绝或脱敏该内容，并记录不含秘密值的安全事件

### Requirement: 私有只读端点必须由版本化清单约束
系统 SHALL 使用版本化 `FutuClientEndpointManifest` 声明每个允许端点的官方 host、TLS 要求、method、path template、允许的 query/body/header 字段、响应 content type、响应 Schema、数据集、幂等语义、适用客户端版本和验证日期。运行时 MUST 拒绝清单外 host、重定向、method、path、字段和值域，不得接受任意 URL、任意请求头或任意请求体。

#### Scenario: 请求完全匹配批准端点
- **WHEN** 数据集请求的 host、method、path、字段和值域均匹配当前清单且客户端版本仍在允许范围
- **THEN** transport 可以在预算内发送请求，并把 manifest ID/version 写入 Capture Session

#### Scenario: 请求偏离端点清单
- **WHEN** 请求包含未知 host、跨域重定向、额外字段、账户标识路径、未批准 method 或超出值域的参数
- **THEN** transport 在网络调用前返回 `BLOCKED_BY_POLICY` 或 `CONTRACT_MISMATCH`，不得尝试自动修复或放宽清单

#### Scenario: 客户端或返回契约发生漂移
- **WHEN** 当前客户端版本不在允许范围，或响应字段、类型、枚举和身份锚点不再符合清单
- **THEN** 系统返回 `ENDPOINT_DRIFT`，冻结该端点及受影响数据集，直到新的脱敏样本经过人工核对并发布新清单版本

### Requirement: Bootstrap 端点发现与运行时采集必须隔离
系统 MUST 将 Bootstrap 与 Runtime 作为两个不同权限阶段。Bootstrap MAY 接受用户从本人客户端提供的脱敏只读请求/响应样本，用于核对并生成端点清单候选；Runtime MUST 只执行已批准清单，不得抓包、扫描端点、枚举路径、观察客户端私有存储、从错误信息猜测参数或自动修改清单。

#### Scenario: Bootstrap 样本包含完整只读契约
- **WHEN** 用户提供的样本能够证明官方 host、请求字段、证券身份、数据时点、响应字段和只读用途
- **THEN** 系统生成待人工批准的清单候选，删除 Cookie/token/账号/设备标识并保留脱敏样本 hash

#### Scenario: Bootstrap 样本包含敏感或禁止区域
- **WHEN** 样本涉及交易、订单、账户资产、消息、登录、认证、设备绑定或无法判断副作用的请求
- **THEN** 系统拒绝把该样本转为允许端点，并在脱敏后记录拒绝原因

#### Scenario: Runtime 遇到未知接口
- **WHEN** 已批准数据集需要调用当前清单不存在的接口
- **THEN** Runtime 返回 `UNSUPPORTED` 或 `ENDPOINT_DRIFT`，要求重新进入显式 Bootstrap，而不是现场探测

### Requirement: 所有客户端会话请求必须严格只读且无副作用
系统 MUST 仅允许 GET、HEAD，或经清单逐端点证明为幂等查询语义的 POST。系统 MUST 禁止账户、资产、订单、交易、入金、转账、消息、社区互动、登录、认证、订阅购买、设置修改及其他具有或无法排除副作用的调用；不得以“未开户”为由放宽禁止边界。

#### Scenario: 查询型 POST 已被批准
- **WHEN** 一个 POST 只提交证券、时间、分页或筛选字段，清单声明其幂等查询语义且响应不含账户状态变化
- **THEN** transport 可以按锁定请求 Schema 调用，并记录 `READ_ONLY_QUERY_POST`

#### Scenario: 请求可能修改状态
- **WHEN** endpoint、method、path、请求字段或返回语义涉及订单、收藏、关注、评论、订阅、账户设置或其他状态修改
- **THEN** 系统在发送前确定性拒绝，且该端点不得通过配置开关临时启用

#### Scenario: 服务器要求登录、挑战或购买
- **WHEN** 服务端返回登录页、验证码、设备确认、风险验证、开户、订阅或购买提示
- **THEN** 系统返回精确能力状态，不自动点击、登录、开户、购买、刷新或寻找绕过路径

### Requirement: 能力清单必须按端点和数据集记录真实状态
系统 SHALL 在采集前生成版本化 `FutuCapabilityInventory`，逐项记录运行平台、客户端版本、endpoint manifest 版本、匿名化会话状态、数据集、端点、权限、字段覆盖、最近成功时间和限制原因。目标数据集至少包括 `option_static`、`option_dynamic`、`capital_flow`、`institutional_two_period`、`insider`、`research_index` 和 `research_body`；状态 MUST 使用 `AVAILABLE`、`SESSION_MISSING`、`SESSION_EXPIRED`、`SESSION_SECRET_UNSAFE`、`CSRF_REQUIRED`、`SIGNATURE_REQUIRED`、`DEVICE_BINDING_REQUIRED`、`CHALLENGE_REQUIRED`、`ENTITLEMENT_REQUIRED`、`RATE_LIMITED`、`ENDPOINT_DRIFT`、`CONTRACT_MISMATCH`、`SOURCE_LIMITED`、`UNSUPPORTED` 或 `BLOCKED_BY_POLICY`。

#### Scenario: 部分数据集可用
- **WHEN** 当前会话可取得资金流但期权动态行情需要额外权限，研报只有列表
- **THEN** 清单分别记录 `capital_flow=AVAILABLE`、`option_dynamic=ENTITLEMENT_REQUIRED`、`research_index=AVAILABLE` 和 `research_body=SOURCE_LIMITED`，不得用一个成功状态覆盖整个平台

#### Scenario: Cookie 登录成功但数据权限不足
- **WHEN** 会话身份有效而目标端点返回当前账号不可访问的字段或行情级别
- **THEN** 系统记录 `ENTITLEMENT_REQUIRED` 及脱敏原始原因，不把登录成功等同于数据可用

### Requirement: 采集会话必须有界且原始响应必须隔离
每次实际采集 MUST 生成独立 `FutuCaptureSession`，包括 session ID、证券身份、请求数据集、开始/结束时间、endpoint manifest ID/version、客户端版本、匿名 credential reference ID、权限状态、请求预算、脱敏请求定位、原始产物清单、逐文件 hash 和 Evidence IDs。采集 MUST 限制证券数、到期日、分页、请求数、频率、并发、重试和总时长；不得因失败循环轮换端点或会话。

#### Scenario: 采集在预算内完成
- **WHEN** 所有响应身份和契约均正确且请求未超过清单与会话预算
- **THEN** 系统冻结原始响应、标准化结果和完整 manifest，供后续 Gate 使用

#### Scenario: 身份、分页或预算异常
- **WHEN** 响应证券不符、分页重复/断裂、返回数据集错误、请求限频或任一预算耗尽
- **THEN** 系统停止受影响数据集并返回精确状态，不合并不完整响应或继续猜测下一请求

#### Scenario: 原始响应含账户或身份字段
- **WHEN** 研究端点意外返回账号、设备、资产、消息或其他不在响应白名单中的字段
- **THEN** 系统将响应隔离为安全失败，不生成 Evidence，并确保可提交产物不包含该字段或其值

### Requirement: 期权静态合约和动态行情必须分开建模
期权数据 MUST 区分静态合约信息与动态快照。静态链至少保留标的、合约代码、看涨/看跌、到期日、行权价和合约乘数；动态快照按实际权限保留 bid/ask、last、成交量、未平仓量、隐含波动率、Greeks、行情级别和最后有效时间。缺少动态字段时不得宣称期权市场结构研究已经完成。

#### Scenario: 只有静态期权链
- **WHEN** 客户端会话只返回合约列表而没有可靠动态报价
- **THEN** 系统输出 `STATIC_CHAIN_ONLY` 子状态及缺失字段，不生成价差、活跃度、波动结构或资金方向所需 Evidence

#### Scenario: 动态快照可核实
- **WHEN** 一个标的的多个到期日和行权价在接近同一时点具有合格动态字段
- **THEN** 系统生成可被 `options-market-structure` 消费的冻结快照，并明确单次快照不能证明历史变化或买卖方向

### Requirement: 资金流必须保持供应商计算语义
富途资金流结果 MUST 标记为 `VENDOR_CALCULATED_FLOW`，保存原始字段定义、周期、币种、适用市场、最后有效时间和 endpoint manifest 版本。系统 MUST 将成交量、持仓量、卖空统计和富途分类资金流分开，不得把大单、主力或净流入表述为已验证的机构买卖，也不得从单一快照推断未来方向。

#### Scenario: 取得资金流序列
- **WHEN** 端点返回整体及特大/大/中/小单等净流入字段
- **THEN** Evidence 保留原始分类、正负号、单位、周期和富途口径说明，不自动转成机构行为结论

#### Scenario: 字段定义、时间或单位缺失
- **WHEN** 返回只有图形序列、模糊标签或无法核实的数值，且缺少字段定义、期间、单位或有效时间
- **THEN** 系统记录 `CONTRACT_MISMATCH` 或 `SOURCE_LIMITED`，不得把视觉趋势、猜测单位或获取时间转换为事实

### Requirement: 机构、内部人与研报必须保持来源分级
富途机构或内部人数据 MUST 作为 `SECONDARY_VENDOR` 保存显示的数据源、持有期、公开/更新时间、分页完整性和披露滞后；存在 SEC 原始披露时不得替代或覆盖 SEC Evidence。研报自动发现 MUST 保存标题、作者/机构、发布日期、页面或文档定位、访问状态和正文 hash；只有当前账号合法取得并实际读取到的正文通过时间与内容检查后，才可生成研究正文 Evidence。

#### Scenario: 两期机构数据可比
- **WHEN** 同一机构、证券和口径存在两个可比报告期且时间及分页完整
- **THEN** 系统保留两期原值、变化和来源限制，并允许与 SEC 原始披露并列而不静默覆盖

#### Scenario: 机构资料只有单期或汇总
- **WHEN** 客户端端点只返回单期持仓、排名或供应商汇总
- **THEN** 系统不得声称机构增减持趋势，并明确缺少第二期、原始披露或可比口径

#### Scenario: 研报只有标题、摘要或受限正文
- **WHEN** 端点只返回列表、评级摘要、转载片段，或正文需要额外权限
- **THEN** 系统仅生成 `FutuResearchCandidate` 和具体访问缺口，不生成 `FutuResearchDocument` 或声称完成研报读取/对比

### Requirement: 标准 Evidence 必须满足 point-in-time 和来源闭合
所有可消费事实 MUST 包含 canonical `evidence_id`、`source_id`、`source_type`、`source_locator`、`security_id`、`as_of`、`retrieved_at`、raw response hash、capture session ID、endpoint manifest ID/version、采集方式和数据提供者语义。`as_of`、发布日期或最后有效时间缺失时，系统 MUST 限制用途或拒绝生成时效性事实。所有结果 MUST 在进入研究 Agent 上下文前通过现有 PIT Gate。

#### Scenario: 只有获取时间而无事实时点
- **WHEN** 期权、资金流、持仓或研报字段没有可核实的观察时间、报告期、发布日期或最后有效时间
- **THEN** 系统不得以 `retrieved_at` 冒充 `as_of`，并排除该时效性事实或明确限制用途

#### Scenario: Evidence 通过截止时间检查
- **WHEN** Evidence 身份、来源和时间完整，公开/观察时间不晚于 `decision_cutoff` 且满足现有时效规则
- **THEN** PIT Gate 可以允许其进入对应专业研究输入，并保留端点及 Capture Session 血缘

#### Scenario: 当前快照晚于历史研究截止点
- **WHEN** 新取得的富途快照晚于目标 `expand-free-data-holding-research` canonical 包的 decision cutoff
- **THEN** 系统只能形成明确当前时点的新产物，不得静默拼入历史研究包或回填成当时已知事实

### Requirement: MCP 和 Agent 只能查询冻结后的只读结果
系统 SHALL 通过数据集级只读 MCP Tool 暴露能力清单、冻结快照和 Evidence 查询。Tool 输入 MUST 限定证券、数据集、截止时间和 Capture Session；输出 MUST 使用版本化 Schema。运行时 Agent MUST NOT 获得 Cookie、secret reference、通用 HTTP client、任意 URL、Bootstrap 权限或客户端控制能力；采集层不得生成 Thesis、交易动作、confidence 或投资结论。

#### Scenario: 专业 Skill 消费合格 Evidence
- **WHEN** 合格期权、资金流、所有权或研报 Evidence 已冻结并通过 Gate
- **THEN** 对应现有 Skill 可以引用 canonical Evidence ID，且输出继续受原专业报告 Schema、语义边界和 Evidence Closure 约束

#### Scenario: Agent 请求越权网络操作
- **WHEN** Agent 请求发送新请求、修改端点、读取 secret reference、访问未冻结响应或查询账户/交易资料
- **THEN** MCP 在任何网络或秘密访问前确定性拒绝并记录脱敏安全错误

### Requirement: 完成判定必须证明真实客户端会话纵向链路
本 Change 的实现完成 MUST 同时具备：真实无副作用可行性证明；确定性契约和负向安全测试；当前本机真实 `FutuCapabilityInventory`；一个美股普通股至少一个核心数据集完成 `CLIENT_SESSION_HTTP → Normalize → PIT Gate → MCP Query`；每个其余目标数据集均有真实成功证据或准确限制状态；以及至多一次不产生投资动作的现有专业 Skill 消费检查。若没有任何核心数据集形成实质 Evidence，或只有合成数据、静态期权链、候选研报或全部 `SOURCE_LIMITED`，Change MUST NOT 申请完成。

#### Scenario: 核心数据集形成有效研究输入
- **WHEN** 一个真实标的的动态期权或富途资金流完成全部链路，并被现有 Skill 正确引用和限定解释
- **THEN** 该数据集可以标记 `RESEARCH_INPUT_VALIDATED`，其他数据集仍按各自证据独立判定

#### Scenario: Cookie 重放可行但核心数据受限
- **WHEN** 证券身份查询成功，但期权、资金流、机构和研报均因权限或契约限制无法形成实质 Evidence
- **THEN** 系统输出真实限制报告和最小外部前置条件，但 Change 保持未完成

#### Scenario: 映射回原多维研究 Change
- **WHEN** 新产物满足 `expand-free-data-holding-research` 的证券绑定、PIT、Evidence closure、实际结构解释和推断边界
- **THEN** 收尾材料可以建立显式证据映射；否则保留延期缺口，不因本 Change 存在或端点可调用而宣称原能力已补齐

### Requirement: 本地产物必须保护隐私、版权与可撤销性
真实会话、Bootstrap 样本、原始响应和研报正文 MUST 默认写入被 Git 忽略、权限受限且 run-scoped 的本地目录。可提交摘要 MUST 移除 Cookie、token、富途 ID、账号、设备标识、本机路径、端口、账户字段和未授权全文。系统 MUST 支持删除或撤销 secret reference 后继续读取既有脱敏 Evidence，但不得继续发起新请求；研报正文的保存与展示 MUST 限于用户当前合法可读范围。

#### Scenario: 准备提交或评审
- **WHEN** 开发者生成可提交差异或评审材料
- **THEN** 自动检查确认其中不含会话秘密、身份信息、客户端私有路径、账户数据或受限制研报全文，失败时阻止相关提交或评审发布

#### Scenario: 用户撤销客户端会话材料
- **WHEN** 用户删除或撤销 secret reference
- **THEN** 后续采集返回 `SESSION_MISSING`，既有合格 Evidence 保留原 provenance 和 hash 但不能被当作当前会话仍有效的证明
