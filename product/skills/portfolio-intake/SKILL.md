---
name: portfolio-intake
description: 当用户通过持仓截图或手工文字提供美股普通股、ETF 或上市期权组合时，提取可见事实、集中澄清并在一次明确确认后生成 PortfolioHandoff；不开展证券研究、不生成投资动作，也不自动启动 portfolio-council。
metadata:
  version: "1.0.0"
---

# Portfolio Intake

本 Skill 是投资委员会之前的输入能力。目标是把用户提供的完整组合转成可审计的 `PortfolioDraft`，经用户一次明确确认后生成 `PortfolioHandoff`。它不是投资 Agent，也不判断买卖、估值、置信度或研究优先级。

## 输入方式

- 截图：直接使用 Codex 原生图片理解读取可见内容。禁止调用 Python OCR，禁止根据版式、盈亏或常识补猜不可见字段。
- 手工输入：接受任意数量的美股普通股、ETF 和上市期权持仓；数量不得人为设置上限。
- 修订：将用户后续明确纠正作为新的 `USER_CORRECTION` 来源追加，保留旧来源并重新计算 `draft_hash`。

真实截图、原始附件、完整账户号以及含私人持仓的 Draft/Handoff 必须保存在仓库外的运行目录。账户引用仅保留脱敏形式。合成样例可以保存在仓库中。

## 截图提取规则

先读取 [结构化契约说明](references/contracts.md)，再生成符合 `product/schemas/intake/portfolio-draft.schema.json` 的结构化观察并交给确定性入口计算 hash。

每个字段必须标记以下状态之一：

- `EXTRACTED`：截图中清晰可见；
- `USER_SUPPLIED`：用户明确输入或纠正；
- `MISSING`：来源中没有该值；
- `AMBIGUOUS`：存在至少两个可能值；
- `CONFLICTING`：不同来源给出不一致值。

所有已识别事实必须引用 `source_id`，每个来源必须包含 `as_of`、`retrieved_at` 与原始内容 hash。看不清时必须保留不确定性，不得静默选值。成本字段允许缺失；现金未知不能写成 `0`。

资产必须明确区分 `COMMON_STOCK`、`ETF` 与 `OPTION`。数量必须非零，负数按用户已有空头仓位原样保留，但不构成新增卖空授权。期权至少需要标的、`CALL/PUT`、到期日、执行价和合约乘数；原始合约标识可缺失。截图只显示截断文本时，把不可见字段标记为 `MISSING`，不得根据盈亏、市值或常见乘数反推。

## 固定流程

1. 确认用户声明的范围：`BROKER_ACCOUNT` 表示完整账户，`USER_DEFINED_PORTFOLIO` 表示用户声明的完整自定义组合。
2. 从截图或文字创建 Draft。多张图逐张建立来源，检测重复证券、缺页和冲突。
3. 用中文展示全部持仓、现金、时间、范围和所有未解决字段。把问题集中在一次消息中提出，不逐字段反复追问。
4. 用户补充后创建新 Draft。任何事实变化都会改变 `draft_hash`，此前确认自动失效。
5. 只有用户明确表示确认当前完整草稿时，才可传入 `CONFIRM_PORTFOLIO`。普通“继续”“下一步”或沉默均不算确认。
6. 生成 Handoff 及全持仓前置研究计划。`research_scope` 固定为 `ALL_INPUT_POSITIONS`；每个 position 恰好出现一次。分批只控制未来并发，不得截断或选择焦点子集。普通股、ETF、期权分别声明 `company-research`、`etf-research`、`options-research`；当前 Package 缺少专业能力时输出 `CAPABILITY_GAP` 并停止，不得把 ETF/期权交给 Company Analyst 冒充覆盖。
7. 到此停止，向用户返回 Draft/Handoff 路径与摘要。不得自动调用 `portfolio-council`。

## 硬边界

- 不新增 Agent，不委派 Company Analyst、Skeptic 或 CIO。
- 不抓取市场数据，不创建 Evidence、Thesis、动作、置信度或投资报告。
- 不接券商，不请求 API 密钥，不修改账户或下单。
- 不把“重点研究标的”解释为子集：用户输入的每一项持仓都是后续研究标的。
- 任何来源悬空、重复证券、无法识别资产、期权身份不完整、数量为零、账户缺页或确认 hash 不一致均 fail-closed。
- 接受用户已有 ETF、期权或空头持仓只表示完整保存输入，不扩大现有 Risk Policy、交易权限或研究能力。
