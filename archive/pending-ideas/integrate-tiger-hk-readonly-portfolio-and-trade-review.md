## Why

当前 `portfolio-intake` 只接受截图和手工输入，虽然协议预留 `BROKER_READ_ONLY_API`，但尚不能从用户的老虎证券香港账户稳定取得当前持仓，也没有可审计的私人交易账本来支持长期复盘。用户已经确认允许严格只读的券商账户与历史数据接入，因此需要在不引入任何交易能力的前提下，把当前美股持仓和老虎实际可提供的历史活动接入现有系统，并以图形和结构化分析支持复盘。

## What Changes

- 将长期产品边界从“禁止任何券商接入”收敛为“允许经过显式授权、严格只读的券商数据接入”，继续永久禁止下单、改单、撤单、换汇、转账、交易解锁和其他账户写入；实施时同步根开发指令与产品方向说明。
- 新增 Tiger Brokers Hong Kong（`TBHK`）只读适配能力，只从仓库外本地配置加载官方 OpenAPI 配置与 Token，并以硬编码接口白名单获取账户、资产、持仓、订单、成交、费用、资金流水和历史资产数据。
- 第一版在私人账本与账户覆盖清单中保留 Tiger 全账户可见资产，但只把美股普通股、ETF 和美股上市期权规范化为现有 `PortfolioDraft v3`，继续经过用户确认才生成 `PortfolioHandoff v3`。混合市场账户 SHALL 将受支持的 US/USD 资产声明为 `USER_DEFINED_PORTFOLIO`；港股、窝轮、牛熊证、期货、基金及非美元资产保留为账户覆盖中的“已采集但投研接入待定”项，不进入当前 Handoff，也不阻断美股子组合确认。只有账户全部属于当前支持范围时才可声明 `BROKER_ACCOUNT`。
- 新增仓库外单一 SQLite 私人交易账本，按时间窗和分页采集老虎 API 实际可见的全部历史，以四组逻辑表保存活动修订、每日资产、同步窗口和分析包；以稳定上游 ID 去重，保留来源、时间、内容 hash、同步水位、失败区间和覆盖状态，不增加内容寻址文件系统或按活动类型扩张成多套主表/修订表。
- 将“API 实际可见的全部历史”与“账户完整生命周期”分开：首次同步保存用户声明的历史起点及其准确/估算状态，接口缺失、历史保留限制或不连续区间必须显式记录。第一版交付最多证明 `API_COMPLETE_WITHIN_DECLARED_WINDOW`；`FULL_HISTORY_RECONCILED` 只作为未来结单勾稽能力的保留状态，不是本 Change 的完成条件。
- 新增确定性交易复盘计算，覆盖现金流调整收益、回撤、已实现/未实现盈亏、费用、分红税费、已平仓交易胜率、盈亏比、持有期及订单执行状态；Python 负责全部数值计算并输出版本化图形数据。第一版不实现 LLM Historical Trade Reviewer、主观评分或税务结论，待确定性账本和页面真实跑通后再独立评估。
- 在现有本机只读研究浏览器增加独立 `/trades` 页面，读取显式准入的私人账本和已验证分析产物，展示核心指标、完整可筛选流水和服务器端图形；浏览器刷新不得连接老虎、加载凭据、调用模型或写入账本。
- 第一版使用显式本地同步，不增加常驻 daemon、后台定时任务、第二套编排器、前端框架或浏览器端图表依赖；真实凭据、账户号、持仓、账本和分析产物均不得进入 Git。

## Capabilities

### New Capabilities

- `tiger-readonly-broker-data`: 定义 TBHK 官方 OpenAPI 的本地凭据边界、只读接口白名单、当前账户快照、全量/增量历史同步、私人账本、覆盖证明及 fail-closed 行为。
- `trade-history-analysis`: 定义交易活动规范化、账户现金流勾稽、确定性绩效与行为指标、图形数据及非税务/非交易边界。

### Modified Capabilities

- `portfolio-intake`: 将已预留的 `BROKER_READ_ONLY_API` 实际接到 Tiger 账户快照，同时保持 v3 的用户确认、字段 lineage、美股/美元范围和未支持资产披露。
- `local-research-browser`: 增加独立、只读且默认不暴露私人原始数据的交易复盘页面与图形展示，不改变现有 Macro、Market、Company 的只读读取语义。
- `point-in-time-evidence`: 将外部数据只读要求细化为允许受限券商查询，但禁止向 Runtime Agent 暴露凭据或任何券商写接口，并为私人账户事实保留来源与双时间语义。

## Impact

- 预计影响根 `AGENTS.md`、`PRODUCT.md`、`product/AGENTS.md`、Intake Schema/Service、只读券商适配层、私人账本与确定性分析模块、本机浏览器 registry/路由/渲染、启动脚本、文档及聚焦测试。
- 新增官方 Tiger OpenAPI Python SDK 依赖或等价的受限封装；具体版本必须锁定，并通过适配器隐藏全部交易、转账和账户修改方法。
- 真实配置只允许位于仓库外权限受限目录；产品产物只保存脱敏账户引用，不保存 RSA 私钥、TBHK Token、密码、完整账户号或可重放认证材料。
- 与当前 `activate-independent-skeptic-for-multidimensional-research` Change 相互独立；本能力只改善持仓输入和个人历史复盘，不启动 Skeptic、CIO、Risk、回测、Regression 或 Promotion。
