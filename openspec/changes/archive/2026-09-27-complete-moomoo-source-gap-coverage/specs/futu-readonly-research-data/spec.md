## ADDED Requirements

### Requirement: OpenD 研究补充的环境权限与来源状态必须可区分
系统 MUST 在已批准的本机只读 Quote 范围内验证 OpenD 研究补充的实际可用性，并区分 SDK 不可加载、SDK 日志路径权限拒绝、loopback 连接失败、OpenD 未就绪、行情权限不足、接口返回空值和正常采集。授权范围仅为 `127.0.0.1:11111` 的既有 Quote allowlist、SDK 为初始化所必需的最小日志目录写入、公开新闻搜索的 HTTPS 读取及仓库外临时验收产物；不得把本需求中的用户授权视为 macOS 或 Codex 沙箱权限已经生效。系统 MUST NOT 因权限失败放宽至用户主目录通配写入、远程 OpenD、Trade Context、账户、Cookie 或私有客户端接口。错误输出 MUST 脱敏，且环境阻断 MUST NOT 冒充来源无数据或 Agent 已消费。

#### Scenario: SDK 日志目录受当前执行环境限制
- **WHEN** OpenD 正在本机监听，但 SDK 在初始化阶段因其日志目录写入被拒绝而未发出 Quote 请求
- **THEN** 来源检查报告明确的环境权限阻断、受限路径类别和所需最小授权，不将其记录为 Moomoo 无宏观数据或成功调用；未实际取得的响应不进入 Gate

#### Scenario: 本机 Quote 已就绪
- **WHEN** 使用当前锁定 SDK/OpenD 版本、所需本机权限真实生效，且既有 Quote allowlist 中的宏观历史、经济日历、FedWatch 或 Dot Plot 请求成功
- **THEN** 本批分别记录来源、采集时间、数据集与覆盖，按现有 PIT/Gate 契约交付，不因为接口在官方文档中存在便推定全部系列或下游研究已完成

#### Scenario: Quote 权限或数据不可得
- **WHEN** OpenD 能连接但某数据集被拒绝、返回空值或超出已批准预算
- **THEN** 只降低该数据集并保留准确原因；BLS、Treasury、Federal Reserve、SEC 和 Yahoo 的现有主流程不被阻断，也不改用 Trade/账户接口
