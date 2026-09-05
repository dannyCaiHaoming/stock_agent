# 开发控制面

本仓库实现一个仅供研究建议使用的组合投研系统。开发 Agent 负责构建和验证产品，在开发任务中不得充当投资决策者。

## 工作流程

- 行为变更必须使用 OpenSpec。实现前先阅读当前 Proposal、Specs、Design 和 Tasks。
- 每次实现一个完整的能力纵向切片；只有通过任务声明的验证后才能将任务标记为完成。
- 保留用户已有修改，并将生产运行时指令集中放在 `product/` 下。
- 迭代期间运行聚焦测试；晋升前运行完整的确定性测试和 Eval 门禁。
- 每次 OpenSpec Change 成功归档后，必须将该次归档、主规格同步及相关实现变更提交到 Git，并推送至 `https://github.com/dannyCaiHaoming/stock_agent.git`。若校验失败、测试失败或发现疑似敏感信息，则不得推送，必须先向用户报告。

## 职责边界

- LLM 组件可以开展研究、解释、形成 Thesis、质疑证据、分析冲突并综合决策。
- Python 组件可以获取和标准化数据、执行数学计算、核算组合、实施明确的硬风险约束、验证契约并持久化产物。
- 禁止将主观投资判断编码为确定性评分或大型条件规则引擎。
- 禁止增加券商接入、订单路由、账户修改或其他真实交易能力。
- 开发 Agent 只能为已授权的实现任务编辑本仓库，不继承产品运行时 CIO 权限。

## 评审与晋升

- 所有承载事实的契约都必须包含 `source_id`、`as_of` 和 `retrieved_at`。
- 所有运行时能力都必须包含 Input、Tool/Data、Skill/Reasoning、Structured Output 和 Eval。
- 候选版本必须锁定模型、Skill、Agent、Schema、MCP Adapter、Risk Policy 和数据版本。
- 晋升必须通过 OpenSpec 校验、确定性测试、Eval/Regression、架构评审，并保留人工批准记录。
- 学习优化输出只能是提案，不得修改生产文件或版本指针。
