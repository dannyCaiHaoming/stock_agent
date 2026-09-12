## Why

现有 Agent Package 已能演示 Portfolio → Specialist → CIO → Risk 的数据流，但用户仍需预先准备内部持仓文件。下一步应让用户通过截图或手工描述直接形成可确认、可追溯并能交给 `portfolio-council` 的标准组合输入。

## What Changes

- 新增 `portfolio-intake` Skill，统一处理一张或多张截图、手工输入和纠正；它只整理持仓事实，不研究股票或提出投资动作。
- 只保留两个核心产物：允许缺失、歧义和冲突的 `PortfolioDraft`，以及包含最终用户确认和 Council 输入的 `PortfolioHandoff`。
- 用户一次性确认当前 Draft hash 后才能生成 Handoff；任何后续修改均使确认失效。
- Portfolio Schema 不设置持仓数量业务上限。用户输入的每一项普通股、ETF 或上市期权持仓都是重点研究标的，Handoff 使用 `research_scope: ALL_INPUT_POSITIONS`，不得截断、抽样或要求另选 1–3 只。
- Intake 使用可辨别的资产契约表示 `COMMON_STOCK`、`ETF` 与 `OPTION`；期权保留标的、方向、到期日、执行价、合约乘数、合约标识和带符号数量，截图字段被截断时必须等待用户补充而不是猜测。
- 区分 `BROKER_ACCOUNT` 与 `USER_DEFINED_PORTFOLIO`；完整性针对用户声明的组合范围，而不是一律要求证明整个券商账户完整。
- 大组合未来可以分批、有限并发研究，但所有输入持仓必须进入研究计划；未处理项必须显式保留，不能生成“全部完成”的结果。
- 截图由 Codex 原生图片理解能力按 Skill 指令提取，不建设 OCR 服务或 Python 视觉判断系统；不确定字段集中向用户澄清一次。
- Handoff 转换为版本化的多资产 Council 输入并声明每项所需研究能力；本 Change 只验证输入与交接，不声称现有 Company Analyst/Risk 已支持 ETF 或期权，也不启动真实研究链路。
- 真实截图、账户标识和私人持仓只保存在仓库外；测试仅使用合成数据。

## Capabilities

### New Capabilities

- `portfolio-intake`：定义截图/手工持仓摄取、Draft、来源与不确定性、一次确认、声明范围及 Council Handoff。

### Modified Capabilities

- `portfolio-council-orchestration`：接受已确认 Handoff，并保证所有输入持仓都是后续研究对象；允许透明分批但禁止数量上限和静默遗漏。
- `deterministic-portfolio-risk`：要求核算与 Risk 使用用户确认的完整声明组合，不得使用截断或抽样集合。

## Impact

预计涉及新的产品 Skill、Draft/Handoff Schema、最小确定性校验、Plugin Skill 发现配置、合成截图与手工样例、聚焦测试和中文说明。输入层增加 ETF 与期权表示，但不新增 ETF/Options Agent、Tiger/券商 API、行情 Provider、OCR 后端、研究数据、下单能力或发布级验证平台，也不放宽现有 Risk Policy。

暂停中的 `us-equity-live-advisory-slice` 保持原任务和未提交修改；本 Change 不恢复其研究链路，也不依赖其未归档 live Schema。
