## Context

参见 [proposal.md](proposal.md)。当前 Package 有通用 Portfolio、Mandate 和 Risk 契约，但用户仍需准备内部文件。首版 Intake 必须保持 LLM-native，同时避免把简单输入流程扩建成状态平台。暂停中的 live Change 有三只持仓临时限制，本设计不复用该限制。

## Goals / Non-Goals

**Goals:**

- 截图或手工输入经过一次集中确认后形成可表示普通股、ETF 与上市期权的 Council-ready Handoff。
- Portfolio 不设持仓数量业务上限，所有输入证券都是研究对象。
- LLM 负责图片理解，Python 仅负责数据校验、规范化和持久化。
- 大组合允许透明分批，不允许截断或隐式遗漏。

**Non-Goals:**

- 不接 Tiger 或其他券商 API，不获取研究 Evidence。
- 不新增 Intake Agent、OCR 后端或工作流平台。
- 不启动真实 Analyst、Skeptic、CIO、Replay、Regression 或 Promotion。
- 不恢复或修改暂停 Change 的验收范围。

## Decisions

### 1. portfolio-intake 是 Skill，不是 Agent

当前 Codex 通过 Skill 读取附件、提取字段、集中提出澄清并展示确认摘要。它不产生独立投资观点，因此不创建新 Agent。截图使用 Codex 原生图片理解，不增加 OCR 服务；Python 不解析图片语义。

### 2. 只保留 Draft 与 Handoff

```text
Screenshot / Manual Text
          |
          v
PortfolioDraft
  - source items
  - extracted/manual fields
  - missing/conflicting fields
  - declared portfolio scope
          |
   one consolidated confirmation
          v
PortfolioHandoff
  - confirmed portfolio
  - confirmation + draft hash
  - research_scope=ALL_INPUT_POSITIONS
```

不再建立独立 Extraction、Confirmation 和 ConfirmedPortfolio 文件。Draft 保存来源、状态和修订；Handoff 内嵌最终确认及规范化 Portfolio。Draft 改动产生新 hash，旧 Handoff 自动失效。

### 3. 完整性以声明范围为准

`portfolio_scope` 支持：

- `BROKER_ACCOUNT`：用户声明输入覆盖某个账户；截图缺页时不能确认完整。
- `USER_DEFINED_PORTFOLIO`：用户声明当前输入集合就是希望研究的组合；不要求证明整个券商账户。

Risk 和最终报告必须保留该范围，不能把自定义组合说成完整账户。

### 4. 全部输入持仓都是研究对象

Portfolio Schema 不使用 `maxItems`。Handoff 固定 `research_scope: ALL_INPUT_POSITIONS`，研究集合由 `positions` 确定性派生，不另设可漂移的焦点列表。证券顺序不影响集合和 Portfolio hash 的语义。

大组合运行时可以按固定批大小和有限并发生成每证券研究任务，但必须记录总数、完成、待处理和失败。批处理是执行控制，不是产品持仓上限。任何未处理证券都会阻止“完整研究完成”终态。

本 Change 只生成并验证未来研究计划，不实际启动这些任务。

### 5. 来源、不确定性和用户修订保留在 Draft

每个来源记录 `source_id`、`source_type`、`as_of`、`retrieved_at`、内容 hash 和外置引用。字段状态至少包括 `EXTRACTED`、`USER_SUPPLIED`、`MISSING`、`AMBIGUOUS`、`CONFLICTING`。用户修订新增来源，不覆盖截图提取。

所有缺失和冲突一次性汇总；用户只确认一次完整摘要。现金未知与零严格区分，成本可选。截图中的价格或市值只是账户快照信息，不能冒充后续市场 Evidence。

### 6. Handoff 使用多资产 Portfolio 边界

Handoff 提供证券、带符号数量、可选成本、现金、币种、Mandate/benchmark、期限、研究问题、声明范围与来源。`COMMON_STOCK` 与 `ETF` 使用市场和 ticker 身份；`OPTION` 使用标的、CALL/PUT、到期日、执行价、合约乘数与可选原始合约标识。Draft 可以保留期权字段缺失或歧义，Handoff 只接受身份完整的合约。

输入层允许记录用户已有的空头期权，因此数量只禁止零，不再把所有负数量当作非法。该事实不改变现有 long-only Mandate：Intake 接受现状不代表 Council 可以建议新增空头或 Risk 已能计算衍生品。

交接器输出一个包含全部证券的 Council 前置计划，用于证明每项输入都有后续研究槽位，并按资产类型声明 `company-research`、`etf-research` 或 `options-research`。它不创建 Thesis、Evidence 或动作；缺少专业能力时计划显式停止，不能降级成只覆盖普通股。

### 7. 私人数据只在仓库外

真实附件、Draft 和 Handoff 写入用户指定的外置运行目录。仓库只保存合成截图、Schema、Skill 和测试。账户引用脱敏，日志不记录完整账户号、凭证或原图文本。

### 8. 限定验收

使用确定性测试验证 Draft、hash、一次确认、声明范围、任意数量持仓、全量研究计划、Handoff、完整 Risk 输入和隐私。再使用一张合成截图直接调用一次 `portfolio-intake` Skill，证明原生图片理解到 Handoff 的产品交互；流程到此停止，不启动研究 Council。

## Risks / Trade-offs

- [图片识别错误] → Draft 显示来源与不确定字段，用户集中确认后才生成 Handoff。
- [用户输入规模很大] → 交接不设业务上限；未来执行使用透明分批和有限并发，永不静默截断。
- [自定义组合并非完整账户] → 强制记录 `portfolio_scope`，Risk 与报告限定解释范围。
- [期权截图标识被截断] → 保留可见字段，将执行价或合约标识标记为不确定，等待用户集中确认。
- [输入支持超前于研究能力] → Handoff 保留全部资产并标注所需能力；Council 缺少对应 Skill 时 fail closed，不冒充完成。
- [与暂停 Change 文件重叠] → 使用独立 Intake 文件；无法按 hunk 安全分离时停止并报告。

## Migration Plan

1. 添加独立 Skill、Draft/Handoff Schema 与显式 Intake 入口，不改变现有 Council 默认行为。
2. 增加 Handoff 和全持仓研究计划的确定性接缝，但不启动研究。
3. 后续 Tiger 只读适配器直接输出同一 Draft，不新增第二套输入模型。

回滚时移除新增 Intake 文件与注册项即可；既有 fixture、Demo 与暂停 live 路径保持不变。
