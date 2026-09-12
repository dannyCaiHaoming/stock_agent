# refine-unified-portfolio-intake 限定验收记录

## 验收范围

本记录仅验证统一多资产输入、`PortfolioDraft/Handoff v3`、历史 v2 显式只读兼容、独立 `CouncilRequest` 和 `planning_only` Council 接缝。没有启动产品 LLM、研究 Agent、真实行情、Risk、Replay、Regression、Calibration、Ablation 或 Promotion Gate。

实现源码快照标识：`cb8f861fac4fb6c8112ce401c05f653746a390323bb06e25362ddbbed709c976`。

历史文件保持不变：

- `portfolio-draft/2.0.0` Schema：`30cb9695c76fb289a4068ac67543830609b0d03f8f93250229d315499f1d6c34`
- `portfolio-handoff/2.0.0` Schema：`339f6b8961858e4ea42c10eb69234560e954c0e3a984d92e727a916fdb9135b5`
- 历史 v2 服务：`505db3a8d847c6703fb1d3eb8e2843d10b95127872705fbc83f5e746ab626033`

## 确定性测试

执行命令：

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_portfolio_intake tests.test_product_config tests.test_governance
```

结果：`54 tests / PASS`。

覆盖范围：

- v3 默认契约、v2 显式校验、未知版本和混合字段拒绝；
- 现金零值、负值、未知值和账户金额字段分离；
- 股票/ETF 的 `SHARE`、Long/Short Option 的 `CONTRACT` 和期权乘数；
- 字段级 lineage、用户修订、派生公式和悬空引用拒绝；
- 证券身份歧义、期权调整状态和预留券商来源类型；
- 总计/小计/Position/现金行分类和账户勾稽；
- 明确确认、Draft hash 失效和中立 Handoff 边界；
- `CouncilRequest` 生命周期、全持仓覆盖、能力映射和零执行规划；
- Skill、能力注册、隐私和产品边界。

执行命令：

```text
openspec validate refine-unified-portfolio-intake --strict --json
```

结果：`PASS`，问题数 `0`。

## 用户截图仓库外验证

产物目录：`/private/tmp/stock-agent-intake-v3.XMsGQb`

该目录位于仓库外，包含用户已确认截图的结构化观察和以下产物；仓库内未保存真实持仓明细或账户金额：

| 产物 | SHA-256 |
|---|---|
| `portfolio-draft-v3.json` | `45f3725d00a4c66cff85e0656ff345f5220fc54e83438147f63092ca49125580` |
| `portfolio-handoff-v3.json` | `d39645f3d2df6f9cc0e9379c4060ff027b20e28065fa850b4798fb77e155b28b` |
| `council-request.json` | `0e7bdb7590d8c082fc8d820787601408f109c938f568d733376caee8d7687e8c` |
| `research-plan.json` | `0e18c18e0c34b3d553e5f5ac9f9727a09bfe3f439dcc8c734d7c475eb2ad66bf` |

验证结果：

- 3 只普通股、1 只 ETF 和 1 份空头 Put 共 5 项 Position，未设置数量上限；
- 账户总计、股票小计、期权小计和现金行未重复生成 Position；
- 期权数量、报价口径、乘数和带符号市值相互独立；
- 截图未显示的可用资金、购买力和保证金字段保持未知；
- 账户勾稽状态为 `RECONCILED`；
- Handoff、Request 和 Plan 的 Handoff/Portfolio hash 保持一致；
- Council 侧生成 `etf-research` 和 `options-research` 能力缺口；
- `agent_invocations=0`、`llm_invocations=0`，没有 Thesis、动作、Risk 结果或投资报告。

## 完成状态

Task 1.1–5.3 已完成。Task 5.4 仍等待用户明确人工完成批准；该批准只表示本 Change 实现完成，不代表 ETF/Options Research、多资产 Risk 或候选版本晋升已经完成。
