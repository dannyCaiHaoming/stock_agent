# Portfolio Intake v3 结构化契约

## 对象边界

`PortfolioDraft v3` 是可修订的账户观察；`PortfolioHandoff v3` 是用户确认后的中立账户状态；`CouncilRequest` 是另一次生命周期中的研究请求。Intake 只生成前两个对象，不生成 Research Capability、计划或投资结论。

历史 `portfolio-draft/2.0.0` 和 `portfolio-handoff/2.0.0` 只允许显式只读验证，不自动迁移或重算 hash。

## PortfolioDraft v3

结构化图片观察以 `product/schemas/intake/portfolio-draft-v3.schema.json` 为准，至少包含：

- `draft_id`、声明范围和完整性；
- 脱敏 `account_ref`；
- 来源的 `source_id/source_type/as_of/retrieved_at/content_hash`；
- `account_snapshot`：账户类型、净值、证券市值、现金、可用资金、购买力和保证金字段；
- 逐行分类结果；
- 任意数量的普通股、ETF 和上市期权 Position；
- 未识别资产、未解决字段、报告总计与勾稽结果。

字段观察统一采用：

```json
{
  "value": "AAPL",
  "status": "EXTRACTED",
  "source_refs": ["source-screenshot-1"],
  "candidates": [],
  "note": null
}
```

`MISSING` 的值和来源为空；`AMBIGUOUS`/`CONFLICTING` 必须保留至少两个候选和直接来源。用户修订新增 `USER_CORRECTION` 来源，并改变 Draft hash。

行类型为 `ACCOUNT_TOTAL`、`ASSET_CLASS_SUBTOTAL`、`POSITION`、`CASH_BALANCE`。只有 `POSITION` 创建持仓。不能分类的行保留为 `row_type: null` 并进入集中澄清。

## Position 单位与身份

- 股票、ETF：`quantity_unit=SHARE`、`quote_unit=PER_SHARE`。
- 期权：`quantity_unit=CONTRACT`、`quote_unit=PER_UNDERLYING_UNIT`。
- 期权市值使用 `quantity × quote_price × contract_multiplier` 的账户口径；例如 `-1 × 0.66 × 100 = -66 USD`。
- `average_cost_price`、`quote_price`、带符号 `market_value`、`unrealized_pnl_amount` 和 `unrealized_pnl_percent` 含义相互独立。
- 身份状态为 `OBSERVED | USER_CONFIRMED | RESOLVED | AMBIGUOUS`；Handoff 不允许歧义身份。
- 期权保留标的、CALL/PUT、到期日、执行价、乘数、原始合约标识和调整状态。

账户展示报价、市值和盈亏是输入快照事实，不是研究 Evidence。

## PortfolioHandoff v3

Handoff 只在完整范围、明确现金、非零数量及单位、非歧义身份、完整期权身份、来源闭合和当前 Draft hash 已明确确认时生成。可用资金、购买力、保证金、平均成本、报价、市值和盈亏允许未知，但必须列入 `unknown_fields`。

Handoff 保存：

- 完整 `account_snapshot` 和所有 Position；
- 来源与字段级 `field_lineage`；
- 派生值的公式、版本、父字段与来源；
- 报告总计和 `RECONCILED | UNRECONCILED | NOT_EVALUATED` 勾稽结果；
- Draft/Portfolio/Handoff hash 和确认记录。

Handoff 禁止包含研究问题、期限、研究范围、benchmark、Mandate、Research Capability、readiness、研究计划、Evidence、Thesis、动作或订单字段。

## CouncilRequest 与规划接缝

用户另行发起研究时，Council 创建独立 `CouncilRequest`，用 `handoff_id/handoff_hash/portfolio_hash` 绑定 Handoff，并承载研究问题、期限、`ALL_INPUT_POSITIONS`、benchmark、Mandate 和可选约束。

Council 的确定性规划接缝根据资产类型产生能力映射和缺口。输出必须标记 `planning_only: true`、覆盖全部持仓，且 `agent_invocations=0`、`llm_invocations=0`。它不获取 Evidence、不生成 Thesis、动作、Risk 结果或报告。

## 确定性入口

```text
python3 -m product.intake.cli manual-draft ...
python3 -m product.intake.cli draft ...
python3 -m product.intake.cli correct ...
python3 -m product.intake.cli summary ...
python3 -m product.intake.cli confirm ... --explicit-confirmation CONFIRM_PORTFOLIO
python3 -m product.intake.cli validate-handoff ...
python3 -m product.intake.cli validate-handoff ... --schema-version v2
python3 -m product.intake.cli council-request ...
python3 -m product.intake.cli validate-council-request ...
python3 -m product.intake.cli council-plan ...
```

这些命令只执行结构、来源、hash、确认和规划校验，不调用 LLM、专业 Agent、Risk 或产品研究链路。
