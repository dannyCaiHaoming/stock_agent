## 1. 固化能力契约与安全边界

- [x] 1.1 在既有文档/覆盖产物中维护一份 Capability Gap Matrix，记录研究问题、已有来源、文档/运行证据、正式交付/实际使用及取舍；交付按 design 第 0 节逐项完整的清单，不新建状态服务
- [x] 1.2 核对公司背景各来源声明、Yahoo 已有动态期权能力及 Treasury 原始响应复用点，明确复用、接线、缺口和错误声明；以方法到 Collector/consumer 的对应清单验证无假可用来源
- [x] 1.3 按 design 第 0 节对候选完成有界评估，覆盖营收分部、管理层、财报日历、新闻、涨跌分布、期权标的总览/历史，以及财务/估值/公司行动/行业资料覆盖；每项记录接入或不接入原因与证据，未接入项不以实施完成标记
- [x] 1.4 对确定接入的方法扩展既有 Quote manifest/wrapper/validator 和 gap 处理，复用现有安全机制；以新增参数越界、敏感响应、权限/版本漂移及来源失败隔离的聚焦测试验证，不重复构建基础框架
- [x] 1.5 在既有采集入口落实 design 第 2 节的每证券/共享/全批请求与总时长预算，共享数据每批一次；以两证券、重试计数和预算耗尽 fixture 验证共享请求不重复且增强项不挤占核心

## 2. 完成动态期权纵向切片

- [x] 2.1 实现标的 snapshot、到期日、静态链和合约身份标准化，保留 source、security、currency、market、session 与原始/标准化字段，并以股票、期权及无可交易期权 fixture 验证证券隔离和缺口语义
- [x] 2.2 按 design 第 3 节实现最近/约 30 天/约 90 天到期日、近价 call/put 与 48 合约上限，优先纳入已确认持仓合约；以缺现价、平价去重、到期日不足、持仓合约超限及稳定排序测试验证可重现和真实覆盖
- [x] 2.3 实现选定合约的批量 `get_market_snapshot` 采集和字段级 Normalize，分别处理 bid/ask/last、volume、OI、IV、Greeks 与 regular/pre/after/overnight 时段，并以 PIT 测试验证价格时间不会被复制到无独立有效时间的衍生字段
- [x] 2.4 按取舍清单接入有增量的标的总览/历史、全市场 volume/OI 或最多四个代表合约 volatility；以合约样本、标的聚合、共享市场的隔离和延迟 OI 测试验证，不接入项以证据支持的取舍完成本任务
- [x] 2.5 复用 Yahoo 现有动态期权能力接到正式 Collector，并修正 Yahoo/Moomoo 主源回退与字段覆盖状态；以主源成功不重复请求、Yahoo 失败 Moomoo 成功、两源失败及静态链受限测试验证

## 3. 完成 Company 与所有权补充切片

- [x] 3.1 将 Morningstar 按正文 section、星级、fair value 和 report metadata 分离标准化，保存各自更新时间、许可层级及正文缺失 gap，并以多 section 时间不同、缺正文和仅 locator 的 fixture 验证不自动下载 PDF
- [x] 3.2 接入机构与分析师两个 rating 维度的一页有界采集，校验 `num`、outer entity、inner item 与 `next_key`，并以推荐日早于更新时间和分页未尽 fixture 验证 PIT 与覆盖限制
- [x] 3.3 统一机构汇总、内部人、short interest、capital flow 及取舍后接入的 distribution 的报告期、供应商更新时间、数据层级和证券身份，并以 period 无法解析、SEC 冲突及供应商计算流 fixture 验证不会冒充原始披露或真实买卖方身份
- [x] 3.4 将完成标准化的 Company/所有权数据集接入正式 Collector、逐证券冻结包与 Gate/MCP 查询，并以单证券成功、跨证券引用失败和单数据集权限失败的集成测试验证闭环及隔离
- [x] 3.5 根据 1.1–1.3 的取舍复用公司背景字段，按需接入营收分部/管理层/财报日历/新闻线索等候选；以至少一项原有背景缺口的接线或准确来源状态修正验证，保留新闻线索与可读正文的区别，不重建 SEC 全文解析器或关系图

## 4. 完成 Macro 与共享 Market 补充切片

- [x] 4.1 将 design 第 5 节的首批指标目标绑定到真实 ID、口径、单位、时区与用途，最多八系列/每系列 24 观测一页；以未知 ID、窗口越界、同比/水平混淆和单位测试验证，缺精确匹配时记录缺口
- [x] 4.2 接入有界 Macro history 与 Economic Calendar，区分 `data_time`、`release_time`、retrieval、actual、predict、previous 和 current-vintage 限制，并以未知发布时间时区及历史 cutoff 测试验证保守 PIT
- [x] 4.3 复用 Treasury 同一响应补充同日 2Y/10Y/30Y 与 10Y−2Y；以缺期限和不同日期测试验证不错误拼接。按取舍清单接入涨跌分布、FedWatch、Dot Plot 或共享 snapshot，并验证各自来源层级与剩余缺口
- [x] 4.4 在来源计划和 provider coverage 中保持 BLS、Treasury、Federal Reserve 主源，按数据集暴露 Moomoo 二级补充、冲突与失败状态，并以同观察期官方/供应商值并存和 Moomoo 不可达测试验证不静默选 winner

## 5. 闭合 Gate、路由与专业消费

- [x] 5.1 在现有选择器增加小型 dataset/semantic field 映射，补齐 Macro/Market provider scope 和候选公司事实/日程/行业材料的既有输入映射；沿用证券/cutoff/批次校验，以正向交付及跨证券/错误能力反向测试验证
- [x] 5.2 在既有覆盖产物中记录采集、Gate 合格、交付数量及排除原因，仅对本次应交付且无合法排除原因的漏选报 `CAPABILITY_EVIDENCE_NOT_ROUTED`；以去重/主源覆盖/专项未启用/预算裁剪和真实漏选测试验证，交付与实际引用状态分开
- [x] 5.3 更新 Gate/MCP 输出契约和专业任务输入，使 `allowed_evidence_ids` 只包含同一 cutoff、证券和 capability 的冻结 Evidence，并以历史 cutoff、跨批次、跨证券和 source-limited 测试验证 fail closed
- [x] 5.4 更新现有 Company Analyst、Market Catalyst 及相关专业 Skill 的字段说明与引用限制，不新增 Agent 或顶层域，并以 topology/config/schema 快照测试验证仍为 Company / Macro / Market 三域且 Options 留在 Market 的 `OPTIONS_FLOW`
- [x] 5.5 在既有时间字段与 metadata 上验证复合响应字段族、当前修订 actual、未来 Calendar/FedWatch 事件的 PIT，必要时局部扩展；以旧 cutoff 排除当前修订值、当前可知未来日程允许引用的测试验证，不建立新时间框架

## 6. 版本、回归与文档一致性

- [x] 6.1 仅更新契约实际变化的 manifest/source policy/source plan/schema/topology 与相关 hash，保持批准运行基线；以配置加载验证无漂移和文档/运行版本混淆，不统一升级无关组件
- [x] 6.2 更新开发与产品文档中的 Moomoo 能力矩阵、PIT 规则、来源层级、Options 有界策略和受限状态，并以文档链接/术语扫描验证不再把 adapter、Spike、`AVAILABLE` 或静态链描述为正式消费完成
- [x] 6.3 运行与本 Change 相关的 adapter、Normalize、PIT、Collector、Gate/MCP、路由和拓扑确定性测试，并记录命令、结果与失败修复；所有聚焦测试通过后才允许进入真实持仓验收
- [x] 6.4 复用版本、参数、字段和证据引用仍有效的既有 Spike，仅对新增/变化部分执行有界 Quote 验证，写回能力清单；核对所有条件接入项有成功证据或具体受限/暂缓原因，不对未变部分重复全量探测
- [x] 6.5 验证 OpenD 不可达、权限变化、schema drift、Yahoo/Moomoo 回退和已退役 `live-us-equity/4.0.0` 历史读取回归，并证明当前正式 profile 与 SEC/Yahoo/官方宏观主流程不受新增补充失败影响

实施证据（2026-09-21）：相关 adapter、Normalize、PIT、Collector、Gate/MCP、路由、拓扑及 Company 启动边界共 192 项聚焦测试通过；新增 fixture 覆盖持仓到期日替换、持仓合约超限、缺现价、到期日不足、ATM 去重、稳定排序、单次失败不重试、逐证券/共享时间预算耗尽和 Dot Plot SDK 方法漂移。OpenSpec strict validation与 `git diff --check` 通过。锁定 SDK/OpenD 的有界 Quote 验证确认机构/分析师 rating 两种响应可分别标准化，并确认实际 SDK 只提供 `get_fed_watch_dot_plot`。

同一已确认 MRVL Handoff 的修复后真实采集、PIT Gate 和零模型准备位于 `/private/tmp/expand-moomoo-research-capabilities-prepare-20260921-v5`：Yahoo 从 19 个到期日、388 个候选中只冻结最近/约 30 天/约 90 天的 48 个近价合约；`options_snapshot` 在 Capture、Gate 和 dispatch 均为 48 条，Dot Plot 为 12 条 `AVAILABLE` Evidence。获用户明确授权后的 `OPTIONS_FLOW` 单任务宿主 Smoke 位于 `/private/tmp/expand-moomoo-research-capabilities-multidimensional-20260921-v4/run`，execution proof 为 `PASSED`，报告因缺 Greeks、multiplier、完整链和主动买卖方向而如实保持 `SOURCE_LIMITED/PARTIAL`，并正确限制在三个所选到期日。此前完整多维 Smoke `/private/tmp/expand-moomoo-research-capabilities-multidimensional-20260921-v2` 继续作为同一持仓的 Company、Macro、共享 Market 正确引用证据；旧 `-v3` 的 252 条期权输入只保留为首次复核发现问题的失败证据，不再作为 7.1 验收依据。

## 7. 持仓闭环验收与收尾

- [x] 7.1 使用同一份已确认 PortfolioHandoff，通过宿主 launcher 对至少一只实际持仓普通股执行获批的真实纵向 Smoke，保存动态期权 `Capture → Normalize → PIT → Gate/MCP → OPTIONS_FLOW` 的逐层证据；若持仓确无合格期权，仅记录真实尝试并等待用户明确接受范围调整
- [x] 7.2 在同一次或同一 cutoff 验收中对 Company、Macro、共享 Market 分别证明至少一项资料完成交付与正确引用/解释，允许复用 SEC/Yahoo/官方宏观；验证三域使用证据、完整缺口清单与来源限制齐全，Moomoo 单源受限不自动否决已有主源成功的域
- [x] 7.3 完成独立只读复核，核对实现差异、四份 delta spec、确定性测试和真实持仓证据；修复范围内问题后取得人工完成批准，未批准前不归档、不宣称 Change 完成

  独立 Reviewer 第二轮结论为 `CHANGE_REVIEW: PASS`：首轮发现的 Yahoo 全链注入、持仓合约优先级、Dot Plot 方法名与预算 fixture 缺口均已闭合；未发现代码、契约、证据、安全或过度设计方面的归档阻塞。用户于 2026-09-21 明确批准完成、同步且归档；该批准不代表 Promotion PASS。
