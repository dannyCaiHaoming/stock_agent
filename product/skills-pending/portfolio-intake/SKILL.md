---
name: portfolio-intake
description: 当用户通过持仓截图或手工文字提供美股普通股、ETF、上市期权及账户资金信息时，统一提取可见事实、集中澄清并在一次明确确认后生成中立 PortfolioHandoff v3；不开展证券研究、不生成投资动作，也不自动启动 portfolio-council。
metadata:
  version: "1.0.0"
---

# Portfolio Intake

本 Skill 是投资委员会之前唯一的输入能力。目标是把用户提供的完整账户状态转成可审计的 `PortfolioDraft v3`，经用户一次明确确认后生成中立的 `PortfolioHandoff v3`。股票、ETF、期权、现金、可用资金、购买力和保证金信息都在一个 Skill 中处理，不创建按资产拆分的 Intake Agent。

Handoff 只保存账户与持仓事实。本次研究问题、期限、benchmark、Mandate 和全持仓研究范围由后续独立 `CouncilRequest` 承载；改变研究请求不会改变 Handoff 或要求重新确认持仓。本 Skill 不是投资 Agent，也不判断买卖、估值、置信度、研究优先级或下游能力状态。

## 输入方式

- 截图：直接使用 Codex 原生图片理解读取可见内容。禁止调用 Python OCR，禁止根据版式、盈亏或常识补猜不可见字段。
- 手工输入：接受任意数量的美股普通股、ETF 和上市期权持仓；数量不得人为设置上限。
- 修订：将用户后续明确纠正作为新的 `USER_CORRECTION` 来源追加，保留旧来源并重新计算 `draft_hash`。

真实截图、原始附件、完整账户号以及含私人持仓的 Draft/Handoff 必须保存在仓库外的运行目录。账户引用仅保留脱敏形式。合成样例可以保存在仓库中。

## 截图提取规则

先读取 [结构化契约说明](references/contracts.md)，再生成符合 `product/schemas/intake/portfolio-draft-v3.schema.json` 的结构化观察并交给确定性入口计算 hash。历史 v2 文件仅供显式只读验证，禁止将旧对象静默改写为 v3。

可见行必须先分类为 `ACCOUNT_TOTAL`、`ASSET_CLASS_SUBTOTAL`、`POSITION` 或 `CASH_BALANCE`。只有 `POSITION` 生成持仓；总计、小计和现金行用于账户快照及确定性勾稽。无法分类的行保留为未解决项，不得猜成 Position。

每个字段必须标记以下状态之一：

- `EXTRACTED`：截图中清晰可见；
- `USER_SUPPLIED`：用户明确输入或纠正；
- `MISSING`：来源中没有该值；
- `AMBIGUOUS`：存在至少两个可能值；
- `CONFLICTING`：不同来源给出不一致值。

所有已识别事实必须具有字段级 lineage，并引用 `source_id`；每个来源必须包含 `as_of`、`retrieved_at` 与原始内容 hash。看不清时必须保留不确定性，不得静默选值。用户修订只替换对应字段的直接来源。派生值还需记录公式版本和父字段。平均成本、报价、盈亏、购买力和保证金允许缺失；现金未知不能写成 `0`。

资产必须明确区分 `COMMON_STOCK`、`ETF` 与 `OPTION`。股票和 ETF 数量单位为 `SHARE`、报价口径为 `PER_SHARE`；期权数量单位为 `CONTRACT`、报价口径为 `PER_UNDERLYING_UNIT`，并结合 `contract_multiplier` 表达整份合约市值。数量必须非零，负数按用户已有空头仓位原样保留，但不构成新增卖空授权。

每项证券保存原始代码、名称、市场、资产类型和身份状态。`AMBIGUOUS` 不得进入 Handoff。期权至少需要标的、`CALL/PUT`、到期日、执行价、合约乘数和已确认的调整状态；原始合约标识可缺失。截图只显示截断文本时，把不可见字段标记为 `MISSING`，不得根据盈亏、市值或常见乘数反推。

## 固定流程

1. 确认用户声明的范围：`BROKER_ACCOUNT` 表示完整账户，`USER_DEFINED_PORTFOLIO` 表示用户声明的完整自定义组合。
2. 从截图或文字创建 Draft。多张图逐张建立来源，检测重复证券、缺页和冲突。
3. 用中文展示账户总计、现金、可用资金、购买力、保证金、勾稽状态、身份歧义、全部持仓和所有未解决字段。把问题集中在一次消息中提出，不逐字段反复追问。
4. 用户补充后创建新 Draft。任何事实变化都会改变 `draft_hash`，此前确认自动失效。
5. 只有用户明确表示确认当前完整草稿时，才可传入 `CONFIRM_PORTFOLIO`。普通“继续”“下一步”或沉默均不算确认。
6. 生成只包含中立账户状态、完整持仓、字段级 lineage、确认和勾稽结果的 Handoff；其中不得出现研究问题、期限、能力、readiness 或研究计划。
7. 到此停止，向用户返回 Draft/Handoff 路径与摘要。不得自动创建 `CouncilRequest`，不得自动调用 `portfolio-council`。

## 硬边界

- 不新增 Agent，不委派 Company Analyst、Skeptic 或 CIO。
- 不抓取市场数据，不创建 Evidence、Thesis、动作、置信度或投资报告。
- 不接券商，不请求 API 密钥，不修改账户或下单。
- 不把“重点研究标的”解释为子集：用户输入的每一项持仓都是后续研究标的。
- 任何来源悬空、字段级 lineage 不闭合、重复证券、歧义身份、期权身份不完整、数量为零、账户缺页或确认 hash 不一致均 fail-closed。
- 接受用户已有 ETF、期权或空头持仓只表示完整保存输入，不扩大现有 Risk Policy、交易权限或研究能力。
- `BROKER_READ_ONLY_API` 与 `BROKER_STATEMENT` 只是预留来源类型，不表示已经接入 Tiger 或其他券商，也不得触发凭据请求或网络连接。
- 账户截图中的报价、市值和盈亏只用于确认与勾稽，不是研究 Evidence。
