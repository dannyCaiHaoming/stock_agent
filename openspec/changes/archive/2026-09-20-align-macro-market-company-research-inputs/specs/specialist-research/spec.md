## ADDED Requirements

### Requirement: Company、Macro 与 Market 必须映射到现有专业职责
当前持仓研究 SHALL 通过版本化拓扑把 Company 域的公司基本面、公司事件与公开研报能力绑定至 Company Analyst，把 `MACRO_CONTEXT` 与 `MARKET_STATE` 绑定至 Market Catalyst。两项 Market Catalyst 能力 MUST 使用独立 invocation、capability-specific 输入和结构化输出，即使它们复用同一 Agent 定义或 Skill 包；Company Analyst MUST NOT 以公司报告替代宏观或市场状态研究，Market Catalyst MUST NOT 把共享环境解释冒充公司 Thesis。provider 只负责资料语义与可用性，不成为新的研究 Agent。

#### Scenario: 同一 Market Catalyst 执行两项能力
- **WHEN** 一个运行同时派发 `MACRO_CONTEXT` 与 `MARKET_STATE`
- **THEN** 两次 invocation 分别锁定 capability、输入、输出和执行证据，任一失败不伪造另一项完成

#### Scenario: 公司资料包含宏观评论
- **WHEN** Company Analyst 的来源包含管理层对利率或行业环境的评论
- **THEN** 报告可将其保留为公司视角及相关 Evidence，但不能据此声称共享 `MACRO_CONTEXT` 或 `MARKET_STATE` 已完成

#### Scenario: 页面新增一个研究栏目
- **WHEN** 产品展示新增或重命名一个研究栏目但没有新的独立判断职责和可测增益证据
- **THEN** 系统通过已有 capability/Agent 映射展示，不新增默认 runtime Agent

### Requirement: 研究材料必须按研究对象分派
研报与新闻 SHALL 作为材料类型而不是固定 Agent 归属。公司研报归 Company Analyst；宏观与市场策略材料分别进入 Market Catalyst 的 `MACRO_CONTEXT` 与 `MARKET_STATE` 输入。系统 MUST 对相关材料执行相同的来源核实、正文解析、PIT 和引用闭合；仅标题摘要不得视为已读正文，IR 公司宣传不得冒充独立研究，机构预测不得冒充已发生事实。

#### Scenario: 同批取得公司研报与宏观策略
- **WHEN** 资料准备取得两类有可验证正文与发布时间的材料
- **THEN** 分别按研究对象进入对应 invocation，报告引用原始材料并保留观点属性，不把全部研报固定交给 Company Analyst
