# 当前交接与历史读取清单

本清单是 Task 1.2 的实现定位，不是通过证明。`W` 表示当前可新写入，`R` 表示历史只读；正/负例是必须保留或补齐的测试，不表示已经执行。规格标题见 `design.md` 第 8 节。运行时技术身份、hash、路径和执行事件由确定性层拥有；模型只拥有主张、反证、解释、引用选择、决策/评分语义。

| 问题 | 当前生产者 → 消费者与写入/读取边界 | 对应规格 | 正例 / 负例 | 验证层级 |
|---|---|---|---|---|
| H01/H08 | 资料准备 `research_materials_stage`、普通股 `common_stock_stage`、八维 `multidimensional_stage`、Skeptic `independent_skeptic_stage`、CIO `smoke_prompt`/`predecision_cio_stage`、两类 Eval `common_stock_eval`/`runtime_eval` → `codex_hook_recorder`/各自报告接收器（W）；旧完整稿 → 对应验证器（R） | 当前语义草稿区分模型判断与技术装配 | 各角色语义稿可装配 / 错 invocation、模型、字段不被修正 | 逐入口 producer→consumer 确定性接缝；真实加载另列 |
| H02 | Gate Evidence 与任务允许集 → `multidimensional_references`/各报告引用解析（W）；旧完整 ID 报告保持只读（R） | 引用选择任务限定且不可模糊修复 | 允许短 ID 精确解析 / 跨任务、过期映射、伪短 ID 拒绝 | 引用与闭包接缝 |
| H03 | 上游正式报告及版本 → 下游依赖 Claim 解析（W/R） | 引用选择任务限定且不可模糊修复 | 指明报告版本的 Claim / 跨报告同名裸 ID 歧义拒绝 | 依赖报告接缝 |
| H04 | 实际文档对象及元数据 → 研报选择装配与正式 `documents`（W/R） | 当前语义草稿区分模型判断与技术装配 | 选已准入文档且原值保真 / 伪文档、版本漂移拒绝 | 资料→研究报告接缝 |
| H05 | `fixture_math.calculate` 收据及事件 → Hook、`research_submission`、报告计算（W/R） | 派生计算选择成功结果；先结构后血缘 | 有序 ratio 的真实成功收据 / 字段错、未知、输入错、篡改事件分别拒绝 | 工具→草稿→报告接缝；首错见 `implementation-evidence.md` |
| H06 | `research_materials_stage` 查询/工具事件 → 检索审计与资料选择（W/R） | 材料CIO及Eval审计来自真实记录 | 已执行成功/失败查询分别留痕 / 未执行查询不得自报成功 | 工具日志→资料准备接缝 |
| H07 | `research_submission.submit` 保存的具体稿版本 → `resolve`/Hook Stop（W）；旧回执仍按旧协议读取（R） | 提交回执精确绑定且不复制hash | 同任务精确短回执 / 旧版、跨任务、错稿、并发误选拒绝 | 提交→Stop接缝 |
| H09 | fixture Council 与 `predecision_cio_stage` 报告目录、实际交付/读取事件 → CIO 产物和 Risk 前输入（W/R） | 材料CIO及Eval审计来自真实记录 | 必需报告真实消费且模型作选择 / 仅授予却未读、漏必需报告拒绝 | 双 CIO 接缝；Risk保持原规则 |
| H10 | 两类 Eval 的冻结输入、rubric、模型事件 → `common_stock_eval`/`runtime_eval` 结果（W/R） | 材料CIO及Eval审计来自真实记录 | 评分理由保留且身份自动装配 / 错 rubric、错模型、改分拒绝 | Eval producer→result接缝 |
| H11 | 已存首稿及定位反馈 → 同一 Agent 局部修订 → 完整验证（W） | 原Agent局部纠正有限并复验 | 仅声明路径变化 / 非授权字段变化、二次失败后继续拒绝 | 修订→重新提交接缝 |
| H12 | `product/version-manifest.json` 批准组件版本 → profile、Agent/Skill镜像及真实调用锁（W）；旧锁不回写（R） | 当前组件版本单一批准来源 | 显式派生幂等 / CIO 3.1.2 与 3.1.0 等漂移拒绝 | 配置只读检查及启动锁接缝 |
| H13 | `hashing`/各对象生产者 → Hook、报告、Memory、历史读取器（W/R） | hash对象口径及历史算法 | 同版本规范对象/文件hash可复算 / 空白、键序、自身字段、非有限数误混拒绝 | 序列化测试向量与生产者→消费者接缝 |
| H14 | `research_memory` Fact/获取观察 → Gate/Research View 与历史查询（W/R） | Memory事实身份与观察/Gate视图分离 | freshness仅变视图且观察可追溯 / value内同名键、修订、歧义回绑拒绝 | Memory 临时库接缝，不改历史库 |
| H15 | 当前草稿/工具入参/CIO/Eval Schema → 各写入验证器（W）；已登记旧版本读取器（R） | 先结构后血缘且约束生效 | 组合关键字及 NO_TRADE null / 0、未知关键字、非法实参于副作用前拒绝 | Schema适配器与各入口参数接缝 |
| H16 | 冻结产物包 → Memory/网页、研究与CIO历史 source-inputs 读取（R）；当前执行单独校验资源（W） | 冻结读取与当前执行准入分离 | 移动完整包仍可读 / 缺依赖、越界路径、当前配置漂移拒绝 | 临时副本历史读取与执行准入测试 |
| H17 | `holding-research-inputs`/`research_input_topology` dataset路由 → `multidimensional_stage`、`research_consumption_audit`（W/R） | 当前数据路由及消费状态共享权威映射 | 多对多能力和实际查询/引用分别计数 / 未知映射不得默认为COMPANY | 路由→任务上下文→coverage接缝 |
| H18 | CLI进程结果、Hook任务结果、来源状态、独立内容复核 → 中文报告、`product/web`、下游（W/R） | 研究结果区分进程、契约、来源与内容 | 部分保存如实展示 / exit0+失败或未复核不得READY | 终态投影与展示接缝 |
| H19 | `dev_architect`/`dev_contracts`/`dev_reviewer`/`dev_eval` 配置及Skill → 开发交付；OpenSpec当前义务 → Reviewer（开发面） | 角色方法任务分层；历史失败分离 | 角色/方法/任务各归其处 / 固定样本污染常驻指令、旧失败当PASS拒绝 | 配置解析、实际交付和独立差异复核 |

当前共享修改保护：`complete-eight-dimension-source-consumption` 继续暂停，其来源覆盖、最低研究内容、最终同批 8/8 属于原 Change；本清单只修交接。其它脏工作区变更未经归属核对不提交、不覆盖。`H01/H08` 的历史读取是仅验证旧产物，不表示仍可将旧协议作为当前写入入口。任何真实模型补验均需另按 Task 6.4 的预算与授权执行。
