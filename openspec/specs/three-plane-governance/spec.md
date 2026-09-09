# three-plane-governance Specification

## Purpose

建立开发、产品运行和学习优化三套相互隔离但可审计衔接的控制边界，使研究系统的运行权限、变更权限和版本晋升责任始终明确。

## Requirements

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

### Requirement: 开发指令必须按任务条件读取
根指令 SHALL 仅承载项目原则、常用入口、职责边界、完成标准、安全要求和专项文档的读取条件，默认中文并保留英文代码标识符及协议字段。流程、模型和验收细则 MUST 有明确且不重复的权威位置，不得要求所有任务完整读取全部专项文档。根指令 MUST 明确：开发自检在当前环境进行且不自动启动产品、模型或项目沙箱；真实 Smoke 与 Execution Replay 使用现有宿主 launcher；独立复核默认读取差异、规格及已有证据。底层运行模块不得被推荐为绕过宿主入口直接启动真实产品的默认方式。

#### Scenario: 普通开发与专项诊断
- **WHEN** 用户执行普通授权开发任务
- **THEN** 仅加载开发规则及该任务必需的专项内容，不因产品指令而获得 CIO 权限；仅在诊断、验收或归档等对应条件满足时读取相应细则

#### Scenario: 产品运行不触发开发收尾
- **WHEN** 用户调用产品 portfolio-council
- **THEN** 应用产品规则，不执行开发归档、Git 提交、推送或生产文件修改；保留 advisory-only、PIT、Evidence、Risk 和学习面禁止自动修改的安全要求

#### Scenario: 仅依靠根指令选择执行入口
- **WHEN** 开发者或 Reviewer 从根指令决定自检、真实产品运行或独立复核方式
- **THEN** 能明确区分当前环境确定性检查、宿主 launcher 和只读证据复核；不被引导自动启动 Council、旧 probe/preflight 或额外项目沙箱，缺少补跑授权时仅报告具体证据缺口

### Requirement: Change 验收必须依据差异限定且不替代晋升
开发流程 MUST 在验收前声明受影响范围、规格映射和证据复用依据，以版本、输入、依赖及底层执行证明判断适用性。仅对受影响且缺少有效证据的项目补测，修改加载或启动行为 MUST 提供受影响的真实 Smoke；独立 Reviewer MUST 复核实际差异与证据而非仅复述 PASS。此规则不得豁免主规格对安全与真实执行的既有要求。

#### Scenario: 未受影响证据复用
- **WHEN** 旧证据对应的能力、输入和依赖未受修改影响
- **THEN** 报告完整 hash、适用理由和局限并复用；历史 Replay/Ablation 只证明对应历史能力，不充当新候选晋升证据，不默认重跑 Calibration、Ablation、Promotion

#### Scenario: 旧 Change 已完成但不能晋升
- **WHEN** 旧 Change 获人工批准且候选为 NOT_PROMOTABLE
- **THEN** 保留两种结论，不要求旧候选 Promotion PASS 来启动下一项已授权工作；尚未完成的安全发布收尾仍须按原批准处理，不重开旧需求

#### Scenario: 发现越界或必须扩大验收
- **WHEN** 发现范围外问题、敏感信息，或现有明确规格与拟定有限验收有冲突
- **THEN** 记录对应依据与缺口并停止相关工作；先提出透明的流程调整供批准，不偷偷降低标准或自行扩展全量 Gate

### Requirement: 功能验收与隔离保证必须如实区分
经明确人工批准，日常开发与功能验收 SHALL 与全进程隔离验收分开；全进程源码强制只读 MUST 保留 UNVERIFIED 和残余风险，排除在本 Change 完成保证之外，不影响原生权限、业务安全或独立生产晋升门禁。

#### Scenario: 范围批准不是完成批准
- **WHEN** 用户批准范围调整并接受残余风险
- **THEN** 同步批准与规格，但不自动关闭其他未完成任务、提升候选、归档或发布；历史运行仅按其版本和功能范围复用
