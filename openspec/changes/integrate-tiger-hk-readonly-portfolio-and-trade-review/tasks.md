## 1. 产品边界与官方能力 Spike

- [x] 1.1 将根 `AGENTS.md`、`PRODUCT.md` 与 `product/AGENTS.md` 对齐为“允许明确批准且严格只读的券商数据接入，永久禁止交易与账户写入，并且不索取凭据正文”，通过文档差异检查确认三处无冲突且未放宽下单禁令。
- [x] 1.2 锁定官方 Tiger Python SDK 版本，逐项核对 TBHK 配置、Token、账户类型及白名单读取方法，并用版本化 capability manifest 和契约测试证明没有任意方法透传；记录官方文档版本/链接和实际字段 gap。
- [x] 1.3 定义不输出金融数据的配置引用与 preflight 契约，覆盖仓库外目录、权限、`license=TBHK`、必要文件、Token 状态和清理后错误码；用缺文件、弱权限、仓库内路径与符号链接 fixtures 验证设计可以 fail closed。
- [x] 1.4 基于锁定 SDK 源码、官方文档和合成响应完成离线 Capability Gap Matrix，逐项映射账户/持仓/订单/成交/费用/资金/资产历史字段、分页限制和待真实核对项；不在适配器与宿主入口完成前直接连接真实账户。

## 2. 契约与私人存储

- [x] 2.1 只增加 `TigerAccountSnapshot`、`BrokerSyncManifest` 和 `TradeHistoryAnalysis` 三个边界 Schema，图形数据内嵌于分析包，数据库行保持内部 schema；用正负样例验证 `source_id/as_of/retrieved_at`、hash、脱敏账户引用、状态枚举和未知字段拒绝，不增加独立 Chart、活动行或 `TradeReviewReport` Schema。
- [x] 2.2 实现仓库外 `PrivateBrokerLedger` 初始化、路径/权限检查、SQLite schema/version 和只读诊断；用仓库内路径、symlink、版本未知、只读连接和数据库繁忙测试验证私人数据不会进入 Research Memory 或 Git。
- [x] 2.3 在单一 SQLite 中实现 `activity_revisions`、`asset_points`、`sync_windows` 和 `analysis_packages` 四组核心逻辑表；用严格活动类型区分订单、成交、费用和资金活动，并以相同 ID/相同内容、相同 ID/修订内容和无稳定 ID 替代键测试证明去重、追加 revision 与旧版本保留，不增加内容寻址对象目录或按类别复制主表/修订表。

## 3. Tiger 严格只读适配与同步

- [x] 3.1 实现惰性加载官方 SDK 的 Tiger 只读适配器和固定接口白名单；用记录调用的 fake client 验证允许查询可执行，而下单、预览、改单、撤单、换汇、转账、权限抢占、未知方法和底层 Client 获取均在网络前拒绝。
- [x] 3.2 实现当前账户资产与全持仓快照，保存同批次时间、来源、内容 hash、原始市场/币种/资产类型和未支持原因；用 US/USD、HK/HKD、期权、空仓和混合账户 fixtures 验证全账户覆盖与子组合完整性分离，港股被标记为投研接入待定且不静默丢失或换汇。
- [x] 3.3 实现订单与逐笔成交的分窗/分页全量和增量同步：先取得窗口内全部订单状态，再对每个实际成交数量大于零的订单补取逐笔成交与订单费用；保留部分成交和状态修订。用跨页、90 天边界、取消前部分成交、空页、重复游标、限流、超时和中间窗口失败测试验证请求有界、成交不遗漏且水位不跨 gap。
- [x] 3.4 实现逐订单费用、资金明细、出入金与历史资产同步，并保存各类别独立水位和重叠检查；用费用延迟修订、分红税费、公司行动、换汇、入金/出金、多币种和类别缺失 fixtures 验证语义不混合。
- [x] 3.5 生成包含 `history_start`、`EXACT|APPROXIMATE` 起点准确度、实际范围、分类计数、分页 receipt、重复/修订数和失败区间的覆盖清单；用 `PARTIAL` 与 `API_COMPLETE_WITHIN_DECLARED_WINDOW` 样例验证状态不能越级，并验证第一版永不产生为未来结单勾稽保留的 `FULL_HISTORY_RECONCILED`。
- [x] 3.6 提供显式 `preflight`、`snapshot`、`sync` 与 `analyze` CLI，限制真实写入到仓库外 ledger root；用帮助输出、结构化状态码、重复执行和中断恢复测试验证无 daemon、无隐式网络和无凭据回显。

## 4. Portfolio Intake 接缝

- [x] 4.1 将有效 Tiger 当前快照转换为现有 `PortfolioDraft v3`：同一快照中全部受支持 US/USD 普通股、ETF 和上市期权进入声明范围；混合市场账户使用 `USER_DEFINED_PORTFOLIO`，港股等资产进入独立覆盖清单且不写入会阻断 Handoff 的 `unsupported_assets/unresolved_fields`；只有全部资产均受支持时才允许 `BROKER_ACCOUNT`。用纯美股、混合市场和无受支持持仓 fixtures 验证范围与完整性语义。
- [x] 4.2 保留 API 字段级 lineage、券商原始未定义字段与账户勾稽，并确保 API Draft 仍需一次明确用户确认；用缺失保证金字段、身份歧义、金额不勾稽、混合账户只有全账户汇总金额和确认路径测试验证不推断、不把全账户净资产/现金冒充子组合字段、不自动生成 Handoff。
- [x] 4.3 实现新账户快照产生新 Draft、旧 Handoff 不变的版本行为；用持仓、现金与成本变化测试验证旧 hash 不被覆盖且下游不会静默切换组合。

## 5. 交易历史确定性分析

- [x] 5.1 实现冻结 ledger revision set 和覆盖状态的分析输入装配，只聚合 US/USD 受支持资产，同时保留非 US/非 USD/未知记录排除计数；用混合市场、多币种和账本后续修订测试验证历史分析不可变。
- [x] 5.2 实现 `formula_version=v1`：现金流调整日收益与累计收益、drawdown、realized/unrealized、费用、分红税费、胜率、盈亏比、Profit Factor、期望、持有期和订单状态；用手算 fixtures、零分母、缺费用、入出金、缺资产点和开放仓位测试核对精确结果与 `unavailable` 原因，第一版不以换手率为完成条件。
- [x] 5.3 使用稳定证券身份与 FIFO 实现仅用于复盘的交易 episode，并完成证券/月度拆分，区分券商 reported P&L 与系统复盘值；用分批买卖、卖空、部分成交、期权到期/指派缺腿、公司行动和身份不确定记录测试证明不冒充税务 lot、不强行闭合 episode。
- [x] 5.4 在 `TradeHistoryAnalysis` 内生成六组版本化结构化图形数据，并用短窗口、缺资产点、开放持仓、费用不完整和非 USD 排除测试验证实际窗口、单位、点数、`LIMITED` 与来源/hash 绑定；月度收益率与月度净盈亏不得混用，不增加独立 Chart Schema。

## 6. 本机网页与图示

- [x] 6.1 为浏览器增加可选私人账本只读 reader、`--trade-ledger` 启动参数、health 诊断、顶级导航和 `/trades` 路由；用未配置、有效、忙、损坏和未知版本 ledger 测试验证交易页独立降级且三域不受影响。
- [x] 6.2 实现交易复盘概览、覆盖状态、确定性指标和限制展示，并以服务器端 inline SVG 渲染资产/净入金/收益、回撤、月度热力图、证券盈亏/费用、持有期散点和交易时间线；用实际非空合成数据验证每张图的语义、单位、实际窗口和窄屏可读性，不依赖 LLM 或复盘报告。
- [x] 6.3 实现活动表的日期、证券、市场、币种、方向、类别和状态筛选及分页，保持订单/成交/费用/资金活动语义；用部分成交后撤单、重复观察和非 USD 排除记录验证不重复计数且不提供原始对象下载。
- [x] 6.4 对 `/trades` 执行 Host/Origin、CSP、HTML/SVG 转义、路径穿越、符号链接、敏感字段和 no-store 检查，并对浏览前后 ledger/分析 hash；验证刷新、筛选和版本切换不连接 Tiger、不调用模型、不刷新 Token、不写账本。

## 7. 集成验收与收尾

- [x] 7.1 将 Tiger 只读模式接入现有 `scripts/run-product-smoke.sh` 宿主 launcher，保证真实账户请求只能经该入口启动；用 mock transport 验证底层 CLI/临时脚本不作为真实验收入口，默认 self-check、demo 和浏览器不会隐式启动 Tiger。
- [x] 7.2 运行受影响的 Schema、Intake、账本、同步、分析和浏览器聚焦测试，并核对当前 `scripts/council-dev.py self-check` 的实际白名单；在没有适用既有 run 的情况下记录无参命令被 `SELF_CHECK_COMMAND_NOT_ALLOWED` 拒绝，不虚构 self-check PASS。记录实际命令、输出、全仓基线失败和关键 hash；不得隐式启动真实账户、LLM Eval、Regression、Ablation 或 Promotion。
- [x] 7.3 使用仓库外合成 ledger 完成“同步 fixtures → Draft → 用户确认样例 → 历史分析 → `/trades`”纵向切片，并实际检查桌面与窄屏页面；纵向切片至少包含一个 US/USD + HK/HKD 混合账户，证明港股保留在覆盖清单、当前投研接入待定且不阻断 US/USD Handoff，同时验证源码和所有输入 hash 在只读浏览前后不变。
- [ ] 7.4 在用户本机配置就绪后，只经宿主 launcher 执行 TBHK preflight、最小当前快照、一次有界初始同步、一次相同窗口重复同步和一次带重叠窗口的增量同步，再生成确定性分析；验证重复同步不增加经济活动、重叠窗口可接收修订、水位不跨 gap。验收记录仅保存脱敏状态、分类计数、时间窗、gap 和 hash，私人账本、配置、日志、持仓与分析全部留在仓库外。未执行时明确记为真实接入未验证，不得宣称 Change 已跑通。
- [x] 7.5 更新管理台准备、Token 续期、首次历史起点及准确度、显式同步、覆盖状态、Intake 确认、确定性交易图示、隐私与故障处理文档，并检查示例不含真实账号、绝对个人路径、私钥、Token 或个人交易。
- [ ] 7.6 执行 `openspec validate integrate-tiger-hk-readonly-portfolio-and-trade-review --strict`、敏感信息扫描和独立差异复核；只有规格、实现、真实只读验收与复核均通过后才请求人工完成批准，且不得把 Change 完成称为候选 Promotion。
