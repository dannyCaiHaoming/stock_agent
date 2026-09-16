## Why

当前普通股多维研究仍缺少可稳定取得的动态期权结构、供应商资金流、两期机构持仓及部分研报正文。用户当前只有未开户的富途牛牛账号，暂不采用 OpenD/OpenAPI，也不希望购买或依赖收费 API；但本人已登录客户端中可能存在合法可见的研究资料，因此需要建立一个复用用户显式授权客户端会话、严格限定为只读研究请求且能够随接口漂移安全失效的数据采集能力。

## What Changes

- 新增富途客户端会话只读资料采集能力。首版不集成 OpenD/OpenAPI，不要求开户，也不以 UI/OCR 作为主数据通道；通过用户本人显式提供的客户端会话材料，重放已批准的只读研究请求。官方 API 仅作为未来可选路线，不属于本 Change 的实现或完成条件。
- 将端点发现与运行时采集分开。Bootstrap 阶段只接受用户本人客户端产生的脱敏请求样本，并固化版本化 `FutuClientEndpointManifest`；运行时只能调用清单中已批准的富途官方 host、method、path、请求字段和响应字段，不得动态发现、猜测或接受任意 URL/请求体。
- Cookie、CSRF token 及其他会话材料统一视为高敏凭据。首版只通过本地 secret reference 注入用户显式导出的会话材料，不自动读取、解密或复制客户端私有 Cookie 数据库、Keychain 或设备认证数据；凭据值不得进入命令参数、日志、Schema、原始快照、Evidence、评审材料或 Git。
- 建立无副作用可行性门槛：在扩展数据集实现前，必须先以一个批准的公开行情或证券身份查询证明 Cookie 会话能够完成只读请求、响应身份可核实且不会触发账户变更。若还需要不可复现动态签名、设备绑定、验证码或反自动化绕过，则停止该路线并记录准确限制，不继续构建虚假的完整适配。
- 首版只面向美股普通股研究资料，按 `expand-free-data-holding-research` 的真实缺口排序：动态期权链与快照、富途口径资金流、两期机构持仓与内部人资料、研报发现及当前账号合法可读的正文。先以一个标的形成纵向闭环，再扩展至当前普通股持仓。
- 对每个数据集和端点记录实际能力状态，包括 `AVAILABLE`、`SESSION_MISSING`、`SESSION_EXPIRED`、`CSRF_REQUIRED`、`SIGNATURE_REQUIRED`、`DEVICE_BINDING_REQUIRED`、`CHALLENGE_REQUIRED`、`ENTITLEMENT_REQUIRED`、`RATE_LIMITED`、`ENDPOINT_DRIFT`、`CONTRACT_MISMATCH`、`SOURCE_LIMITED`、`UNSUPPORTED` 或 `BLOCKED_BY_POLICY`；不得因客户端页面存在该功能就宣称程序可用。
- 建立只读 Capture Session、原始响应隔离区、标准 Evidence 和完整来源血缘。所有可消费事实保留 `source_id`、`as_of`、`retrieved_at`、客户端版本、端点清单版本、采集方式、脱敏请求定位、原始响应 hash 和权限状态。
- 将合格 Evidence 接入现有 PIT Gate 和只读 MCP Tool，供 `options-market-structure`、`ownership-disclosure`、`research-report-analysis` 及现有市场研究能力消费；运行时 Agent 只能查询已经冻结并通过 Gate 的数据，不得持有 Cookie、发起任意 HTTP 请求或操控富途客户端。
- 明确数据语义：富途资金流属于 `VENDOR_CALCULATED_FLOW`，不等于已验证的真实资金方向；期权静态合约与动态报价分开；富途机构数据属于二级资料，不替代 SEC 原始披露；只有实际取得并核实正文的研报才可标记为已读取。
- 对会话过期、接口漂移、返回身份错误、行情权限、限频、挑战页面和字段缺失全部 fail closed。禁止自动登录、盗取或刷新凭据、伪造设备、绕过验证码/付费/风控、解密 TLS、调用账户/交易/订单/消息接口或模拟下单。
- 验收覆盖无副作用可行性证明、确定性契约与负向安全测试、一个真实客户端会话能力清单、至少一个核心数据集的真实 Capture → Normalize → PIT Gate → MCP Query，以及至多一次不产生投资动作的现有专项研究消费检查。不重跑完整 Council、Regression、Replay、Calibration、Ablation 或 Promotion Gate。
- 本 Change 不自动改写或重新打开 `expand-free-data-holding-research` 已关闭的受限分支任务。只有新产物满足其来源、PIT、Evidence、实际结构解释和内容标准后，才可在原 Change 的收尾材料中建立显式证据映射；接口受限或 Change 存在本身均不代表缺失能力已经补齐。

## Capabilities

### New Capabilities

- `futu-readonly-research-data`: 规定基于用户显式授权客户端会话的富途只读研究数据端点发现、白名单重放、凭据隔离、能力判定、标准化、来源追溯、PIT 接入、MCP 暴露及有限研究消费验收。

### Modified Capabilities

无。现有多维研究、PIT Evidence、专业 Skills 和 Agent 职责保持不变；本 Change 仅增加可被它们消费的数据能力。

## Impact

- 预计扩展 `product/mcp/live/` 的来源路由、受限 HTTP transport、采集、缓存和标准化，并增加富途客户端会话专用只读适配；复用现有 `LiveFact`、Evidence Gate、运行目录和宿主产品入口。
- 预计新增 `FutuClientEndpointManifest`、会话能力清单、Capture Session、数据集 Schema、只读 MCP 契约、聚焦测试、中文本地操作说明及脱敏验收记录；不新增编排后端或投资 Agent。
- 不增加官方 `futu-api` SDK 依赖。会话导出与更新由用户在本人本机显式完成；实现只接收本地 secret reference，不提供客户端私有存储提取或登录自动化能力。
- 原始响应、账号或设备相关字段、会话材料和可能受版权约束的研报正文只允许保存在被忽略且权限受限的 run-scoped 本地目录；Git 仅保存脱敏契约、端点模板、代码、合成测试及不含本机身份的验收摘要。
- 私有端点可能随客户端版本变化或受到服务条款、账号权限及反自动化机制限制，因此该来源默认实验性、显式启用且可按端点或数据集立即熔断；不得替换或覆盖现有 Yahoo、SEC、宏观和公开研报来源。
- 不修改 Sandbox、模型路由、Risk、券商账户或订单能力；不接入交易接口，不保存或提交用户凭据。
