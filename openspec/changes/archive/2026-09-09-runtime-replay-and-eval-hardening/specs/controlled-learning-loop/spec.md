## ADDED Requirements

### Requirement: Promotion Gate 必须直接消费真实验证产物并执行安全硬门禁
候选版本的 Promotion Gate MUST 直接读取版本锁、确定性测试结果、Runtime Regression、Artifact/Execution Replay、Runtime Eval、Ablation 和统一 Trace Integrity 报告，并输出机器可读 `promotion/PASS` 或 `promotion/FAIL` 及稳定 reason codes。Evidence Closure、PIT Leakage、Risk Bypass、Schema/Trace 完整性、必须 NO_TRADE 案例和关键版本缺失 MUST 是不可被平均质量分抵消的硬门禁；人工填写的 candidate 摘要不得代替底层真实产物。

#### Scenario: 平均质量高但存在 Risk bypass
- **WHEN** 候选的平均语义评分高于阈值，但任一适用真实运行形成 CIO 草案后绕过 Risk Engine
- **THEN** Promotion Gate 输出 `promotion/FAIL` 和 `RISK_BYPASS`，不允许平均分覆盖失败

#### Scenario: 候选完整通过
- **WHEN** 确定性测试、Regression 硬不变量、Trace、Replay、Eval、必要 NO_TRADE 案例和预先声明的 Ablation/成本政策全部通过
- **THEN** Gate 输出 `promotion/PASS`，列出全部输入产物 hash、候选与基线版本、软指标和已知限制

#### Scenario: 只有静态候选报告
- **WHEN** Promotion Gate 无法从候选摘要解析到完整且通过验证的真实 run、Regression、Ablation 和 Eval 产物
- **THEN** Gate fail closed，并列出缺失证据，不接受摘要中的布尔通过声明

#### Scenario: 上游摘要声称通过但底层证据失败
- **WHEN** 任一上游 `status`、`PASS` sentinel 或 `configuration_equivalent` 声称成功，但重新读取底层 Trace、Evidence Closure、PIT、Risk lineage、Replay、Eval 或测试原始结果时发现不一致
- **THEN** Promotion Gate 以底层重验结果为准输出 `promotion/FAIL`，并保留可定位的验证错误

#### Scenario: 注入安全负例
- **WHEN** 测试分别在底层产物中真实注入悬空 Evidence、未来信息、Risk 绕过、Trace 缺失、配置漂移或测试断言失败
- **THEN** 六类负例均必须被对应硬门禁拒绝，不得仅通过修改摘要状态来模拟失败

### Requirement: 语义校准必须证明独立 dev_eval 执行
语义校准的重复评分 MUST 来自独立 `dev_eval` 会话，并保存 session ID、执行事件、模型、Prompt hash、输入输出 hash、起止时间、评分产物和原始 rollout hash。Calibration Runner MUST 重放验证这些绑定，同一案例的两次评分复用同一 session 或只有静态评分 JSON 时 MUST fail closed。

#### Scenario: 两次评分 JSON 自洽但来自同一会话
- **WHEN** 两份评分输出均满足 Schema 和人工标签范围，但 execution proof 显示相同 `dev_eval` session ID
- **THEN** Calibration 失败并报告会话不独立，不得将 JSON 自洽视为重复执行证明

### Requirement: Promotion PASS 不得自动修改生产系统
`promotion/PASS` SHALL 只表示候选满足自动门禁，不得修改生产 Skill、Agent、Schema、Risk Policy、默认版本指针或插件发布状态。实际晋升 MUST 继续由开发控制面记录人工批准、旧/新版本、评估证据、时间和回滚条件；`promotion/FAIL` MUST 保留失败报告并禁止晋升。

#### Scenario: 自动门禁返回 PASS
- **WHEN** 候选生成有效的 `promotion/PASS`
- **THEN** 系统保持生产文件和版本指针不变，等待独立人工批准与 Promotion Record

#### Scenario: Ablation 未显示多 Agent 增益
- **WHEN** 当前 Change 未新增 Agent，完整 Council 的 Ablation 结果为 `NO_MEASURABLE_GAIN` 但没有安全退化
- **THEN** Gate 必须公开该结果并按预先声明的候选政策处理，不得伪造增益；只有候选涉及新增或默认启用 Agent 时，预先声明的增益阈值才是强制晋升条件

#### Scenario: 候选新增 Agent 但无增益
- **WHEN** 未来候选拟新增或默认启用 Agent，且真实 Ablation 未达到预先声明的留出集增益阈值
- **THEN** Promotion Gate 输出 `promotion/FAIL`，即使其他平均指标改善也不得启用该 Agent

### Requirement: Promotion 决策必须可审计、可重复并保留基线
每次 Promotion Gate 运行 MUST 使用唯一 gate ID，锁定候选版本、当前已批准基线、Regression Set、Rubric、模型、Ablation Profile 和所有输入报告 hash，并保存人类可读报告。相同输入的确定性硬门禁 MUST 给出相同结果；软评分变化、缓存复用、跳过案例和成本预算 MUST 被显式呈现，失败记录不得覆盖或删除。

#### Scenario: 候选与基线版本不明
- **WHEN** Promotion 输入缺少候选或已批准基线的完整版本锁
- **THEN** Gate 输出 `promotion/FAIL` 和版本缺失原因，不允许以“当前工作区”作为隐式版本

#### Scenario: 重新检查相同候选
- **WHEN** 操作者以相同候选、基线和已验证输入产物重复执行 Promotion Gate
- **THEN** 确定性门禁与最终 reason codes 一致，并在新记录中引用原结果而不覆盖历史记录
