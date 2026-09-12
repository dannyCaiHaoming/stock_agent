# Portfolio Intake 结构化契约

## PortfolioDraft

Draft 是可修订、尚未授权进入研究链路的组合事实集合。字段定义以
`product/schemas/intake/portfolio-draft.schema.json` 为准。

结构化图片观察必须提供：

- `draft_id`、`portfolio_scope`、`portfolio_complete`；
- 脱敏后的 `account_ref`；
- 含 `source_id/source_type/as_of/retrieved_at/content_hash/external_ref/synthetic/coverage_status` 的来源；
- `portfolio_as_of/base_currency/cash`；
- 任意数量的 `positions`；每项包含 `ticker/market/asset_type/quantity/cost_basis/option_contract`；
- 无法识别的资产及其来源。

每个事实字段采用：

```json
{
  "value": "AAPL",
  "status": "EXTRACTED",
  "source_refs": ["source-screenshot-1"],
  "candidates": [],
  "note": null
}
```

不确定字段的 `value` 必须为 `null`。`AMBIGUOUS` 或 `CONFLICTING` 必须保留至少两个 `candidates` 和相关来源。`MISSING` 不得把猜测值放入 `value`。

`asset_type` 仅接受 `COMMON_STOCK`、`ETF`、`OPTION`。股票和 ETF 的 `option_contract` 必须为 `null`；期权必须提供字段包装后的 `underlying_ticker/option_type/expiration_date/strike/contract_multiplier/contract_symbol`。前五项是确认 Handoff 前的必填身份，`contract_symbol` 可保持 `MISSING`。数量为带符号非零数值，负数表示用户已有空头仓位。

## PortfolioHandoff

Handoff 只在 Draft 没有阻断性未解决字段、组合范围完整且用户明确确认当前 `draft_hash` 后生成。它必须：

- 保留 `draft_id/draft_hash` 和确认时间；
- 固定 `advisory_only: true`；
- 固定 `research_scope: ALL_INPUT_POSITIONS`；
- 包含全部已确认持仓和现金；
- 用 `portfolio_hash` 绑定 Risk 前置输入；
- 为每个持仓生成且只生成一个研究计划项；
- 为普通股、ETF、期权分别声明 `company-research`、`etf-research`、`options-research`；
- 当当前 Package 缺少对应专业能力时输出 `council_readiness: CAPABILITY_GAP`，不丢弃资产或伪装成完整 Council。

计划中的 `batch_size` 只描述未来如何分批。它不得改变总数、删除后序持仓或形成“重点标的”子集。

## 确定性入口

```text
python3 -m product.intake.cli draft ...
python3 -m product.intake.cli manual-draft ...
python3 -m product.intake.cli correct ...
python3 -m product.intake.cli summary ...
python3 -m product.intake.cli confirm ... --explicit-confirmation CONFIRM_PORTFOLIO
python3 -m product.intake.cli validate-handoff ...
python3 -m product.intake.cli risk-input ...
python3 -m product.intake.cli council-input ...
```

这些命令只做结构、来源、hash 和确认校验，不调用 LLM，也不启动 Council。
