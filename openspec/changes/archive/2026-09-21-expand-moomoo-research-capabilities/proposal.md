## Why

当前 Moomoo SG OpenD 集成已证明部分 Quote API 可用，但“官方接口存在、manifest 已批准、Normalize 已实现、正式 Collector 已调用、专业能力实际消费”之间仍有断层：期权来源计划没有真实动态快照，Morningstar、评级、所有权与空头资料存在已采集但不可消费或已批准但未采集的情况，新增 Macro/Market Fundamentals 也尚未纳入来源职责与 PIT 约束。与此同时，官方网页已展示 v10.11 契约，而当前可运行并锁定的 SDK/OpenD 仍为 `10.10.7008`/server `1010`，需要在不提前宣称版本升级的前提下建立兼容验证和字段级时点语义。

本 Change 以已完成的只读 Spike 为依据，补齐高价值 Moomoo 能力从 Capture 到 Skill 消费的最小纵向闭环，并保持 SEC、Yahoo、BLS、Treasury、Federal Reserve 等现有主源职责、三域 Agent 拓扑和 Quote-only 安全边界不变。

## What Changes

- 以 Company / Macro / Market 的研究问题建立一份有界能力取舍清单：先复用已下载 SEC/Yahoo/官方宏观响应和已有 normalizer，再补 Moomoo。逐项记录接入、已有来源足够、权限受限或暂缓及原因，不以接口数量作为完成标准。
- 必须评估营收分部、管理层、财报日历、新闻线索、市场涨跌分布和期权标的总览/历史统计；候选先做有界 Spike，仅在存在实际资料缺口且可复用现有链路时接入。财报、估值、公司行动和行业关系接口先核对已有覆盖，不默认全量实施。
- 建立 Moomoo 官方文档版本与实际 SDK/OpenD 运行版本的兼容矩阵；v10.11 文档只作为 forward contract，未经当前运行版本真实验证的字段不得进入批准 manifest 或完成状态。
- 扩展只读 Quote allowlist，优先接入动态期权 `get_market_snapshot`、全市场期权成交量/持仓量统计、期权波动率、Macro 指标历史、FedWatch、经济日历、评级双维度和资金分布；每项保持明确的证券/区域、参数、分页、行数、请求与总时长预算。
- 将期权到期日、静态链、确定性有界合约选择和动态字段组成真实 `options_snapshot`；不得把静态链、全链上千合约或缺失字段冒充动态期权面。
- 统一字段级 Normalize/PIT：区分观察期、生效期、推荐日、供应商更新时间、公开/可知时间和获取时间；Morningstar 按 section、评级按 recommendation/update、机构汇总按报告期/更新时间、期权按价格与衍生字段分别处理。
- 将 Moomoo Macro History、Economic Calendar、FedWatch 和 Dot Plot 明确为二级供应商补充；官方 BLS、Treasury、Federal Reserve 继续作为宏观事实主源，供应商实际值、共识、前值、市场隐含概率和官方预测不得互换。
- 修复 Collector、来源选择、Gate/MCP、provider coverage 和多维 Evidence 选择，使合格资料实际到达 `RESEARCH_REPORT`、`OWNERSHIP_DISCLOSURE`、`MARKET_STATE`、`MACRO_CONTEXT` 与 `OPTIONS_FLOW`。
- 保持 Company / Macro / Market 三个稳定研究域以及现有 Company Analyst、Market Catalyst、Skeptic、CIO 职责；Options 继续作为 Market 域下的 `OPTIONS_FLOW` 专项，不新增 Options Agent、数据源 Agent 或第二套编排器。
- Company、Macro、共享 Market 分别验证正式输入交付与实际研究使用，Options 保留持仓动态快照专项验收；三域允许复用合格既有来源，不要求每域 Moomoo 必须成功。合理排除与路由故障分开，资料进入允许列表不等于已被研究使用。
- 沿用既有 adapter、缓存、Gate、metadata 和配置，只扩展变化的契约；不新增能力状态服务、通用路由引擎或独立时间框架。共享市场与宏观每批采集一次，并受证券级和全批预算约束。
- 明确排除 Trade Context、账户/持仓/资金/订单、远程 OpenD、Cookie/Token、任意 SDK 调用、期权下单/策略交易，以及首阶段无明确研究增量的全市场筛选榜、异动提醒和 0DTE 排行。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `futu-readonly-research-data`: 扩展并真实闭环高价值 Moomoo Quote 数据集，补充版本兼容、字段级 PIT、期权动态快照、Macro/Market Fundamentals 和逐能力完成证明。
- `research-domain-inputs`: 调整 Company、Macro、Market 的 Moomoo 数据集职责与消费位置，并明确 Options 是 Market 域专项而非新增顶层域或 Agent。
- `point-in-time-evidence`: 增加供应商复合响应的字段级观察、公开、更新和获取时间规则，禁止用单一响应时间覆盖不同字段语义。
- `multi-dimensional-holding-research`: 修复合格 Moomoo Evidence 到研报、所有权、宏观、市场及期权/资金专项的正式选择、查询、引用与受限状态验收。

## Impact

- Moomoo：`product/mcp/live/moomoo_opend.py`、版本化 manifest、Normalize、缓存与聚焦契约测试。
- 资料准备：`research_supplement_collection.py`、来源计划、能力矩阵、provider coverage、Gate/MCP 查询和逐证券冻结包。
- 多维消费：`multidimensional_stage.py` 的 capability Evidence 路由，以及相关 Company/Market Catalyst Skill 输入契约和测试。
- Macro/Market：现有官方宏观快照和 Yahoo 市场快照保持主路径；Moomoo 只增加显式补充/回退，不静默覆盖或混源。
- 既有来源复用：核对公司背景与已声明但未采集的数据集；优先从当前 Treasury 响应补充 2Y/10Y/30Y 和可核对期限差，复用已有 Yahoo 期权能力接入正式采集。只修改确实需要扩展的来源配置与消费契约。
- 版本与依赖：当前生产基线继续锁定 `moomoo-api==10.10.7008`，只有在新 SDK/OpenD 发布、字段重验、manifest/hash 更新和聚焦测试通过后才允许升级默认版本。
- 兼容性：已退役的 `live-us-equity/4.0.0` 仅维持历史读取，不重新启用；历史冻结 Evidence 不改写。
