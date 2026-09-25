## Why

MRVL 冻结运行中有个股日线、却没有 SPY 基准，准备阶段未形成技术计算产物；Technical Agent 仍把四条无依据的“无法判断”写成 Claims，最终被 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 拒绝。另一份基准完整的 MRVL 运行已经证明正常计算引用路径可用，因此需要修复缺资料分支，并明确计算成功但图表失败时的降级边界，而不是放松引用校验。

## What Changes

- 对 `TECHNICAL_STRUCTURE` 明确三种输入结果：缺基准导致无 calculation 时，生成 `INSUFFICIENT_EVIDENCE`、`claims=[]` 与指明缺口/影响的合法报告；个股与基准齐备时，保留有真实 `calculation_refs` 的技术研究。
- calculation 已成功、仅图表生成失败时，保留有效计算及其 Claims，只记录 chart 缺口；不得把计算成功误报为资料不足或整个技术任务失败。
- 用聚焦契约检查和真实宿主样本验证两种资料分支，区分任务执行 `SAVED`、报告充分性和研究包 `coverage.status`：缺 SPY 且无 calculation 时，即使合法报告已保存，报告及 coverage 仍须为 `INSUFFICIENT_EVIDENCE`，不得展示 `TECHNICAL_STRUCTURE COMPLETE`；`PARTIAL` 仅用于报告 `sufficiency`，不新增 coverage 状态。不把 8/8 已保存等同于 8/8 有实质研究。
- 不增加数据源、跨 run 补入 SPY、Python 投资判断、Agent 拆分、Schema 大版本或另一套运行入口。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `multi-dimensional-holding-research`：技术结构在缺基准、有完整计算、以及计算成功但图表失败三种情况下的报告、引用与缺口语义。

## Impact

主要影响技术任务准备和分派说明、技术图表降级、`ResearchDimensionReport` 的现有引用校验及其聚焦测试；保持 Macro/Market、Company、Skeptic、CIO、Evidence Gate 与历史产物不变。验收复用冻结 MRVL 输入及已有基准完整样本；真实产品运行仍通过现有宿主 launcher。
