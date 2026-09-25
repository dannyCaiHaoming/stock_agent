## ADDED Requirements

### Requirement: 正反交接包必须通过显式独立阶段进入研究级 CIO
系统 SHALL 提供 `PREDECISION_CIO_SYNTHESIS` 阶段，从经过重新验证的 `PreDecisionResearchPackage`、绑定的来源 Handoff 和显式研究请求启动。本 Change 只发布 `RESEARCH_SYNTHESIS`；该阶段 MUST 拒绝 `PORTFOLIO_ADVICE` 请求，不得自动降级后假称已完成建议。阶段 MUST 使用新 run_id 和仓库外独立输出目录，保留 source_run_id、package_hash、源请求及新请求身份。原独立反证阶段的停止点、`complete_portfolio_decision=false` 和源产物 MUST 保持不变。CIO SHALL 由现有宿主入口下的 Codex 主线程执行，不新增 CIO 子 Agent 或第二套编排器。

#### Scenario: 用户研究已清仓的 MRVL
- **WHEN** 用户指定历史合格 MRVL 交接包并明确请求 CIO 研究综合
- **THEN** 新阶段在独立运行中综合原截止点的正反研究，标注当前持仓适配未评估，不要求用户提供新的账户截图或把 MRVL 伪装为现持仓

#### Scenario: 请求本阶段未发布的持仓建议
- **WHEN** 调用方选择 `PORTFOLIO_ADVICE`
- **THEN** 宿主在模型前明确拒绝该级别，不产生持仓动作、Risk 通过或建议文件

#### Scenario: 只运行研究阶段
- **WHEN** 用户仅请求多维研究或独立反证
- **THEN** 原阶段仍停止于研究产物，不自动调用 CIO 或 Risk，也不因缺少决策报告而失败

### Requirement: CIO 准备必须验证来源闭包与时点
系统 MUST 验证源交接包及其 forward bundle、逐股反证、执行证明、完整 coverage、原始报告引用和内容哈希，要求 `consumability=DOWNSTREAM_READY`。CIO 输入 MUST 绑定相同来源 Handoff、portfolio hash、decision_cutoff 与 Gate；源研究 run_id 与新 CIO run_id MUST 分别保留，不改写源报告身份。CIO MUST 只能查询该冻结 Gate 允许的 Evidence，不得获得原始缓存、其他运行或未来事实。承载事实的输入 MUST 保留 source_id、as_of、retrieved_at。旧研究包在新运行中的使用 MUST 明确为原研究截止点的综合，不能标记为当前行情或当前持仓判断。

#### Scenario: 资料篡改或报告来自另一批研究
- **WHEN** 任一报告 hash、证券身份、Gate、cutoff、执行证明或组合绑定不匹配
- **THEN** 系统在 CIO 前报告 `FAILED_VALIDATION`，保留具体错误，不启动模型且不生成建议性 NO_TRADE

#### Scenario: 历史报告不冒充当前研究
- **WHEN** MRVL 的来源 cutoff 早于实际生成时间
- **THEN** 报告分别展示两个时间，说明判断适用于来源 cutoff，不把新价格与旧结论拼接

### Requirement: CIO 阶段必须区分来源失败与研究不确定性
系统 SHALL 按下列范围处理缺口：身份、hash、引用或执行证明错误导致 FAILED_VALIDATION，不得降级发布；正向包未就绪或适用 Skeptic 为 INSUFFICIENT_EVIDENCE、TIMEOUT、缺失或失败时，沿用源包不可下游消费的限制，阻止本阶段；合法完成的 LOW_CONFIDENCE 以及辅助维度的数据不足、不适用、未覆盖 SHALL 保留给 CIO 解释影响。当前账户现金、仓位、ETF 或期权能力不构成本研究级调用的输入前提，也不得据此生成账户适配或完整组合建议。包的 DOWNSTREAM_READY MUST 与逐资产、逐维度 coverage 一起检查，不能代表组合决策就绪。必需上游任务执行失败不得当作普通数据限制。

#### Scenario: 当前账户持有 ETF 和期权但 MRVL 已清仓
- **WHEN** 用户只请求冻结来源包的 MRVL 非动作研究
- **THEN** 系统不要求当前完整账户 Risk 输入，不裁剪历史或当前持仓来制造建议，报告明确账户适配未评估

#### Scenario: 合格交接包有实质性研究不确定性
- **WHEN** 完整性校验和上游就绪规则通过但报告保留置信度限制
- **THEN** CIO 接收真实限制，自主解释其对研究判断的影响，不用 NO_TRADE 代替不确定性

#### Scenario: Skeptic 本身尚未完成研究
- **WHEN** Skeptic 返回 INSUFFICIENT_EVIDENCE 而交接包仅为 STRUCTURALLY_CONSUMABLE
- **THEN** 本阶段列出未完成研究项并停止，不将其与辅助维度信息缺失混同，也不强制修改上游 readiness

#### Scenario: 辅助维度合法受限
- **WHEN** 合格交接包的某个辅助维度为合法资料不足或不适用，且没有必需任务执行失败
- **THEN** CIO 保留限制并解释其是否改变判断；不能把无资料描述为无风险，也不由程序强制投资结论

### Requirement: 研究级成功检查必须核对宿主进程结果
`check-predecision-cio` 在返回成功 PASS 前 MUST 读取既有 `invocation/process-result.json`，确认运行身份与 Request/Trace 相同，`process_exit_code` 为整数 0、`timed_out` 为布尔 false、`failure_code` 为 null、`stage_status=COMPLETED_RESEARCH_SYNTHESIS` 且与 Trace 终态一致、`source_integrity_unchanged` 为布尔 true。缺文件、缺必需字段、非法类型、失败值或身份/状态矛盾 MUST 拒绝成功；不得仅凭报告及 `turn.completed` 认定宿主运行成功。该检查 SHALL 复用现有文件与检查器，不增加独立证明服务；既有模型、版本、Evidence 和同源报告校验保持有效。

#### Scenario: 有研究报告但缺进程结果
- **WHEN** 报告、Trace 和模型事件存在，而宿主进程结果缺失或必需字段缺失
- **THEN** 事后检查拒绝 PASS，保留原始文件，不自动启动模型或补造成功证据

#### Scenario: 宿主失败与研究终态矛盾
- **WHEN** 进程结果表明非零退出、超时、源码变化或失败原因非空，或运行身份/终态不一致
- **THEN** 事后检查拒绝成功，即使研究报告本身符合 Schema

#### Scenario: 合格进程与研究证据一致
- **WHEN** 宿主进程结果满足成功条件，且原有版本、模型、来源、引用及报告检查均通过
- **THEN** 事后检查返回研究级 PASS，仍不代表 Risk、回测或 Promotion 通过

### Requirement: 源码保护验收必须准确表达有限保证
本阶段 SHALL 保留原生沙箱，将模型可写工作区放在仓库外，不将源码目录纳入可写根，并沿用现有受保护产品文件的执行前后完整性检查；发现变化 MUST 阻止成功发布。验收 SHALL 记录实际命令、执行证据及宿主完整性结果，并明确受保护文件清单的范围。全进程 OS 强制只读 SHALL 保持 `UNVERIFIED`，不是本 Change 的完成前提；命令配置、前后 hash 相同或一次路径拒写均 MUST NOT 被解释成运行期间所有进程从未写入源码的证明。本 Change 不新增权限探针平台或额外外层沙箱。

#### Scenario: 宿主完整性证据满足有限保证
- **WHEN** 仓库外工作区与原生沙箱配置正确，宿主结果及原有完整性校验通过，但没有全进程 OS 拒写证明
- **THEN** 可按本阶段有限保证验收，明确保留 OS 强制只读未验证的限制，不要求额外权限工程

#### Scenario: 受保护产品文件发生变化
- **WHEN** 宿主执行前后的受保护产品文件完整性不一致
- **THEN** 启动器拒绝成功发布，事后检查不得把失败的完整性结果认证为 PASS

### Requirement: 新 CIO 阶段必须通过真实 MRVL 研究级验收
Change 验收 MUST 从宿主入口对合格 MRVL 交接包完成真实 CIO 研究综合，证明多维正向报告和独立反证、只读 Evidence 查询、主线程身份、模型及锁定指令版本和最终同源内容。研究级路径 MUST 有非持仓、缺当前账户输入仍可交付且禁止动作字段的聚焦测试。已通过的旧 MRVL 真实研究运行只可复用未受实现和版本锁变化影响的证据；本轮收敛入口后须对受影响路径补一次真实宿主 Smoke 与独立内容复核。模拟资料或固定草案 MUST NOT 替代真实消费证据。实现完成 MUST 经独立只读复核和人工批准；本次不要求完整组合建议、固定动作、市场收益或晋升 PASS。

#### Scenario: MRVL 已不在当前持仓
- **WHEN** 来源包来自过去持有 MRVL 的时点，而当前已清仓
- **THEN** 真实验收只检查正反研究综合的证据、内容和边界，不要求或伪造持仓动作及 Risk

#### Scenario: 实际运行只完成准备
- **WHEN** 没有可信 CIO 模型消费及查询证据
- **THEN** 验收保持未完成，不把输入文件存在或进程退出成功当作消费证明
