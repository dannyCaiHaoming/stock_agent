## MODIFIED Requirements

### Requirement: 缓存复用和受控补充资料必须兼容
系统 SHALL 通过现有只读数据工具访问 Provider，沿用仓库外内容寻址缓存保存原获取时间、版本和原始 hash，并通过跨运行 Research Memory 维护证券/数据集 checkpoint、采集尝试和不可变标准化版本。每次自动资料准备 MUST 在 Provider 请求前生成确定性 `IncrementalPlan`；相同有效资料 SHALL 复用，缺失、过期、新增或修订资料 SHALL 按数据集策略有界补充。研究 Agent MAY 提出有理由的同行、基准或公开研报等补充请求，新增资料 SHALL 经持久化、冻结、PIT 和引用验证后才进入新的研究上下文；原冻结包不得改写。

#### Scenario: Agent 请求补充资料
- **WHEN** 研究提出既有 Memory 和缓存未覆盖的合格资料请求
- **THEN** 现有只读工具可在既定来源权限、数据集策略和预算内获取、追加保存并冻结资料；晚于当前 cutoff 的资料不得加入当前研究包，原冻结包不得改写

#### Scenario: 多个研究消费者读取同一事实
- **WHEN** Company Analyst 和后续研究 Skill 需要相同的行情或披露事实
- **THEN** 二者读取同一持久化资料版本和本次冻结 Evidence ID，且不会因为消费者数量产生新的 Provider 请求

#### Scenario: 合格缓存被复用
- **WHEN** 缓存的身份、口径、版本、时间和时效满足当前研究要求
- **THEN** 系统复用原记录并保留最初 `retrieved_at`，不得伪装成新获取

#### Scenario: 合格资料被跨运行复用
- **WHEN** Memory/缓存记录的身份、口径、版本、时间、checkpoint 和时效满足当前研究要求
- **THEN** 系统复用原记录并保留最初 `retrieved_at`，将其纳入新的运行级冻结 View，不伪装成新获取

#### Scenario: 数日后只需少量增量
- **WHEN** 上次研究已保存完整 checkpoint，当前只有最近交易日、新 accession 或过期快照需要更新
- **THEN** 系统按 `IncrementalPlan` 只请求相应范围和检查，不重新安排完整历史行情与旧 filing 文档获取，并保存计划与实际请求差异

#### Scenario: Research Memory 不可用
- **WHEN** 自动资料准备无法打开、迁移或验证指定 Research Memory
- **THEN** 系统在 Provider 请求和 Agent 启动前明确失败，不静默改用临时运行目录、旧 JSONL 或全量抓取

#### Scenario: 可选来源失败且历史资料仍合格
- **WHEN** 可选来源刷新失败但持久化历史披露仍满足既有身份、PIT 和用途要求
- **THEN** 系统保留原获取时间使用合格资料、显式记录刷新失败，不推进成功检查时间；必要基础 Evidence 合格则继续该证券研究，复用报告仍须另外通过当前 freshness 与完整输入等价性检查

#### Scenario: 过期快照不可继续使用
- **WHEN** 当前价格或可选快照不满足既有 Gate 时效要求且刷新失败
- **THEN** 排除过期数据并记录缺口；可选数据缺失不自动阻断其他合格研究，必要数据缺失按既有规则阻断该证券，不为继续运行放宽 Gate

#### Scenario: 新运行使用稳定外置存储
- **WHEN** 宿主 launcher 在新的运行目录启动自动资料准备
- **THEN** 使用已配置的同一 memory_root 及长期原始对象缓存，不因运行目录变化创建新的空 Memory 或全量初始化已有股票

#### Scenario: SEC 汇总刷新但已知 filing 未变
- **WHEN** submissions/companyfacts 超过刷新期，而选中的同 accession/document 身份及已验证原文对象未改变
- **THEN** 可以有界请求汇总端点，已知 filing 原文的实际网络请求数为零；保留原文 hash 和最初 retrieved_at，新 accession 才按预算获取新文档

#### Scenario: 已知文档对象缺失或损坏
- **WHEN** 持久化索引命中但原文对象无法读取或 hash 不匹配
- **THEN** 不盲目命中缓存；按有界恢复政策请求并记录原因，预算或来源不足时保留待补与失败状态，不推进完整成功状态

#### Scenario: 增量 View 引用了上一运行事实
- **WHEN** 本次响应仅含增量，而当前 View 同时选择旧事实和新事实
- **THEN** 旧事实和新事实的原始对象、来源引用均可从稳定存储解析，新运行包通过现有 Gate 及来源闭包检查，原 run_dir 不构成必需依赖
