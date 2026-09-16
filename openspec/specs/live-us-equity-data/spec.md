# 美股普通股真实数据基础规格

## Purpose

为已确认的美股普通股持仓提供免费优先、只读、可追溯且符合 point-in-time 约束的数据准备能力，并把冻结 Evidence 与结构化缺口交给下游研究 Agent 使用，而不在数据层生成投资判断。

## Requirements

### Requirement: 已确认 PortfolioHandoff 必须是唯一持仓来源
系统 SHALL 只从用户已确认的 `PortfolioHandoff v3` 派生内部普通股采集请求，不得要求用户再维护一份包含 mandate、研究问题或投资动作的 live portfolio。系统 SHALL 处理 Handoff 中的全部普通股，不得设置 1 只或 3 只产品上限。

#### Scenario: 多持仓进入数据准备
- **WHEN** 已确认 Handoff 包含任意数量的合法普通股持仓
- **THEN** 系统为每个普通股生成唯一采集项，并通过资源预算控制执行；预算耗尽的未执行项必须保留具体状态，不得静默丢弃

#### Scenario: Handoff 同时包含其他资产
- **WHEN** 已确认 Handoff 同时包含 ETF、期权、现金或账户级字段
- **THEN** 系统保留完整 Handoff 绑定，只将普通股交给本 Capability，且不把其他资产伪装成普通股

### Requirement: 真实来源必须角色明确且访问有界
系统 SHALL 使用版本化来源策略记录 provider、data role、启停状态、最小域名、请求预算、客户端/适配版本、核实状态和检查时间。NASDAQ 仅提供证券目录，Yahoo/yfinance 为非实时日线主行情，AKShare/东方财富为受控备用行情，SEC 为公司披露来源。

#### Scenario: 来源策略有效
- **WHEN** 某来源已启用且请求满足域名、预算、版本和用途限制
- **THEN** 系统允许对应只读采集并记录实际请求和响应血缘

#### Scenario: 来源拒绝或超出范围
- **WHEN** 来源返回 401、403、429、认证挑战、明确禁止，或请求超出策略范围
- **THEN** 系统停止对应访问、记录结构化失败，且不得通过重试、换源或扩大域名规避限制

### Requirement: 证券身份必须在事实进入 Gate 前核实
系统 SHALL 将 ticker 绑定到稳定 `security_id`，并核实交易所、币种、资产类型和必要股类。NASDAQ 目录只能提供候选身份；已知持仓在目录不可用时 MAY 通过 SEC 与行情来源独立核实。

#### Scenario: 已知持仓不在当前目录结果中
- **WHEN** NASDAQ 目录缺少一个用户持仓，但 SEC 和行情来源能一致核实其美股普通股身份
- **THEN** 系统继续处理该持仓并记录目录限制，不得将其自动删除或判定退市

#### Scenario: 身份来源冲突
- **WHEN** ticker、交易所、币种、股类或 SEC 发行人绑定互相冲突
- **THEN** 系统隔离该证券并报告身份缺口，不得猜测映射或生成事实

### Requirement: 每条事实必须具有完整来源和时间语义
系统 SHALL 为每条事实保存唯一 `evidence_id`、`source_id`、`as_of`、`retrieved_at`、原始内容 hash 和来源定位。披露事实还 SHALL 保存 `published_at` 及其判定策略；派生事实 SHALL 保存公式、父 Evidence ID 和父 hash。

#### Scenario: 标准化行情与披露
- **WHEN** 行情或 SEC 披露被标准化为研究事实
- **THEN** 事实包含完整来源、时间、口径和原始内容血缘，并通过 Schema 校验

#### Scenario: 缺失关键来源字段
- **WHEN** 一个候选事实缺少必需来源、时间、身份、单位或原始内容血缘
- **THEN** 系统拒绝其进入通过 Gate 的 Evidence，并记录排除原因

### Requirement: 行情必须采用单一来源选择且不得静默拼接
系统 SHALL 对每个证券和研究窗口冻结一个行情 SourceSelection。只有主源暂时性连接失败、超时、5xx 或明确无满足时效的数据时，才可对已启用备用源执行一次有界尝试；不得逐字段或逐日期拼接主备行情。

#### Scenario: 主行情可用
- **WHEN** Yahoo/yfinance 返回身份、币种、时间和口径均合格的行情
- **THEN** 系统选择主源并且不请求备用行情

#### Scenario: 允许的备用行情
- **WHEN** 主源发生策略允许的暂时可用性故障，且 AKShare/东方财富备用源独立满足全部约束
- **THEN** 系统选择备用源并保存主源失败、备用尝试和最终选择记录

#### Scenario: 完整性错误不能触发切源
- **WHEN** 主源数据存在身份冲突、Schema 异常、原文 hash 异常或 PIT 问题
- **THEN** 系统 fail-closed，且不得通过备用源掩盖该安全错误

### Requirement: 数据必须先冻结再执行 PIT Gate
系统 SHALL 在 Agent 消费事实前冻结统一 `decision_cutoff`、来源选择和候选事实，并由既有 PIT Gate 排除截止时间之后公开、获取或生效的数据。Agent 不得原地改写已冻结的来源选择或数据包；补充资料 SHALL 形成明确的新冻结产物并通过现有绑定与 PIT 规则。

#### Scenario: Future Evidence 被排除
- **WHEN** 候选事实的 `published_at`、`as_of` 或适用获取时间晚于 `decision_cutoff`
- **THEN** PIT Gate 排除该 Evidence、保存原因，且下游允许 ID 集合不包含该 ID

#### Scenario: 多持仓共享截止时间
- **WHEN** 同一 Handoff 的多个普通股完成数据准备
- **THEN** 所有证券使用相同 `decision_cutoff`，但保留各自身份、来源选择、Evidence 和缺口

### Requirement: 缓存复用和受控补充资料必须兼容
系统 SHALL 通过现有只读数据工具访问 Provider，并沿用仓库外缓存保存原获取时间、版本和原始 hash。相同有效资料 SHALL 复用；研究 Agent MAY 提出有理由的同行、基准或公开研报等补充请求，新增资料 SHALL 在冻结、PIT 和引用验证后才进入研究上下文。

#### Scenario: Agent 请求补充资料
- **WHEN** 研究提出既有缓存未覆盖的合格资料请求
- **THEN** 现有只读工具可在既定来源权限和预算内获取并冻结资料；晚于当前 cutoff 的资料不得加入当前研究包，原冻结包不得改写

#### Scenario: 多个研究消费者读取同一事实
- **WHEN** Company Analyst 和后续研究 Skill 需要相同的行情或披露事实
- **THEN** 二者读取同一冻结 Evidence ID，且不会产生新的 Provider 请求

#### Scenario: 合格缓存被复用
- **WHEN** 缓存的身份、口径、版本、时间和时效满足当前研究要求
- **THEN** 系统复用原记录并保留最初 `retrieved_at`，不得伪装成新获取

### Requirement: 数据不足必须形成结构化缺口
系统 SHALL 对每个证券记录采集状态、通过 Evidence、排除 Evidence 和数据缺口。数据不足不得被解释成 HOLD、NO_TRADE 或其他投资动作。

#### Scenario: 单证券数据不足
- **WHEN** 一个持仓缺少合格价格、身份或必要披露
- **THEN** 系统将该证券标记为 `SOURCE_LIMITED` 或等价失败状态，说明影响，并允许其他证券的数据准备独立完成

#### Scenario: 所有来源均不可用
- **WHEN** 没有来源能提供合格事实
- **THEN** 系统输出可诊断的数据包和缺口，不生成虚构 Evidence 或投资结论

### Requirement: 冻结研究数据包必须可被下游研究消费
系统 SHALL 沿用与 Handoff hash 绑定的 Gate、data-preparation manifest、证券身份、SourceSelection、Evidence、排除记录、现有版本记录和结构化缺口。下游普通股研究入口 SHALL 能直接验证并读取该数据包，无需转换回旧 live Council 输入。结构可读 SHALL NOT 被解释为研究资料充分、研究质量通过或 DOWNSTREAM_READY；这些判断沿用下游 Capability 的现有规则。

#### Scenario: Company Analyst 接收数据包
- **WHEN** 数据准备成功且至少一个普通股具有合格 Evidence
- **THEN** 普通股研究阶段能按 `security_id` 获取允许 Evidence 和缺口，并保持所有引用闭合

#### Scenario: 数据包被篡改
- **WHEN** Handoff、Gate、来源选择、Evidence、版本或 manifest hash 不一致
- **THEN** 下游消费在 Agent 启动前确定性失败

### Requirement: 私有数据与运行产物必须留在仓库外
系统 SHALL 将真实持仓、SEC 联系信息、Cookie、凭证、原始响应、缓存和运行包保存到显式仓库外目录。可提交的样例和验收摘要不得包含私人持仓或认证材料。

#### Scenario: 保存公开验收摘要
- **WHEN** 开发者整理数据能力验收记录
- **THEN** 记录只包含合成输入、脱敏标识、命令形态和必要 hash，不包含真实持仓、Cookie、凭证或原始私有数据

### Requirement: 数据层不得生成投资判断
系统 SHALL 只输出事实、派生计算、来源冲突和数据缺口，不得生成 Thesis、反证结论、confidence、HOLD、TRIM、EXIT、NO_TRADE 或组合动作。

#### Scenario: 数据准备完成
- **WHEN** 一个或多个持仓的数据包已冻结
- **THEN** 终态只描述数据准备结果和可消费性，投资判断由后续 Agent 与 Risk Capability 负责
