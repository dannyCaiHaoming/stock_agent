## Purpose

为普通股公开基本面研究提供跨运行、追加式且可审计的长期 Research Memory，使首次研究能够有界初始化、后续研究能够按数据集增量刷新并复用已验证资料，同时保持 point-in-time、来源血缘、Company Agent 调度和失败隔离。

## ADDED Requirements

### Requirement: Research Memory 必须具有完整能力契约
系统 SHALL 以已确认普通股身份、采集计划参考时间、版本化来源/刷新政策和仓库外持久化位置为输入，由确定性数据准备层规划采集、保存和查询，不由 LLM 决定数据库写入、checkpoint 推进或 freshness。输出 MUST 至少包含逐证券 `IncrementalPlan`、采集尝试、不可变资料版本、dataset checkpoint、冻结 Research View、结构化缺口和持久化状态；验证 SHALL 覆盖 Schema、来源、三时间、身份、幂等、事务、并发、增量范围和现有 Company Agent 消费接缝。

#### Scenario: 新持仓进入持久化研究链路
- **WHEN** 已确认 Handoff 首次包含一只有效普通股且该证券没有历史 Research Memory
- **THEN** 确定性层生成有界初始化计划、保存合格资料并物化冻结 Research View，Company Agent 只读取该 View 而不直接写入或修改持久化状态

### Requirement: 长期状态和原始对象必须保存在仓库外
系统 MUST 将 Research Memory、增量状态、采集尝试、报告历史及原始公开资料缓存保存到显式仓库外位置，拒绝位于源码仓库内、符号链接逃逸或权限不满足的路径。数据库不得保存来源凭据、SEC 联系身份、用户 Cookie 或不必要的私人组合字段；原始大对象 SHALL 继续使用内容寻址缓存，持久化索引只保存必要元数据、hash 和引用。

#### Scenario: 持久化目录指向源码仓库
- **WHEN** 自动资料准备收到位于仓库内或解析后逃逸到未授权位置的 Memory 路径
- **THEN** 系统在 Provider 请求和 Agent 启动前拒绝执行，不创建临时仓库内数据库或静默改用运行目录

#### Scenario: 进程重启后再次研究
- **WHEN** 上一次运行已成功提交资料和 checkpoint，随后进程退出并重新启动
- **THEN** 新运行从同一仓库外 Research Memory 恢复状态，且不依赖仍驻留内存的索引或上一运行目录

### Requirement: 证券身份、事实和文档必须追加保存完整时间与来源版本
Research Memory SHALL 追加保存证券身份版本、标准化事实和公开文档版本，不得覆盖已提交版本。每项承载事实的记录 MUST 保留稳定标识、`security_id`、`source_id`、`as_of`、`published_at`、`retrieved_at`、来源定位、适配/Schema 版本、内容 hash 和必要期间/单位/父引用；文档 MUST 绑定 provider identity、accession/report ID 或等价稳定键及原始对象引用。系统 MUST 区分逻辑事实键、内容版本和采集观察；获取时间、响应整体 hash、行排序变化不得单独制造新事实版本。逻辑事实键包含指标、期间/交易日、单位、币种、口径和必要维度；内容版本保留来源披露身份及有效/公开时间。相同版本标识和内容 SHALL 幂等，同一版本标识内容冲突 MUST fail closed，逻辑事实的合法修订 SHALL 形成新版本。原始响应、首次合格获取时间、后续观察及既有 Evidence ID 血缘 MUST 保留，不重写历史证据。

#### Scenario: SEC 修订同一历史期间
- **WHEN** 后续申报或来源响应改变同一期间的已知事实
- **THEN** 系统追加带新公开/获取时间和来源 hash 的版本，历史版本保持可查询且 checkpoint 不把修订伪装成首次事实

#### Scenario: 重复收到完全相同的事实
- **WHEN** 两次采集产生相同稳定标识、内容和来源版本
- **THEN** 第二次提交不增加重复事实，并在采集尝试中记录幂等命中

### Requirement: 每个数据集必须具有独立 checkpoint 和采集尝试历史
系统 MUST 按 `security_id`、provider、dataset、身份/口径范围及版本化适配策略维护独立 checkpoint，至少记录覆盖范围、水位或 cursor、最后成功时间、freshness 截止、内容/策略版本和 revision。每次计划执行 MUST 追加采集尝试，区分 `SKIPPED_FRESH`、`CACHE_HIT`、`CHECKED_NO_CHANGE`、`FETCHED_INCREMENTAL`、`FETCHED_BOOTSTRAP`、`SOURCE_LIMITED`、`FAILED_VALIDATION` 和 `FAILED_PERSISTENCE` 或等价状态；没有新增数据不得与请求失败混淆。

#### Scenario: 一项数据失败而其他数据成功
- **WHEN** 某证券的 Yahoo 日线增量成功但 SEC 检查暂时失败
- **THEN** 日线 checkpoint 可以按其已提交结果推进，SEC checkpoint 保持原水位并记录失败尝试，二者不得共享一个全局 `last_updated_at`

#### Scenario: 来源检查成功但没有新内容
- **WHEN** Provider 检查完成且没有新 accession、事实或文档版本
- **THEN** 系统记录 `CHECKED_NO_CHANGE`、实际请求与检查时间，不伪造新增资料或将其标成来源失败

### Requirement: 系统必须在请求 Provider 前生成可审计 IncrementalPlan
每次自动资料准备 MUST 先读取当前 checkpoint、来源策略、`planning_as_of`、交易日历和目标证券，为每个数据集生成版本化 `IncrementalPlan`。计划 MUST 明确 `BOOTSTRAP`、`REFRESH`、`DELTA` 或 `SKIP_FRESH`、请求范围、有限重叠、待补区间、初始化范围、刷新周期、来源总预算及修复子预算、失败降级规则、计划依据和 plan hash，并在运行包中保存计划与实际结果的对应关系。计划不得由 Company Agent 在自然语言中生成或修改。

#### Scenario: 首次研究新股票
- **WHEN** 新增股票没有任何有效 checkpoint
- **THEN** 计划仅执行规格允许的有界历史初始化和当前资料获取，不递归扩展来源或无上限补齐历史

#### Scenario: 数日后再次查看持仓
- **WHEN** 股票已有成功 checkpoint 且只有最近若干交易日和一份新披露可能缺失
- **THEN** 计划复用仍新鲜资料，只为相关日线窗口、来源检查和新披露安排请求，不重新安排完整历史文档获取

### Requirement: 增量语义必须按数据集定义而非统一 TTL
系统 SHALL 为不同数据集保留版本化增量策略。日线数据 MUST 从已提交完成交易日水位附近的有限重叠窗口开始，以识别缺口和供应商修订；SEC filing 文档 MUST 依据新 accession/文档身份和内容 hash 获取，已验证旧文档不得重复下载；SEC submissions/companyfacts 或其他汇总端点如需重新读取完整响应，MUST 如实标记网络检查范围，并仅追加新增或修订的标准化记录。低频身份、当前快照和公开补充资料 MUST 各自使用适用 freshness/cursor，不得以单一“24 小时缓存”替代。

#### Scenario: Yahoo 日线已有历史水位
- **WHEN** 上次成功水位为已完成交易日且本次 cutoff 晚于该水位
- **THEN** 请求窗口从版本化有限重叠起点开始并截止于本次已完成交易日，不重新请求既定完整多年窗口；重复日期经版本和内容校验后幂等或追加修订

#### Scenario: SEC 汇总端点需要重新检查
- **WHEN** 汇总端点 freshness 到期但来源不支持所需的网络级 delta
- **THEN** 系统可以有界重读该端点，但必须区分响应下载、无变化检查、新增事实和新文档请求，不得宣称所有网络字节均为增量

### Requirement: 数据提交、checkpoint 推进和并发必须保持一致
合格事实/文档、成功采集尝试和 checkpoint 更新 MUST 在逐数据集短事务中原子提交，checkpoint 只能在对应资料成功验证并持久化后推进。Provider 请求期间不得长期持有全局写事务；同一数据集的并发计划 MUST 使用有界等待的单机进程互斥及 checkpoint revision 校验；首版采用 OS 文件锁，进程退出自动释放，不实现续租服务。重复提交 MUST 保持幂等，陈旧执行不得倒退或覆盖新水位。一个证券/数据集失败不得回滚其他已独立提交的数据。

#### Scenario: 写入事实后 checkpoint 更新失败
- **WHEN** 持久化事务不能完整提交事实、尝试记录和新 checkpoint
- **THEN** 整个数据集事务回滚或保持旧 checkpoint，下次运行仍会重新计划缺失范围，不出现已跳过但未保存的数据区间

#### Scenario: 两个运行同时刷新同一数据集
- **WHEN** 两个运行基于同一旧 revision 生成计划
- **THEN** 至多一个执行者持有有效刷新权或成功推进该 revision；后完成者重新核对状态，不能重复事实、倒退水位或覆盖已提交修订

#### Scenario: 持锁进程退出或竞争超时
- **WHEN** 执行进程退出或另一进程等待数据集锁达到政策上限
- **THEN** 已退出进程的 OS 锁自动释放；等待超时的一方记录可恢复状态而不全量抓取，后续取得锁时重新读取 checkpoint 和计划

### Requirement: 冻结 Research View 必须由持久化资料确定性物化
系统 MUST 针对当前 `security_id`、采集完成后的共同 `decision_cutoff`、来源/身份选择和数据集策略从 Research Memory 物化不可变 Research View，保存所选资料 ID、版本、三时间、数据集覆盖、缺口、冲突、checkpoint revision、策略版本和 `view_manifest_hash`。该完整性 hash MUST 与研究输入指纹分离，运行 ID、检查时间或 checkpoint revision 的变化不得单独判为研究内容变化。View 必须继续通过既有 PIT Gate、Evidence Closure 和运行包绑定；未选中的历史版本不得进入 Agent Prompt。当前 Change 只要求当前运行 View，不提供历史 Agent 重放或回测执行。

#### Scenario: 当前 View 混入未来资料
- **WHEN** 候选资料的公开、生效或适用获取时间晚于本次 cutoff
- **THEN** 资料被排除并记录原因，View 允许集合和 Gate 允许集合均不包含该资料

#### Scenario: 同一证券有多个历史版本
- **WHEN** Research Memory 保留同一事实的原始版和后续修订版
- **THEN** View 按版本化选择政策确定本次可用版本并保存选择血缘，不覆盖或删除未选历史版本

### Requirement: 只有已验证 Company Agent 报告才能进入报告历史
Research Memory SHALL 追加保存通过现有 Schema、证券/运行绑定、Evidence Closure、计算引用和禁止动作校验的 Company Agent 报告及其 View 完整性 hash、完整研究输入指纹、问题 hash、模型、Agent、Skill、Schema、策略版本和原运行引用。非法、超时或缺失报告 MUST 仅保存尝试/失败状态，不得进入有效报告索引；数据采集成功不因模型失败而回滚。

#### Scenario: Company Agent 输出无效报告
- **WHEN** 模型完成但报告存在悬空 Evidence、错误证券绑定或禁止组合动作
- **THEN** 本次资料提交仍保留，报告不进入有效历史，并记录独立的研究失败状态

#### Scenario: 报告历史写入失败
- **WHEN** 运行目录中已有通过校验的 JSON/Markdown 报告但长期报告写入失败
- **THEN** 原运行产物继续保留，持久化状态明确失败且不得把该报告当作可复用历史；已提交数据和 checkpoint 不回滚

### Requirement: 持久化层不得生成研究判断、投资动作或回测结果
Research Memory、增量计划和 View Builder MUST 仅保存、选择和呈现来源事实、文档、报告原件、覆盖及缺口，不得根据阈值生成 Thesis、confidence、组合动作、绩效、Benchmark 结论或回测结果。时间字段和不可变版本只是未来能力的数据前提，不构成本 Change 已实现回测。

#### Scenario: 资料和历史版本已足够进行后续分析
- **WHEN** 数据库包含多个时点的事实和 Company Agent 报告
- **THEN** 当前能力仍只提供持久化、增量准备和当前 View，不自动启动历史重跑、Performance、Skeptic、CIO 或任何交易策略模拟

### Requirement: 采集计划时间必须与最终研究截止时间分离
系统 MUST 在请求前使用 planning_as_of 规划范围，响应使用真实完成时间记录 retrieved_at，在本次采集结束后按现有共同 cutoff 机制冻结 View/Gate。系统不得为通过 PIT 校验伪造获取时间或将最终 cutoff 固定为采集前时间；显式历史 cutoff 不得自动推进。

#### Scenario: 新资料在采集开始后返回
- **WHEN** 新响应在 planning_as_of 之后完成且最终研究 cutoff 尚未冻结
- **THEN** 系统保留真实获取时间，在采集结束后的共同 cutoff 执行既有 PIT 校验，不因误用计划参考时间排除全部新响应

### Requirement: 无变化检查不得制造新事实或重置原始血缘
系统 MUST 在保留采集观察与原始对象关联的同时按语义内容去重，当前 live-fact 继续作为生产事实契约。新增的不同 accession、数值、期间、口径或适配语义不得被去重规则吞掉。

#### Scenario: SEC 响应排序或 Yahoo 请求窗口改变
- **WHEN** 返回的旧事实内容及披露身份未变，仅获取时间、行顺序、外层响应 hash 或请求窗口变化
- **THEN** 旧事实版本数和对应 Evidence 身份保持不变，新增观察记录指向本次原始对象，真实新增部分单独追加

### Requirement: 增量覆盖必须处理缺口和有界历史修复
checkpoint MUST 保存已验证覆盖和待补区间，不得仅以最大日期声称连续完成。拆股、复权或重叠区修订线索 MAY 触发带原因及预算的有界修复，不得默认重新请求完整历史；无法确认一致性的序列 MUST 禁止用于依赖其一致性的计算。每个 dataset 的有效默认范围、时效、预算和失败规则 MUST 按 Design 政策表版本化冻结，来源准入更严格的限制优先。

#### Scenario: 最新交易日存在但中间缺失
- **WHEN** 来源返回最近日期却漏掉一个预期交易日
- **THEN** 系统保留待补区间，下次有界补缺，不因最大日期推进永久跳过缺口

#### Scenario: 公司行动影响重叠窗口外历史
- **WHEN** 发现复权修订线索可能影响已保存窗口较早部分
- **THEN** 系统在政策限定窗口和预算内修复，或记录不一致及计算限制，不静默混用两套价格口径

### Requirement: 报告历史必须独立于原运行目录可读取及验证
系统 MUST 长期保存最小完整报告包，包括原 JSON/Markdown、请求/绑定、选中 Evidence、引用计算、附件/图形及验证所需 manifest；共享对象可通过长期内容寻址引用，不能只索引原运行路径。必要私有上下文 MUST 外置隔离且不进入公开事实查询。先发布完整对象再原子提交有效索引，重复保存 SHALL 幂等。

#### Scenario: 原运行目录不可用
- **WHEN** 报告已成功保存而原运行目录被移走
- **THEN** 历史报告仍可读取、按原始绑定验证并接受当前复用兼容性检查；对象缺失或损坏时拒绝复用

#### Scenario: 保存失败后仅补存报告
- **WHEN** 用户或恢复流程指定仍有完整原件但未成功持久化的报告
- **THEN** 系统重新执行确定性验证并幂等补存，不请求 Provider 或模型，不更改原报告身份

#### Scenario: 数据事务回滚且数据库无法记录失败
- **WHEN** 资料事务失败并且后续失败记录也无法写入数据库
- **THEN** checkpoint 保持未提交状态，运行包保留失败诊断，不宣称失败 attempt 已落库

### Requirement: 缺口与修复必须贯穿真实快照契约
系统 MUST 在采集与 Memory 边界解析生产快照中的字符串缺口，保留证券、dataset、区间、原因和无法解析的诊断；重新冻结 MUST 满足现有 snapshot Schema。pending 只能根据锁定交易日历和实际验证覆盖消除；请求成功、最大日期推进或进入修复模式不能单独证明缺口完成。

#### Scenario: 来源返回字符串形式的日线缺口
- **WHEN** 真实快照包含 JSON 字符串缺口且中间已完成交易日缺失
- **THEN** 对应 checkpoint 保存待补区间，下次计划包含有界补缺；休市日和未完成 session 不被误标为缺口

#### Scenario: 价格修订触发重新冻结但修复未完成
- **WHEN** 重叠窗口发现价格口径修订且当前预算不足或修复响应仍不完整
- **THEN** 保留修订版本及 pending，限制相关派生计算，输出符合真实 Schema 的快照和诊断；不得清空 pending 或将不一致序列当作完整数据

### Requirement: 成功 checkpoint 必须对应实际数据集结果
系统 MUST 从对应来源采集和验证结果判定成功、缓存、失败及未尝试状态，不得仅因整个快照存在或零新增事实就推进所有数据集的成功时间。逻辑请求、实际网络子请求/重试、缓存命中 MUST 区分并可从现有事件核实。数据库局部写入异常 MUST 回滚相应事务并按证券隔离；共同库不可安全使用时 MUST 明确停止批次并保留已提交成果。

#### Scenario: 可选来源失败而基础资料成功
- **WHEN** 某可选数据集刷新失败或未尝试，而其他数据集取得合格资料
- **THEN** 失败或未尝试项不推进成功 checkpoint，成功项按实际提交推进；旧资料仅按用途与时效规则使用，无法证明刷新成功时拒绝报告复用

#### Scenario: 一只股票发生 SQLite 写入异常
- **WHEN** 一只股票的数据事务抛出局部 OperationalError 或 IntegrityError，而共享库仍可安全用于其他股票
- **THEN** 该事务回滚、该证券不派发，其他股票继续；数据库失败记录也不可写时使用运行目录诊断，不将数据库错误改报为来源限制

### Requirement: 持久化完成必须具有生产契约链路证据
验收 MUST 分别证明资料入库、增量获取、报告持久化/复用及稳定宿主配置。确定性测试 SHALL 按 Design 双时点矩阵执行生产标准化、冻结、Schema、身份/PIT、Memory、Gate、prepare 和运行包验证，只在外部 transport、时钟和模型执行边界使用替身。真实数据侧验收 MUST 使用已确认 MRVL 输入和当前来源授权；没有真实数据入库证据时不得以报告复用代替整体完成。

#### Scenario: 报告表非空但事实与 checkpoint 为空
- **WHEN** 验收库仅存在有效报告，fact_versions 和 dataset_state 都为空
- **THEN** 只标记报告侧证据有效，资料入库及增量验收保持未完成，不勾选整个持久化闭环

#### Scenario: 双时点完整链路通过
- **WHEN** T0 资料入库后进程退出，T1 在同一稳定 Memory 上获取新增日线和申报
- **THEN** 断言请求范围与文档计数、版本及 checkpoint 前后差异、旧对象可解析、新 Evidence 经实际工具交付、RUN/REUSED 包及归集均符合预期，不依赖仅 Repository 单测

#### Scenario: 真实数据来源受限
- **WHEN** 当前授权、环境或来源不可用导致数据侧真实验收无法完成
- **THEN** 记录 BLOCKED 及最小缺口，保留确定性证据与旧报告证据，不追加未经授权的模型调用或把模拟运行标为真实通过
