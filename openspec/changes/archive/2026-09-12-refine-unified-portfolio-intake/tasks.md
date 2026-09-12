## 1. v3 输入契约与兼容边界

- [x] 1.1 新增 `PortfolioDraft v3` 与 `PortfolioHandoff v3` Schema，保留 v2 Schema 文件与历史校验路径；用正负 Schema 测试验证默认 v3、显式 v2、未知版本、v2/v3 字段混用和历史 hash 不变。
- [x] 1.2 在 Draft/Handoff 中增加规范化 `account_snapshot`，区分账户类型、净清算价值、证券市值、现金余额、可用资金、购买力及保证金字段；测试明确零、负现金、未知值、冲突值和不同账户金额字段互不覆盖。
- [x] 1.3 精确定义 Position 的 `quantity_unit`、`average_cost_price`、`quote_price/quote_unit`、带符号 `market_value`、`unrealized_pnl_amount`、`unrealized_pnl_percent` 和币种；测试普通股/ETF 使用 SHARE、Long/Short Option 使用 CONTRACT，且 `-1 × 0.66 × 100` 不会被误读为 `-0.66 USD`。
- [x] 1.4 保留完整期权标的、CALL/PUT、到期日、执行价、乘数、原始合约标识和调整状态；测试缺失可选账户字段不阻断、零数量拒绝、负数量原样保留且调整合约歧义必须澄清。
- [x] 1.5 增加字段级 lineage、`broker_reported_fields`、`unknown_fields` 和派生值公式血缘；验证同一 Position 的截图字段与用户修订字段可分别追溯，未定义“保证金水平”不被静默映射。
- [x] 1.6 增加证券身份结构和 `OBSERVED | USER_CONFIRMED | RESOLVED | AMBIGUOUS` 状态，并预留 `BROKER_READ_ONLY_API`、`BROKER_STATEMENT` 来源类型；测试歧义身份阻断 Handoff，预留类型不触发真实券商连接。

## 2. 单一 portfolio-intake Skill 与确定性服务

- [x] 2.1 更新 Draft 创建、手工合并和用户修订流程，使同一个 Intake 输入同时处理账户摘要、股票、ETF 和期权；聚焦测试证明不创建按资产划分的输入 Agent、不读取 Research Agent 清单且不启动产品研究。
- [x] 2.2 将结构化截图行分类为 `ACCOUNT_TOTAL`、`ASSET_CLASS_SUBTOTAL`、`POSITION`、`CASH_BALANCE`，只从 Position 行生成持仓；测试总计/小计不会重复入仓，未知行保留待澄清。
- [x] 2.3 实现版本化账户勾稽，输出报告值、计算值、差额、容差、组成字段和 `RECONCILED | UNRECONCILED | NOT_EVALUATED`；测试带符号期权市值参与总值、超容差不静默调数、组成不足不伪造通过。
- [x] 2.4 更新最小确认规则：要求声明范围、基础币种、明确现金、非歧义证券身份、非零数量及单位、完整期权身份、字段级来源和当前 Draft hash；测试购买力/保证金/报价缺失可以确认，而未知现金、歧义证券、不完整期权或悬空 lineage 仍被阻断。
- [x] 2.5 更新 Handoff 构建与校验，使 v3 只包含中立账户与持仓事实，移除研究问题、期限、范围、benchmark、Mandate、Research Capability、readiness 与 plan 字段；测试任一旧任务字段出现在 v3 时 fail closed。
- [x] 2.6 更新中文 Draft 摘要和集中澄清输出，分别展示账户总计、现金、可用资金、购买力、保证金、勾稽状态、身份歧义及全部持仓；测试普通“继续”仍不算确认、用户修订产生新 hash 并使旧确认失效。
- [x] 2.7 更新 Intake CLI 默认生成 v3，并提供显式历史 v2 只读校验入口；测试 CLI 不静默迁移、重算或覆盖历史 v2 产物。

## 3. CouncilRequest 与最小规划接缝

- [x] 3.1 新增独立版本化 `CouncilRequest` Schema 和确定性构建/校验入口，绑定 Handoff/Portfolio hash 并承载研究问题、持有期限、`ALL_INPUT_POSITIONS`、benchmark、Mandate 和可选约束；测试改变研究问题只产生新 Request，不改变 Handoff 或重新确认持仓。
- [x] 3.2 将资产到 Research Capability 的映射和可用性判断从 Intake 模块移至 Council 所有的确定性规划接缝；验证同一 Handoff 与有效 Request 在不改变输入 hash 的情况下生成普通股、ETF、期权计划项和能力缺口。
- [x] 3.3 让 Council 规划接缝校验确认状态、Request/Handoff/Portfolio hash、全持仓研究集合和版本边界；测试十只持仓不截断、请求遗漏持仓、缺失期限、Draft、未知版本或绑定错误均在任何 Agent 前失败或进入明确补充状态。
- [x] 3.4 为规划输出增加 `planning_only`、输入 hash、总数、待处理项、覆盖状态和能力状态；验证该入口不获取 Evidence、不调用 LLM/专业 Agent、不生成 Thesis、动作、Risk 结果或最终报告。

## 4. Skill、文档与合成样例

- [x] 4.1 更新 `portfolio-intake` Skill 和契约说明，明确一个 Skill 统一识别多资产及账户信息、账户展示价格不等于研究 Evidence、Handoff 与 CouncilRequest 生命周期分离；通过静态边界测试验证字段名与 v3 Schema 一致。
- [x] 4.2 更新合成多资产样例，覆盖账户总计/小计、普通股、ETF、空头 Put、现金、可用资金、购买力、部分缺失保证金、期权单位和字段级来源；验证样例通过 v3 Schema 且不包含私人账户数据或研究结论。
- [x] 4.3 增加同一 Handoff 对应两个不同 CouncilRequest 的合成样例，验证持仓 hash 稳定、研究请求 hash 不同且全部持仓研究范围一致。
- [x] 4.4 更新面向用户的输入说明和 Council 接缝说明，明确 Handoff 完成不代表 ETF/Options Research 可用、券商来源类型不代表 API 已接入；检查文档链接、示例版本和协议字段一致。

## 5. 限定验证与人工完成批准

- [x] 5.1 运行 Intake v3、历史 v2 兼容、单位语义、字段级 lineage、身份、汇总行、账户勾稽、CouncilRequest、规划接缝和隐私边界的聚焦确定性测试，并执行 OpenSpec strict validate；不得启动产品 LLM、真实行情、Council Smoke、Replay、Regression 或完整 Gate。
- [x] 5.2 使用用户现有多资产持仓截图在仓库外重新生成并确认 v3 Draft/Handoff，核对三只普通股、SOXL ETF、空头 SOXL Put、账户总计、现金、期权报价/乘数/带符号市值和盈亏字段；未显示购买力/保证金保持未知，汇总行不重复入仓，仓库不出现真实持仓内容。
- [x] 5.3 基于该 Handoff 单独创建 CouncilRequest 并交给最小 Council 规划接缝，验证五项持仓全部进入规划、能力状态由 Council 产生、Handoff hash 不变、零 Agent/LLM 调用且没有投资输出；保存脱敏结果路径和 hash。
- [x] 5.4 汇总本 Change 的规格、差异和限定验证结果，取得一次明确人工完成批准；未获批准不归档、不提交、不推送，也不恢复暂停中的 live Change。

用户已在核对真实截图识别结果、账户勾稽及 Council 规划输出后，明确批准本 Change 通过验收并同步归档；批准记录见 `reviews/development/refine-unified-portfolio-intake-approval.md`。该批准不代表 ETF/Options Research、真实研究链路或候选版本晋升通过。
