## ADDED Requirements

### Requirement: Moomoo 补充字段必须映射到既有研究域和专业能力
系统 MUST 继续使用 Company、Macro、Market 三个稳定研究域，并按数据语义而非 provider 名称分配 Moomoo Evidence。Company 域的 `RESEARCH_REPORT` SHALL 消费合格评级/目标价共识、评级历史和分章节 Morningstar 材料；Macro 域的 `MACRO_CONTEXT` SHALL 消费宏观实际、单独标记的供应商 consensus、日历、官方预测转引及其来源限制；Market 域的 `MARKET_STATE` SHALL 消费共享市场快照、全市场期权统计和 FedWatch 市场预期。期权合约及个股供应商资金数据 SHALL 由 Market Catalyst 的既有 `OPTIONS_FLOW` 专项消费；机构、内部人与空头披露 SHALL 由 `OWNERSHIP_DISCLOSURE` 消费。上述消费以数据合格且本次专项启用为前提，条件接入增强项未取得时保留取舍结果与缺口。系统 MUST NOT 为 Moomoo、Options、Macro 数据或页面栏目新增数据源 Agent。

#### Scenario: Morningstar Evidence 通过 Gate
- **WHEN** 某普通股的分章节 Morningstar Evidence 通过同一 cutoff Gate
- **THEN** 它可进入 Company 域 `RESEARCH_REPORT`，但不得进入 `FUNDAMENTAL_EVENT` 作为 SEC 原始事实，也不得被 Macro 或 Market invocation 消费

#### Scenario: 全市场 Put/Call 统计通过 Gate
- **WHEN** Moomoo 返回美国证券期权市场按日成交量或 OI 的 call、put、total 和 ratio
- **THEN** 统计进入 Market 域共享 `MARKET_STATE` 或作为 `OPTIONS_FLOW` 的明确市场基线，不绑定为任一公司的资金方向事实

#### Scenario: 个股期权和资金流通过 Gate
- **WHEN** 某证券具有合格 options snapshot、IV/HV 或供应商资本流/分布 Evidence
- **THEN** Evidence 只进入该证券的 `OPTIONS_FLOW`，保持证券隔离，不进入共享 Macro 报告或其他证券任务

### Requirement: Moomoo Macro 必须作为二级补充而非官方宏观层替代
当前 provider 视图 MUST 保留 `OFFICIAL_MACRO` 中 BLS、Treasury 和 Federal Reserve 的主源职责，并在 `RESEARCH_SUPPLEMENT` 中逐数据集显示 Moomoo Macro、Economic Calendar、FedWatch 和 Dot Plot 的实际状态。Moomoo 实际值只有在官方主源缺少对应系列或作为冲突/覆盖补充时进入 Macro Context；供应商共识和 FedWatch 概率 MUST 使用独立字段与来源类型，不能替代官方实际值或政策正文。

#### Scenario: 官方系列已经可用
- **WHEN** BLS 已提供同一观察期的 CPI、失业率或非农事实
- **THEN** Moomoo 同类值不覆盖官方 Evidence，只作为二级交叉核对、供应商预期或覆盖说明

#### Scenario: 官方 Collector 尚未覆盖某系列
- **WHEN** Moomoo 提供 PPI、核心 CPI、PCE、零售销售或其他已批准系列，而当前官方 Collector 没有对应事实
- **THEN** Macro Context 可在明确 `SECONDARY_VENDOR`、单位、观察期、发布时间和历史 vintage 限制后使用，不将其重新标记为官方来源

### Requirement: Provider coverage 必须暴露采集与消费两种状态
当前拓扑和每批 provider coverage MUST 分别说明数据集的文档/Spike/采集状态与下游交付状态，并记录合理排除原因。`AVAILABLE` 或 `PARTIAL` 的响应若未进入正式 Collector、Gate/MCP 或目标 Skill，MUST 显示为未完成交付；进入允许列表仅证明交付，实际研究使用 MUST 依据有效报告的引用与解释验证，不能仅凭 adapter、Normalize 或选择数量宣称已消费。

#### Scenario: 采集成功但选择器不匹配
- **WHEN** 合格 Moomoo Evidence 已写入冻结包，但目标 capability 的 Evidence 选择规则没有包含该 semantic field 或 dataset
- **THEN** provider coverage 标记采集成功、消费未接线，并使对应专项验收失败而不是把 Evidence 静默丢弃

#### Scenario: Moomoo 当前批次失败
- **WHEN** OpenD 不可达、权限不足或接口字段漂移
- **THEN** 只降低受影响的数据集和 capability 消费状态，SEC/Yahoo/官方宏观仍按其合格输入继续运行

### Requirement: 三域补全必须先复用既有资料并核对剩余缺口
系统 MUST 分别维护 Company、Macro、Market 的研究问题与资料覆盖，优先使用已下载响应、现有标准化结果和已授权来源。来源计划声明的公司治理、关系、资本配置、指引和事件数据 MUST 与真实采集/消费状态一致；未实现的回退不得冒充可用。候选公司事实、日程、新闻和行业材料 MUST 按语义进入既有输入或专项，保留供应商层级，不能全部归入研报观点。

#### Scenario: Treasury 已下载响应含多个期限
- **WHEN** 同一日期的响应具有合格 2Y、10Y、30Y 数据
- **THEN** 复用响应输出期限事实与可核对的 10Y−2Y 期限差；期限缺失时保留 gap，不额外抓取相同资料或跨日期拼接

#### Scenario: 公司背景来源声明尚未兑现
- **WHEN** 某数据集仅有来源配置，正式采集不存在或资料没有被正确交付
- **THEN** 补接可复用链路或纠正来源状态，保留真实资料缺口，不以方法存在将背景资料标记齐全
