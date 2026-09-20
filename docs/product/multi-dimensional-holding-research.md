# 普通股持仓多维研究

本文说明 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 产品阶段。它承接用户已经确认的 `PortfolioHandoff v3`，自动准备免费公开资料，并为每只普通股生成可供后续 Independent Skeptic 直接读取的结构化研究包。它不是组合决策阶段，不输出买卖动作，也不启动 CIO、Risk Engine 或真实交易。

## 运行链路

```text
PortfolioHandoff v3
→ 只读行情、SEC、NASDAQ、宏观、披露及期权资料采集
→ point-in-time Evidence Gate
→ 资料准备：公开研报发现 / 同行候选选择
→ 正文取得与同行有限采集、冻结、再次 Gate
→ 多维专业研究（有界并行）
→ HoldingResearchBundle + 中文报告
```

用户只提供已确认持仓，不需要制作 Evidence。系统仍保留完整组合，但本阶段只研究普通股；ETF、上市期权及账户级项目在覆盖表中保留为当前能力缺口，不能被静默删除。

## Agent、Skill 与工具边界

- `runtime_company_analyst`：公司基本面深化、公司事件和公司研报分析；复用已有公司研究报告，不重复生成同一份基础报告。
- `runtime_market_catalyst`：技术结构、行业同行、宏观环境、市场状态、所有权披露及期权市场结构。`MACRO_CONTEXT` 与 `MARKET_STATE` 是两个独立 capability、两个独立 invocation；前者解释利率、通胀、经济活动和政策传导，后者解释基准、板块、跨资产、波动/信用代理与短期市场事件。每个 invocation 只执行一个 capability。
- Skills：定义各维度应回答的问题、证据分层、反向条件和表达边界。
- 只读工具：获取与标准化公开资料、计算指标、冻结正文、核实同行身份；不得形成投资评级。
- Python：执行 PIT、Schema、引用闭合、依赖调度、哈希、渲染和存储；不得代替 LLM 选择 Thesis、同行赢家或交易动作。

## 资料准备与正式研究分离

公开研报和同行比较采用两步流程：

1. 资料准备 invocation 允许 Company Analyst 调用 `research_search`、`research_fetch`，允许 Market Catalyst 从冻结的 NASDAQ 候选池选择有理由的同行候选。
2. 工具核实并冻结正文或同行资料，再执行 PIT Gate。正式研究 invocation 只读取 Gate 合格资料，不继承搜索权限。

搜索标题和摘要始终是 `LEAD_ONLY`，不能写成已读研报。只有 `BODY_VERIFIED` 正文可进入研报报告。缺少正文 API key 等配置问题标记为 `BLOCKED_CONFIGURATION`；实际搜索/正文路径受限标记为 `SOURCE_LIMITED`。两者都必须引用本 invocation 的真实尝试产物，不能由模型自行宣称。

同行目录只用于限制候选范围与请求预算。`candidate_status=UNVERIFIED` 不是同行事实；只有 `materialization_status=FROZEN` 且对应 Evidence 已进入正式 Gate，Agent 才能进行实质比较。

## 并发和依赖

默认最多三个活跃 Subagent。技术、基本面、宏观和市场等独立任务可并行；正式研报分析等待正文准备与公司基础报告，正式同行比较等待候选选择、有限采集、Gate 与公司基础报告。某一资料路径失败只阻塞真实依赖项，不能阻止其他维度运行。共享 `MACRO_CONTEXT` 与 `MARKET_STATE` 各自每批只执行一次，不能再用一份历史 `MACRO_MARKET` 报告冒充两个维度均已覆盖。

## 输出

新运行的每个维度输出 `ResearchDimensionReport/2.0.0`，至少包含：

- 研究身份、Agent/Skill/模型及输入绑定；
- 具体问题、Claim、原始 Evidence、计算、假设和反向观察条件；
- 研报正文元数据及其对已有主张的支持、挑战、修订或无新增信息；
- 可比性、时效、来源和资料缺口；
- `COMPLETE`、`LOW_CONFIDENCE`、`INSUFFICIENT_EVIDENCE`、`SOURCE_LIMITED`、`FAILED` 或 `TIMEOUT` 状态。

最终 `HoldingResearchBundle/2.0.0` 同时引用已有 `EquityResearchReport`、新增维度报告、原始 Evidence 与产物哈希，按每只普通股列出每个维度的覆盖状态。它分别报告 `STRUCTURALLY_CONSUMABLE` 与 `DOWNSTREAM_READY`：前者只证明结构、绑定和引用可解析，后者还要求每只普通股的公司报告已经重新验证并纳入、补证来源处理完整、待反证问题或空值原因明确。

历史 `ResearchDimensionReport/1.1.0` 与 `HoldingResearchBundle/1.1.0` 仍可只读和确定性重组，其中 `MACRO_MARKET` 明确标记为 `LEGACY_COMBINED_COVERAGE`。兼容读取不自动升级历史结论，也不把一份合并报告判为 `MACRO_CONTEXT`、`MARKET_STATE` 两项通过。

历史阶段产物可通过确定性 `assemble-canonical-holding-research` 入口重组。该入口选择一个基础 run 和统一 decision cutoff，重新验证公司报告并复制到新的外置交接目录；它不会修改原运行包或调用模型。不同 run、cutoff、CouncilRequest 或 Evidence 集合的补证保留在 `package_provenance.excluded_supplements`，不能静默拼成同一次用户研究。

`unresolved_cross_dimension_questions` 只归集报告已经写明的观察或失效条件，并引用原报告和 Claim；Python 不判断哪项 Thesis 正确，也不补写投资意见。中文摘要只归集已验证报告，不消解跨维冲突、不生成统一分数。

## 首版最低研究问题

- 技术：多窗口趋势、相对基准、波动/回撤、量价关系和推翻当前解释的信号。
- 基本面与事件：业务与增长驱动、盈利质量、现金流/资本配置、适用估值假设、关键事件和未知项。
- 研报：作者依据、预测/估值假设、与其他资料的分歧、对已有研究判断的具体作用及利益披露限制。
- 行业：同行相对位置、行业与公司因素、需求/价格/周期传导和可比性限制。
- 宏观：相关利率、通胀、经济活动、央行政策与发布日历，对不同持仓的传导、敏感性和反向情景。
- 市场：大盘与相关板块、跨资产序列、波动/信用指标或明确代理，以及 24 小时市场事件；所有代理、时点和不能推断的方向必须显式说明。
- 所有权与期权：只解释实际取得的披露或快照、滞后和覆盖，不从单期数据推断资金方向。

## 当前来源与限制

当前三域及 provider 平面的权威映射见 [`holding-research-inputs.json`](../../product/profiles/holding-research-inputs.json)，来源、预算和实测状态见 [免费公开资料能力表](../data/free-source-capability-matrix.md)。新运行会在 manifest 中锁定该拓扑、引用版本与 hash；历史 `live-us-equity/4.0.0` 仅作 `RETIRED/COMPATIBILITY_ONLY` 读取，不再代表当前创建入口。

基础披露层以 SEC 与 Yahoo 为主：SEC 承担公司身份、申报、财务事实与公开事件，Yahoo 承担冻结行情、基准及可确定性派生的市场/估值输入。研究补充层可以接入本机 `127.0.0.1` Moomoo OpenD，但其当前契约只允许新加坡区域、只读 quote capability；OpenD 不可达、未授权或字段不足时，只降低对应 supplement 数据集状态，SEC/Yahoo 合格资料仍继续，不得回退到客户端 Cookie、私有接口或登录绕过。

公开研报正文、13F 两期机构持仓、历史期权结构和可验证资金行为等仍按能力矩阵逐项记录 `AVAILABLE`、`PARTIAL`、`SOURCE_LIMITED` 或准确失败状态。它们不是因为某个已归档 Change 而自动完成；只有真实采集、PIT Gate、冻结引用和对应 Agent 实际消费闭合后，才可提升本批次 coverage。

完成本阶段只证明 canonical 研究包可以供下一 Agent 消费，不代表 Skeptic、CIO、Risk 或候选版本晋升已经通过。
