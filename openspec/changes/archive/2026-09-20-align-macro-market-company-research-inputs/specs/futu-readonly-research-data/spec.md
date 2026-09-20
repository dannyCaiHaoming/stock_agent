## ADDED Requirements

### Requirement: 三源补充能力必须进入当前 Provider 拓扑
当前持仓研究的权威 provider 拓扑 MUST 引用并锁定 SEC + Yahoo + Moomoo Singapore 的来源计划和数据集能力矩阵，区分基础披露/行情层与研究补充层，并将实际 provider/dataset 状态传递到运行 coverage 和缺口。Moomoo Singapore MUST 显示为通过用户管理的 loopback OpenD 提供的 quote-only 补充层；该视图不得暴露认证材料、客户端 Cookie、账户、订单、持仓、资金或交易能力。历史 `live-us-equity/4.0.0` 未列出 Moomoo MUST 被解释为该 profile 已退役且内容冻结，而不是当前系统没有 Moomoo 补充能力。

#### Scenario: 当前拓扑被查询
- **WHEN** 使用者或运行准备器读取当前 provider 视图
- **THEN** 能解析 SEC、Yahoo、Moomoo SG 的职责层、数据集状态、区域、限制及权威来源文件引用，同时看到 Moomoo 的 OpenD quote-only 边界

#### Scenario: Moomoo 暂时不可达
- **WHEN** 当前 OpenD 不可达但 SEC/Yahoo 的合格输入可用
- **THEN** 当前拓扑和运行 coverage 保留 Moomoo 准确失败状态，其他来源继续工作，不回退到客户端 Cookie 或私有接口

#### Scenario: 查阅退役 live profile
- **WHEN** 工具或维护者直接发现 `live-us-equity/4.0.0`
- **THEN** profile discovery 明确返回 RETIRED/COMPATIBILITY_ONLY，并引导到当前研究输入拓扑，不要求修改历史 profile 的 provider 列表

### Requirement: 新来源必须与既有三源补充包保持明确边界
三域新增的政策、新闻、IR 或公开研究来源 SHALL 通过获准的独立来源包进入共同 Evidence Gate，并保留真实 provider 和来源政策。既有 SEC/Yahoo/Moomoo SG 补充包 MUST 保持三源身份与原有安全边界，不能把外部正文伪装为三源资料，也不能因候选 Skill 适配而扩大 OpenD 权限。

#### Scenario: 公司 IR 正文补充 SEC 披露
- **WHEN** 公开 IR 文档被获准采集且通过时间和来源验证
- **THEN** 它以自身来源进入 Gate，与 SEC 披露保留关系和差异，不重标为 SEC 或 Moomoo Evidence
