# 开发控制面

本仓库实现仅供研究建议使用的组合投研系统。默认用中文沟通和编写文档；代码标识符、模型名及协议字段保留英文。

## 适用范围与入口

- 开发任务不充当 CIO；产品分析仅在有效组合输入与 `portfolio-council` 调用下应用 [product/AGENTS.md](product/AGENTS.md)，不执行开发归档、Git 提交或推送。
- 行为变更使用 OpenSpec：先 propose/update，再显式 apply；实施前阅读当前 Proposal、Specs、Design、Tasks。运行工具入口为 `python3 -m product.runtime.cli`，新 LLM 运行复用 `nested-codex-smoke`，不另造编排后端。
- 实施、验收或归档时读取 [开发流程](docs/development/workflow.md)；配置、路径、权限或启动排障时读取 [开发环境](docs/development/environment.md)；实际运行/重放/Eval 时读取 [运行手册](reviews/runtime/runtime-replay-eval-runbook.md) 的对应章节。无关专项文档不必全部加载。

## 职责边界

- LLM 组件可以开展研究、解释、形成 Thesis、质疑证据、分析冲突并综合决策。
- Python 组件可以获取和标准化数据、执行数学计算、核算组合、实施明确的硬风险约束、验证契约并持久化产物。
- 禁止将主观投资判断编码为确定性评分或大型条件规则引擎。
- 禁止增加券商接入、订单路由、账户修改或其他真实交易能力。
- 开发 Agent 只能为已授权的实现任务编辑本仓库，不继承产品运行时 CIO 权限。
- 保留用户已有修改；产品运行时指令集中在 `product/`，学习优化输出只能是提案，不得自动修改生产文件或版本指针。

## 完成标准与安全

- 所有承载事实的契约都必须包含 `source_id`、`as_of` 和 `retrieved_at`。
- 所有运行时能力都必须包含 Input、Tool/Data、Skill/Reasoning、Structured Output 和 Eval。
- 候选版本必须锁定模型、Skill、Agent、Schema、MCP Adapter、Risk Policy 和数据版本。
- 每次实现一个能力纵向切片，按任务验证后才勾选完成。迭代先聚焦测试，复用仍适用的证据；晋升前必须通过 OpenSpec、完整确定性测试、Eval/Regression、架构评审及人工批准。Change 完成不代表 Promotion PASS。
- 测试/复核必须保护源码并允许指定产物和临时目录写入；实际权限不足即报告最小授权需求，不自动提权或关闭沙箱。配置存在和事后 hash 均不能代替权限或实际加载证明。
- 禁止提交凭据、私人会话数据库及无关用户消息；发现疑似敏感信息、未审阅变更或校验失败时停止相关发布并报告。
- 仅开发收尾：每次 Change 成功归档后，按已批准范围提交归档、主规格同步及相关实现并推送至 `https://github.com/dannyCaiHaoming/stock_agent.git`；校验失败、测试失败或敏感信息未处理时不得推送。详见开发流程。
