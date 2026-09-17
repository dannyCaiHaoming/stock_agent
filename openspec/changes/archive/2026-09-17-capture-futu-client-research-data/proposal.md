## Why

已归档的 `expand-free-data-holding-research` 仍有期权、资金流、两期机构持仓及研报正文缺口。本 Change 按用户最新决定采用 **SEC + Yahoo + Moomoo Singapore** 组合，通过原始披露、市场数据和供应商研究资料互补，避免把全部研究能力绑定到富途牛牛客户端 Cookie 重放的可行性。

## What Changes

- 新增可复用的个股背景资料包 `CompanyBackgroundSnapshot`：公司档案与证券身份、业务/产品/地区分部、管理层与治理、客户/供应商依赖、财务历史与资本配置、业绩与指引、分析师预期、公司事件及可得空头持仓。它是三源 Evidence 的结构化索引与中文背景说明，不是新的投资 Agent 或评分系统。
- 依据参考项目源码和本仓库采集/Schema 的差异补齐资料层：已有研究方法与正文片段继续复用；对分部维度、治理文件、营运资本/R&D、预期版本与结构化档案增加获取和验证任务，不能仅增加提示词即宣称数据已补齐。
- 个股背景按基础必备与可得增强分层；三源不提供的电话会全文、历史一致预期、借券费率等记录具体受限原因，不新增第四来源、不猜测供应链、不以缺失值补零。背景包验收加入完成条件，不抵扣原期权/资金流/两期机构核心增量。
- 研究范围仍为美股普通股；Singapore 指 Moomoo 服务区域，不表示扩展新加坡股票或交易能力。
- SEC 为财报、公司披露、13F 机构申报及内部人披露的原始来源；Yahoo 为价格、OHLCV、公司行动、基准及实际可得期权快照的市场数据来源；Moomoo Singapore 为供应商资金流、机构资料展示、期权补充和研报候选/可读正文来源。
- 采用按数据集固定的来源职责与显式回退，不把三家视为可任意替换的同类接口。原始披露、供应商统计、行情与研报观点分别保留语义；跨源冲突并列保存。
- SEC 公共 EDGAR 数据接口可以使用；Moomoo 采用官方 `Moomoo OpenAPI + OpenD`，不再保留“不使用 OpenD/OpenAPI”的旧约束。仍不采购收费 API、不要求开户、不接入交易能力。
- Moomoo SG 的账号登录、API 问卷与协议由用户在本机 OpenD 完成。Runtime 只通过 loopback 连接已登录 OpenD，使用官方 `moomoo-api` SDK 的 Quote API；不接收、读取或存储 Moomoo 密码、Cookie、Token、交易解锁密码或客户端私有数据。
- Cookie 重放、网页私有端点、Charles 抓包与客户端协议模拟从本 Change 的 Moomoo 主路线移除。官方 API 缺少的数据记录为能力缺口，不自动回退到抓包或会话重放。
- Moomoo 适配器使用版本化 Quote API allowlist，锁定方法、参数、证券范围、返回字段、频率与分页预算；禁止构造 Trade Context、调用交易/账户/订单接口或连接非 loopback OpenD。
- 统一能力矩阵、OpenD/SDK 版本、采集批次、原始资料隔离、标准化 Evidence、PIT Gate 与冻结 MCP。每条事实保留来源、证券、事实时点、公开时间、获取时间和原始 hash。
- 分来源验证：Moomoo SG 受限不阻止 SEC/Yahoo 形成有效研究输入；但 SEC/Yahoo 成功也不能标记 Moomoo SG 或原缺口已完成。
- 验收要求 SEC 与 Yahoo 真实接入、至少一个原延期核心缺口形成实际增量，以及 Moomoo SG 至少一个研究数据集完成真实纵向链路；只有受限报告不足以宣称整个三源组合完成。
- 用户已要求使用此前确认的截图持仓验证真实系统消费链路；因此 Change 收尾还必须证明已冻结三源资料能够由 ALB、MRVL、WOLF 三个独立 Company Analyst 调用形成可验证报告。父调度线程必须等待全部已派发子任务取得真实终态，不能把启动事件、等待调用返回或自报计数当作完成。
- 不修改已归档 Change 的任务勾选与历史产物；新证据按证券、cutoff 和缺口建立显式映射。
- 正式接入以既有宿主持仓入口为准：用户提供确认 Handoff 和既有来源配置后，入口完成有界采集、逐证券补充包挂接、冻结、研究及中文/JSON 输出，不要求用户手工准备补充包或运行临时拼包脚本。多包写入、索引、重建校验、查询与引用必须一起闭合。
- Moomoo 受限时继续输出合格 SEC/Yahoo 研究与来源缺口；这是产品部分可用，不代表三源 Change 验收通过。至少一只实际持仓的 Moomoo 研究数据消费仍是归档条件。
- 旧运行证据不足以定位故障时，允许在现有入口补充针对具体假设的最小诊断；先确定观测信号和预算再做有界验证，不扩建通用监控或调度平台。

## Capabilities

### New Capabilities

- `futu-readonly-research-data`: 保留既有 capability 路径以维持延期责任引用，内容修订为 SEC、Yahoo 与 Moomoo Singapore 组合的只读研究资料获取、来源分工、OpenD 隔离、PIT 与研究消费验收。旧名称不代表使用富途牛牛客户端或其 Cookie。

### Modified Capabilities

无。现有专业 Skill、Evidence Gate 与投资 Agent 的职责不变；组合数据以补充输入接入。

## Impact

- 预计复用 `product/mcp/live/` SEC/Yahoo transport、期权、缓存与标准化模块，增加基于官方 `moomoo-api` SDK、仅连接本机 OpenD 的 Moomoo SG 只读适配和组合研究补充快照。
- 优先沿用现有研究 sidecar 与 Evidence 接缝；实施前核对既有 provider 枚举，不能直接向锁定四来源的基础快照写入第五来源。
- 增加来源能力矩阵、Quote API allowlist、OpenD/SDK 版本与权限记录、来源选择记录、数据契约、聚焦测试和中文操作说明，不建设新编排后端或投资 Agent。
- 补齐确认持仓到逐证券三源补充包、Gate、冻结 MCP 和真实报告的接入；先检查输入是否含本 Change 的新增数据，再定位研究消费失败。父线程 Stop 屏障仅为已有防提前退出措施，不作为根因已解决或需求完成的证据。
- 已完成的来源无关实现继续保留；Cookie/Charles 专用实现不再作为验收证据，相关任务按 OpenD 路线重新验证。既有宏观/公开研报等不属于本 Change 的来源不被删除；本 Change 新增数据路由限定为三源组合。

## 当前完成证据（2026-09-17 更新）

AAPL 三源样本与有限专项消费仍只作为历史限定证据。新的 `capture-futu-client-research-data-20260917-v5` 已从同一确认 Handoff 自动生成 ALB、MRVL、WOLF 三份独立补充包；多包保存、preparation 逐股索引、source bundle 重建、Gate 准入、补充 MCP 与通用 Evidence 查询均已通过。每只持仓均有 SEC/Yahoo/Moomoo SG Evidence 和 5 条供应商资金流；治理与关系资料保持显式受限，不用空值伪造覆盖。

用户明确授权数据外发后，正式宿主入口先完成 ALB 单股验证，随后完成 ALB/MRVL/WOLF 三股并发批次。最终 3/3 中文/JSON 报告通过 Schema、PIT、Evidence Closure 与持久化校验，`parallel_overlap=true`，每份报告都实际引用 SEC、Yahoo 与 Moomoo SG `vendor_money_flow`；MRVL/WOLF 还引用新增背景类别。ETF 和 SOXL 期权继续显式保留能力缺口。实现与产品验收边界已闭合；只剩最新差异的独立只读复核和人工完成批准，未获该批准前不归档、不提交、不推送。
