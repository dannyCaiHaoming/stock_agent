## ADDED Requirements

### Requirement: 普通股入口保留已验证的完整 Company 配置
`COMMON_STOCK_RESEARCH` SHALL 使用原完整 `runtime_company_analyst` 配置及其版本/hash，保持同一 Agent 身份、只读权限与原必需研究 Skills。未通过质量验收的精简 Profile MUST NOT 被默认入口加载。准备、隔离副本与启动 MUST 绑定同一实际选择配置；文件缺失、权限/身份/技能集合错误或 hash 漂移 MUST 在既有错误路径拒绝，不静默选择实验文件。其他 Company 模式 SHALL 保持原完整配置与工具边界。

#### Scenario: 普通股默认研究配置
- **WHEN** 为新的普通股研究准备并启动调用
- **THEN** 清单、隔离配置及宿主角色选择均指向原完整 Company 配置；实验 Profile 的存在或内容不影响默认选择，运行 Agent 名称不变

#### Scenario: 完整配置损坏或绑定漂移
- **WHEN** 所选完整配置缺失、无效或与准备绑定不符
- **THEN** 拒绝启动，不回退到未验收的实验配置

#### Scenario: 历史报告与其他模式
- **WHEN** 读取旧报告或执行其他 Company 模式
- **THEN** 沿用原版本语义和契约，不迁移或改写历史运行；旧 prepared run 的绑定漂移继续拒绝

### Requirement: 普通股字段查询必须完整且受当前授权范围约束
`COMMON_STOCK_RESEARCH` 的现有只读 `query` SHALL 支持单一精确 `semantic_field` 或原 `evidence_ids` 二选一；空选择、两种同时指定或空字段 MUST 拒绝。新增方式仅在经验证的普通股阶段工具声明中呈现，并由服务端校验阶段、Agent、run 与 invocation；其他模式 SHALL 保留原工具声明和按 ID 的行为，并拒绝新增方式。不得新增 Agent、工具服务、编排器、模糊检索或投资指标推荐。

字段展开 MUST 仅在目标证券、Gate 允许 ID、当前 request 允许 ID 和当前普通股目录 ID 的交集内进行。成功时 MUST 返回该字段全部匹配的原始事实与原 `evidence_id/source_id/as_of/retrieved_at`、期间、主体及申报元数据，不挑选最新一期、不合并冲突或修订、不自动判断完整财年和可比性。范围内无匹配 SHALL 返回空证据，不泄露范围外事实或存在性。字段选择由 LLM 决定，事实适用性、Thesis 和估值继续由 LLM 判断；不得硬编码 MRVL、EPS 数值、固定必查字段或旧报告结论。

字段模式成功响应的 compact UTF-8 JSON MUST 不超过 65536 字节；超限 MUST 整次拒绝并说明可使用既有按 ID 查询，不返回部分事实冒充完整、不记录成功交付。旧 ID 查询原有行为不变。成功事件 MUST 在既有记录路径保存实际交付的 `evidence_ids` 与结果 hash，使原引用和计算校验继续识别真实交付事实；失败、空匹配或目录中存在都不得冒充已交付证据。冻结 Gate、Evidence、目录及报告 Schema 不变；工具声明、Adapter 版本与绑定/hash 的必要变化须单独记录。

#### Scenario: 一次读取同字段的全部获准期间
- **WHEN** 普通股 Agent 对目录中存在的字段使用 `semantic_field` 查询，匹配响应未超限
- **THEN** 返回范围内全部期间和各版本的原事实，与同集合按 ID 查询的事实一致；实际交付 ID 可被原引用校验识别，模型自行核对期间、主体与适用性

#### Scenario: 字段相同但事实不属于当前研究范围
- **WHEN** Gate 或其他 request 中存在同名字段，但事实不属于当前证券、request 或普通股目录的交集
- **THEN** 不返回这些事实、不暴露其存在性；只对交集匹配结果回答，身份或阶段非法时拒绝调用

#### Scenario: 无匹配或字段结果过大
- **WHEN** 当前范围无匹配，或完整成功响应超过 65536 字节
- **THEN** 前者返回空证据并限定当前范围，后者整次拒绝并提示既有按 ID 查询；均不能提供虚假的完整结果或成功交付引用

#### Scenario: 其他模式及旧调用继续兼容
- **WHEN** 非普通股模式使用原按 ID 查询，或调用者同时提交两种选择方式
- **THEN** 原调用继续遵守原契约；互斥违规拒绝，非普通股模式不得接受字段方式，新增能力不扩展其授权

### Requirement: 普通股工具指引须与授权和原报告契约一致
普通股 dispatch SHALL 只在本次存在冻结附件且拥有相应权限时展示附件查询入口。原始 Evidence 查询与计算不依赖附件存在。研究判断、期间和可比性解释 SHALL 继续由 Company Agent 负责；Schema、PIT 和实际交付引用校验 MUST 保留。无支撑 Claim、悬空计算和未交付事实 MUST 按原契约拒收并保存真实失败状态，不自动补写草稿或由 Python 生成投资判断。

#### Scenario: 没有冻结附件
- **WHEN** 本次 invocation 没有附件及附件查询权限
- **THEN** packet 不展示可调用的附件入口；原始事实查询和计算仍可使用，不能将附件为空解释为所有原始事实缺失

#### Scenario: 无支撑 Claim 或悬空计算
- **WHEN** Claim 不满足原 Schema 的支撑条件，或引用未交付/未在 artifact_refs 闭合的计算
- **THEN** 原校验拒收并保留草稿和失败终态，不能因进程零退出而显示研究完成

#### Scenario: 消减实验未通过
- **WHEN** 精简配置的真实报告仍有重要事实遗漏或契约失败
- **THEN** 保留原始失败结果，不能用输入字节下降或工具局部成功声称消减质量通过；经明确批准恢复完整配置也不改写旧实验结果
