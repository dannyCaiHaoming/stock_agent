## Why

归档状态说明（2026-10-02）：以下方案及实施时的“原八维暂停”边界保留为历史规划；原八维已另行通过自身验收并归档，本 Change 的最终状态及限定发布证据见 [archive-closeout.md](archive-closeout.md)。不追改历史预算、失败或最低研究标准。

从开发入口、数据准备到研究、CIO/Eval与历史读取，技术身份、引用、hash、版本和状态存在多处重复维护及职责混淆；八维需求的反复失败只是其中一个真实案例。本 Change 处理前述全部19类问题（11类模型交接、8类工程契约与开发方式），按优先级修复现有边界，不以减少安全校验、降低内容标准或全系统重写换取通过。

## What Changes

- 复用既有 `research_submission`、短引用、可信 Start/Stop 身份绑定和宿主 launcher，不新增 Agent、Skill、编排器或验证平台。
- 已实现且支持新写入的资料准备、普通股研究、八维、Skeptic、CIO及两类Eval入口均采用“语义草稿 → 确定性装配 → 严格校验 → 正式产物”的职责边界，分别保留各角色业务Schema；不强迫它们共用一个大报告结构。真正只读兼容的旧协议保留，不把仍可新写入的遗漏入口改名为历史路径规避修复。
- 首先修复最新基本面首差异：收据实际存在，但草稿把 `input_evidence_refs` 写成 `evidence_refs`，先执行的血缘校验报 `MULTIDIMENSIONAL_CALCULATION_RECORD_MISSING`，且不允许纠正。使用真实计算选择而非重抄记录，按结构、引用、血缘顺序准确诊断。
- 任务局部短引用覆盖 Evidence、Document、Calculation 和依赖 Claim；跨报告 Claim 具有明确命名空间。严禁模糊匹配、截断 ID、猜来源或自动修改研究含义。
- 结构化提交前检查可机械定位的问题；同一任务最多一次原 Agent 局部修订，修订后完整复核，不因修订生成新一轮无限额度。技术失败、来源限制、研究充分性分别展示。
- 在既有宿主定点入口支持八维任务的最小依赖闭包，用于调试和补证；保持原八维 Change 的最终“同批八维 8/8 内容通过”要求。不得把跨批拼接或部分通过冒称原最终验收。
- 精简当前规划与历史账本的职责：当前文档只保留生效要求、当前阻断及停止条件；历史运行失败原样保留并索引，不再把每次失败整批计划累加成独立重跑债务。
- 补齐8类工程处理：组件版本单一权威及派生配置；文件/对象/内容hash的显式口径；Memory事实、获取观察与Gate视图分离；当前Schema实际执行一致；历史包离线完整性读取与当前执行配置校验分离；来源拓扑/路由/消费审计共享权威映射；进程/契约/来源/内容/晋升状态分离；开发角色、专业方法与任务上下文分离。
- 明确优先级：P0先修可复现阻断、当前版本冲突并移除CIO/Eval/提交回执hash抄写；P1统一现有交接及工程契约；P2精简上下文、局部修订与依赖闭包调试；P3落实开发防复发和有限收尾。已有正确机制以正反例证明复用，不为19个编号分别建19套实现。

## Capabilities

### New Capabilities

- `research-handoff-contracts`：现有研究/评分/决策入口的语义草稿与可信装配，引用和hash口径、Memory视图绑定、冻结包读取兼容；八维作为首个修复实例而非全部范围。

### Modified Capabilities

- `multi-dimensional-holding-research`：任务闭包定点执行、权威路由到实际消费、内容/执行状态分离，原严格整批验收不变。
- `codex-development-environment`：字段所有权、版本派生、角色/方法/任务边界、19项关闭映射、按影响补验及有限收尾。

## Impact

- 2026-10-01 已批准补验输入调整：允许以新真实正反研究包验证 predecision CIO，不再要求救活旧临时包。仅复用既有宿主入口和冻结资料绑定，显式执行反证准入所需核心正向范围；不恢复原八维整批，不改变其验收标准。具体角色、模型和停止边界见 `bounded-runtime-validation-approval.md` 末节。

- 预计实现范围：既有submission/references/Hook/MCP；`research_materials_stage`、`common_stock_stage`、`multidimensional_stage`、`independent_skeptic_stage`、`predecision_cio_stage`、`smoke_prompt`、`common_stock_eval`、`runtime_eval`的对应交接；现有hash/schema验证、Research Memory、topology/routes/consumption audit、版本清单和相关读取器；现有Agent/Skill/开发规则的对应片段。按实际调用依赖修改，不全目录重构；不修改网络、沙箱、来源授权、Risk/PIT语义或投资判断。
- 依赖影响：若当前没有标准Schema实现，允许为明确的当前契约增加`jsonschema`依赖及薄适配，不再扩写不完整验证引擎；不安装额外平台、不允许校验器联网获取Schema。本轮不安装依赖。
- 开发文档与 `dev_contracts`/`dev_reviewer` 只增加可复用边界、清除重复案例，不将当前股票、失败次数或阶段优先级写入根规则。模型选择和预算策略不改变。
- **兼容边界**：新写入使用显式新版草稿协议；旧运行、正式报告、历史锁不重写。共享代码改变时以实际影响证明复用，不把新版本偷偷套到旧包。
- `complete-eight-dimension-source-consumption` 保持暂停、未完成。后续 apply 须协调共享文件归属；其来源修复与研究质量任务仍属于原 Change。本需求不自动关闭原任务，不启动 Skeptic/CIO/Eval、Regression、Replay 或 Promotion。
- 本次仅更新规划。`analysis.md` 保留最初诊断快照，其中“后续处理”的旧范围划分已由本 Proposal 和 Design 的H01–H19映射替代，不再是延期依据。真实调用次数、模型及输入发送需明确批准；实现/确定性验证/真实运行证明分列，旧额度不继承。
