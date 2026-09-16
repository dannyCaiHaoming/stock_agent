# 免费公开资料能力表

本表用于记录 `expand-free-data-holding-research` 各阶段的真实来源语义与有界请求预算。它不是供应商长期可用性承诺；每个来源在对应阶段实测后更新状态。所有进入研究上下文的事实都必须带 `source_id`、`as_of`、`retrieved_at`，并在 Agent 读取前通过 PIT Gate。

## 请求预算约定

- “正常请求”包括必要的身份查询、单次列表/分页、明细和正文获取，不计作失败重试。
- 每个请求至多进行一次有原因的暂时故障重试；权限拒绝、登录/付费限制不重试。
- 每项能力默认最多两个供应方，禁止无界轮换来源。
- 缓存命中保留原始 `retrieved_at`，不得伪装为新采集。
- 研报每证券至多 3 次查询、检查 10 个候选、尝试 5 份正文；取得足够材料后提前停止。

## 渐进来源矩阵

| 能力/字段 | 首选来源 | 备选来源 | 费用/认证 | 时间语义与延迟 | 历史/缓存 | 本阶段预算 | 当前状态与缺口影响 |
|---|---|---|---|---|---|---|---|
| 美股身份/股票池 | NASDAQ Screener 官方接口 | SEC ticker/CIK 映射 | 免费、通常无密钥 | 响应时点；不是上市状态的完整历史 | 本地冻结响应 | 身份列表 1 次；必要明细 1 次 | 已有代码与离线契约测试；网络可用性须按批次记录 |
| 日线 OHLCV、复权、分红拆股 | Yahoo Finance（现有 yfinance 路由） | AkShare 暴露的美股日线 | 免费、无项目凭证；非正式 SLA | 日线、可能延迟；未完成交易日必须排除 | 约 252 交易日起步；按冻结批次缓存 | 每证券/基准正常采集 1 次；暂时故障重试 1 次；切换 1 次 | `IMPLEMENTED`：已保留 OHLCV、调整收盘、分红和拆股，完成 PIT、断点、固定计算和图表同源测试；真实 LLM 批次待 P1 验收 |
| SEC 公司披露、财务事实、公司事件 | SEC submissions/companyfacts/filing 文档 | 发行人 IR 公开页面（后续最小接缝） | 免费；SEC 需合规 User-Agent | `accepted`、报告期与获取时间分别保留 | SEC 历史覆盖；冻结原始响应 | 身份、submissions、companyfacts 各 1；必要 filing 文档 2；暂时故障各 1 次 | `IMPLEMENTED`：现金流、资本开支、稀释、债务到期标签及业绩附件可进入 Gate；companyfacts 不含 XBRL 分部 dimension，明确保留分部结构化数值缺口 |
| 自动研报发现与正文 | OpenAlex Works 搜索 + Content API 的公开 GROBID XML 正文 | 暂无默认第二来源 | 搜索可匿名；Content API 需要外置 `OPENALEX_API_KEY`；不绕过登录/付费 | 发布日、获取时间与预测目标期间分开；未来发布日期排除 | 搜索结果为 `LEAD_ONLY`；正文按 body hash 冻结并保留章节定位 | 每证券 3 查询/10 候选/5 正文 | `IMPLEMENTED_PENDING_LIVE_VALIDATION`：准备 invocation 已绑定只读搜索/正文工具，正式研究只接收 `BODY_VERIFIED`；配置缺失为 `BLOCKED_CONFIGURATION`，来源失败才是 `SOURCE_LIMITED`，真实批次待 P2R 验收 |
| 行业同行资料 | NASDAQ 完整股票池选择 + SEC/行情有限采集 | 公开行业材料 | 免费公开资料 | 各公司期间、币种、会计口径分别保留 | 候选池、选择、采集快照和 Gate 分层冻结 | 每公司最多 3 个候选；只采集实际选择的去重同行 | `IMPLEMENTED_PENDING_LIVE_VALIDATION`：LLM 选择未核实候选，现有只读采集器核实身份并重新 Gate 后才可比较；不会自动排名，真实同行比较待 P3 验收 |
| 官方宏观：利率、通胀、经济活动 | BLS Public Data API v1 + U.S. Treasury Daily Rates | 无默认非官方替代 | 免费且无需密钥；BLS v1 每日 25 次、每次最多 25 序列/10 年 | 观察期与获取时间分开；响应缺精确发布时间时以 retrieved_at 作为保守 published_at | 不宣称拥有 historical vintage；不能还原时拒绝历史断言 | BLS 两序列合并 1 请求；Treasury 1 请求；来源间失败隔离 | `IMPLEMENTED`：CPI、失业率、10Y 收益率标准化、PIT 与 Gate 合并已测试；实际网络与 LLM 解释待 P4 批次 |
| 机构持仓/内部人披露 | SEC Forms 3/4/5；未来 SEC 13F | 无默认商业源 | 免费；SEC 需合规 User-Agent | 交易日、accepted 公开时点与获取时间分别保留，天然滞后 | 最新一份内部人原始 XML；保留 submissions 展示 URL 与原始文档 URL；不作拆股回溯调整 | 每发行人最新 1 份 Form 3/4/5；无暂时故障循环 | `IMPLEMENTED_PARTIAL`：已修复 SEC `xsl.../` 展示路径、原始 XML 解析及 Gate 来源/时效映射；ALB、MRVL、WOLF 最新 Form 4 已真实完成 3/3 获取、解析和 Gate 准入。ALB 已完成一次 GPT-5.6 Terra `SOURCE_LIMITED` 研究样本，正确保留交易类型、滞后和不可推断边界。13F 申报主体发现、两期机构比较及完整历史序列仍未实现，不能声称机构资金流或完整 `RESEARCH_VALIDATED` |
| 期权链快照/资金代理 | Yahoo Finance 期权链（yfinance） | 无默认第二来源 | 免费、无项目凭证；非正式 SLA | 每份事实记录获取时点、到期日与 last trade；非交易所快照时间 | 不承诺历史持仓量、IV 历史或成交方向 | 每证券最近 1 个到期日；独立会话、单股失败隔离 | `IMPLEMENTED`：bid/ask、volume、open interest、IV 快照及过期/缺字段测试；明确禁止从单快照推断方向，真实来源可用性与 LLM 解释待 P6 批次 |

## 状态定义

- `IMPLEMENTED`：代码和确定性契约存在，不代表外部来源本次可用。
- `RESEARCH_VALIDATED`：真实资料进入 Gate，并由真实 LLM 形成满足最低问题的实质报告。
- `SOURCE_LIMITED`：完成了限定尝试并保存失败、影响、未实现子能力和 TODO；不等于能力通过。
- `NOT_TESTED`：尚未在对应阶段执行，不得写成来源不可用。

## 已知延期子能力

- 结构化分部数值：SEC `companyfacts` 不保留 XBRL axis/member；需读取 filing XBRL instance 后才能建立可靠分部桥接。正文仍可供公司 Agent 定性分析，但不能冒充结构化分部数值。
- 机构持仓：13F 以申报机构为主体，不能只凭被投公司 CIK 直接得到完整机构持仓变化；需增加申报人发现、information table 解析、CUSIP/发行人身份绑定及两期可比链路。
- 研报：OpenAlex 主要覆盖学术与技术研究，不等于卖方股票研报库；正文 Content API 需要外置 API key。若真实批次没有可读正文，保留实际尝试和未验证范围；SEC 业绩附件只能标为发行人材料，不能冒充独立卖方或第三方研报。
- 期权：首版只有当前链快照，不提供历史 open interest、成交方向、净资金流、期权持仓估值或保证金研究。
