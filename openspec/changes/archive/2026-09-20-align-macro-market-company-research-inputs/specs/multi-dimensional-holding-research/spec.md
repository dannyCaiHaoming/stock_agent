## MODIFIED Requirements

### Requirement: 宏观市场研究必须共享事实并连接持仓
系统 SHALL 在同一 decision cutoff 下分别形成 `MACRO_CONTEXT` 与 `MARKET_STATE` 两项共享研究输出。`MACRO_CONTEXT` MUST 覆盖适用的利率、通胀、经济活动与政策环境，区分观察期、发布时间和修订版本；`MARKET_STATE` MUST 覆盖适用的大盘、风格、波动、信用或流动性状态，并区分市场事实、解释和不确定性。两项输出 SHALL 分别说明对各持仓的具体传导路径、假设和反向情景，MUST NOT 将宏观判断或市场状态转换为确定性择时规则，也不得把共享叙述冒充公司事实。

#### Scenario: 多只普通股共享宏观环境
- **WHEN** 同批次有多只普通股且两项 capability 均具备合格输入
- **THEN** 系统各生成一份共享报告，各股分别解释敏感性；原始共享资料不重复采集，Macro 与 Market 的覆盖和缺口可独立核对

#### Scenario: 宏观资料可用但市场状态资料受限
- **WHEN** `MACRO_CONTEXT` 具备合格证据而 `MARKET_STATE` 的必要快照缺失或过期
- **THEN** 宏观报告继续形成，市场报告记录准确限制，系统不把宏观完成状态复制为市场完成状态

### Requirement: 受限任务必须明确交付与延期能力
研报、所有权和期权/资金的条件任务 SHALL 分别定义可得与受限路径。可得路径 MUST 实现并验证实际研究；受限路径 MUST 保存限定尝试、原因、影响、未实现或未验证的子能力及明确责任，不能以未执行、代码错误、Change 已归档或配置存在代替。部分可得 MUST 保留已完成子能力。当前完成状态 MUST 以 SEC + Yahoo + Moomoo Singapore 数据集能力矩阵、实际 Capture → Normalize → PIT → MCP → Skill 消费证据及当前批次 coverage 为准；产品说明 MUST NOT 再把已归档 `capture-futu-client-research-data` 描述为未来延期目标，也不得把该 Change 归档解释为所有研报、13F、期权或资金行为在任意证券与 cutoff 下均可用。

#### Scenario: 只有内部人披露可得
- **WHEN** 内部人资料可用但机构可比持仓资料受限
- **THEN** 完成可用部分，单列机构子能力状态及证据，不将整个维度伪装成通过或全部不可用

#### Scenario: 已归档能力在当前批次受限
- **WHEN** 历史验收证明某数据集曾成功，但当前证券、权限或 cutoff 下无法取得合格输入
- **THEN** 系统保留历史能力证明并将当前覆盖标记为 SOURCE_LIMITED、PARTIAL 或准确失败状态，不引用已归档 Change 代替本次 Evidence

#### Scenario: 用户接受受限子能力延期
- **WHEN** 已保存限定来源尝试、具体失败、影响及明确责任，且用户接受本次受限结果
- **THEN** 条件任务可按 `SOURCE_LIMITED_ACCEPTED` 或等价状态收尾，但对应 capability 仍不得标记为 `RESEARCH_VALIDATED`

## ADDED Requirements

### Requirement: 当前多维草稿与报告必须遵守一致的结构契约
系统 MUST 为当前草稿和正式报告使用一致的权威嵌套结构定义，并锁定实际使用的契约版本/hash；历史版本仍按其原契约读取。系统 MUST 在派生计算、渲染与正式保存之前完整校验字段结构，另行执行身份、来源、PIT 和证据闭合校验。仅在 invocation 中声明 output_schema 不构成原生强制输出约束的证明，系统 MUST 核实实际生效边界并保留执行端校验。

#### Scenario: 草稿包含缺失或错误类型的嵌套字段
- **WHEN** claims 缺 question、data_gaps 缺 impact、limitations 项为对象或草稿含不允许的顶层字段
- **THEN** 系统在正式报告保存之前返回明确错误码、字段路径与预期结构，不产生原始 KeyError，不将草稿标记为有效报告

### Requirement: 多维输出纠正必须有界且由原 Agent 执行
可纠正的输出契约错误 SHALL 将原草稿、锁定契约与具体错误反馈给原 Agent/原会话；每任务初次提交后 MUST 最多允许一次纠正，重派不得重置预算。系统 MUST 保留原始输出、纠正输出及关联记录，并对纠正结果重跑完整校验。Python 或父线程 MUST NOT 代写研究判断或引用、静默删改主张以通过校验；缺失的实质内容只能由原 Agent 根据本次冻结资料补充。身份错配、越权引用、来源与时点违规 MUST 准确失败，不得伪装为纯格式纠正。原会话不可续接、超时或纠正仍失败 MUST 形成明确终态。

#### Scenario: 首次输出结构错误而原 Agent 纠正成功
- **WHEN** 首次草稿被结构校验拒绝，原 Agent 在一次纠正预算内提交新草稿并通过全部校验
- **THEN** 系统保存两次提交的追踪证据，仅将有效正式报告用于依赖任务，且冻结输入和身份绑定不变

#### Scenario: 纠正预算耗尽或发生不可纠正错误
- **WHEN** 纠正后仍非法、原会话无法续接或检测到身份错配及越权引用
- **THEN** 系统记录准确失败并结束该任务，不无限重试、不新建 Agent 绕过预算，也不将实现错误记为 SOURCE_LIMITED

### Requirement: 依赖任务必须按有效报告与明确终态推进
系统 MUST 仅在上游正式报告通过完整校验后解锁下游；纠正中不得提前认定成功或终态失败。上游最终失败 MUST 使依赖任务形成可追溯的 dependency-blocked 终态，独立任务继续执行，父线程不得无限等待缺失报告。调度终态齐全、报告结构可消费、报告有效与核心材料已消费 MUST 分别判断。

#### Scenario: Company 基础研究纠正期间有等待中的研报任务
- **WHEN** FUNDAMENTAL_EVENT 首次提交失败且仍在一次纠正预算内
- **THEN** RESEARCH_REPORT 保持等待；只有有效报告保存后才启动，若最终失败则记录 dependency-blocked，Macro 与 Market 不受该依赖阻塞

#### Scenario: 全部任务已结束但仍有非法报告
- **WHEN** 启动器或调度流程完成，而某任务输出无效或被依赖阻塞
- **THEN** 系统保留逐任务失败，不以 STRUCTURALLY_CONSUMABLE 或进程成功声明研究全部通过

### Requirement: 宏观市场能力拆分必须版本化并保持历史可读
新运行 MUST 使用包含 `MACRO_CONTEXT` 与 `MARKET_STATE` 的新版报告、研究包、stage 和 dispatch 契约，不得继续写入新的 `MACRO_MARKET` 报告。历史 `MACRO_MARKET` 报告和 `holding-research-bundle/1.1.0` MUST 继续按其锁定版本读取和校验；系统 MUST NOT 将一份历史合并报告自动复制成两份已验证的新能力报告。跨版本纳入新研究包时 MUST 显式标记兼容来源、实际覆盖和未拆分限制。

#### Scenario: 创建新的多维研究运行
- **WHEN** 当前入口准备新的研究任务集合
- **THEN** 任务、输出 schema 与 coverage 分别包含 `MACRO_CONTEXT` 和 `MARKET_STATE`，且不产生新的 `MACRO_MARKET` 任务

#### Scenario: 读取历史合并报告
- **WHEN** 消费方打开锁定旧 schema 的历史 `MACRO_MARKET` 产物
- **THEN** 旧产物仍可验证和展示，但只标记为历史合并覆盖，不自动满足新版两个 capability 的完成条件

### Requirement: 三域验收必须证明资料增量和受限边界
本次验收 MUST 在同一确认 Handoff/cutoff 下证明三域核心资料获取与真实研究消费，至少包含新增政策正文、市场新闻/跨资产输入，以及自动发现、去重并具有可核实正文定位的 issuer/IR 公司材料。核心项缺证据 MUST 保持未完成。独立研报全文与专有资料属于增强项；在限定来源验证后仍受限时 MUST 保存候选、失败、影响与具体覆盖，并仅在人工明确接受后按受限项收尾。公司 IR 不得冒充独立研报，但可在通过正文身份、去重和引用闭合后满足 Company 核心材料消费；新闻摘要和安装成功不能替代任何正文。已有证据只有在输入、实现版本及契约仍适用时才能复用，不要求重跑无关研究。

#### Scenario: 只有结构更新而无新增资料
- **WHEN** 三域任务和报告 schema 已通过测试，但未取得新增政策、市场和公司材料
- **THEN** 系统只能报告工程实现进度，不能判定三域信息能力补齐

#### Scenario: 独立研报正文确实受限
- **WHEN** 免费来源的有界真实尝试已结束，只有摘要或公司 IR，且用户明确接受该缺口
- **THEN** 该专项保留受限状态及影响，不宣称独立研报能力通过；其他核心项仍须真实闭环

#### Scenario: 当前版本的 Company 依赖链接受验收
- **WHEN** 完成确定性失败样例验证与宿主入口的 Company 依赖链验证，再进行同批三域验收
- **THEN** FUNDAMENTAL_EVENT 和 RESEARCH_REPORT 使用同一 Handoff/Gate/cutoff 与当前实现绑定，后者真实消费并引用去重后的 issuer 正文，逐股保存定位证据；单任务成功、跨批次报告拼接或结构可读均不替代该证明

#### Scenario: 验收中其他维度仍有引用失败
- **WHEN** INDUSTRY_COMPARISON 等任务仍出现证据闭合失败
- **THEN** 本次引入的回归必须修复并验证；声称既有且无关须提供可比基线与影响分析，保留失败状态且不得豁免核心项或宣称全包成功，独立复核核对该结论
