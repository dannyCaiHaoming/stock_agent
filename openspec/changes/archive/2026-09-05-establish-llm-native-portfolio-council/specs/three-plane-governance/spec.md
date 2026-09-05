## Purpose

建立开发、产品运行和学习优化三套相互隔离但可审计衔接的控制边界，使研究系统的运行权限、变更权限和版本晋升责任始终明确。

## ADDED Requirements

### Requirement: 系统必须区分三个治理平面
系统 SHALL 将开发控制面、产品运行面和学习优化面定义为不同的指令域，并分别规定其可访问资源、允许操作和禁止操作。

#### Scenario: 运行时加载产品规则
- **WHEN** 用户启动一次 portfolio council 运行
- **THEN** 系统仅向运行时 Agent 应用产品运行面的指令和只读能力，不授予开发或生产修改权限

#### Scenario: 开发任务加载开发规则
- **WHEN** 开发 Agent 执行 OpenSpec、测试、评审或实现任务
- **THEN** 系统应用开发控制面规则，并将产品运行规则作为被实现和验证的契约而非开发权限来源

### Requirement: 开发与运行 Agent 必须物理区分
系统 SHALL 使用根级开发指令和 `dev_*` Agent 配置管理开发工作，并使用产品级指令和 `runtime_*` Agent 配置管理投资研究运行，二者不得共享可变生产权限。

#### Scenario: Runtime Agent 尝试修改产品
- **WHEN** runtime Agent 请求编辑 Skill、Agent 配置、Risk Policy 或程序文件
- **THEN** 系统拒绝该操作并在 Decision Trace 中记录权限违规

### Requirement: 能力必须先于 Agent 建立
任何新增 runtime Agent MUST 对应至少一个已定义完整输入、数据工具、推理方法、结构化输出和 Eval 的 Capability；系统不得仅为角色完整性创建空 Agent。

#### Scenario: 提议新增专业 Agent
- **WHEN** 开发者提议新增行业、宏观或技术分析 Agent
- **THEN** 评审必须验证其 Capability Contract 和相对现有架构的 Eval 增益，否则不得晋升

### Requirement: 生产版本必须通过人工晋升
Skill、Agent 配置、Schema、MCP Adapter 和 Risk Policy 的候选版本 MUST 经 OpenSpec、测试、回归评估和人工评审后才能成为产品运行面默认版本。

#### Scenario: 学习面提出改进
- **WHEN** 学习优化面生成 Improvement Proposal
- **THEN** 该建议保持为非生产候选，直到开发控制面完成规定的晋升流程
