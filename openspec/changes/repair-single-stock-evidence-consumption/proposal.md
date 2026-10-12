## Why

ALB 第六稿的限定版归档仍保留上游假缺口、目录错引、计算遗漏及 CIO 消费不足，不能作为系统全面修复证明。用户进一步明确换股票以及刷新持仓/自选股列表后也应稳定推进，因此本 Change 修复通用研究消费与执行接缝，ALB 必须实质通过，但不再是唯一泛化样本。

## What Changes

- 将统一章节定位与逐条支持核对用于显式新版普通股研究交付：单股及已确认持仓研究共用方法，不硬编码 ALB；正文、目录、截断和未知范围保真，Python 不代选依据或改研究语义。
- **BREAKING（仅显式新版新写入）**：新增 CIO request/synthesis v3 与 native draft v2，记录来源处置、逐条事实/冻结计算支持和全部目标正式挑战。支持已授权的单股或持仓研究综合，仍仅 RESEARCH_SYNTHESIS；不扩大原证券准入、账户适配或动作权限。旧协议、Schema、报告、锁与失败原件不迁移。
- 沿既有 Company、多维、Independent Skeptic、CIO 宿主与主线程调度接入固定 deadline、可信任务状态、最后有效事件、无进展诊断和依赖终态归集；超时、中断、权限拒绝和真实失败可定位，不无限空等、不刷新预算、不增加原阶段 timeout。
- 按真实 invocation、事件口径和父子关系记录 input/output/cached usage、交付字节、读取次数及重复大包；缺失/重叠统计明示，预算耗尽不追加派发，优化只做机械元数据/重复血缘无损共享与定点读取，不削减事实、反证或研究职责。
- 用跨证券、不同资料结构及多任务故障的零模型接缝验证通用行为；另获具体样本/模型/预算批准后完成新 ALB 上游/CIO 内容裁定及至少一个非 ALB 样本的真实运行稳定性与内容核对，不把确定性测试或旧 MRVL PASS 当新版本证明。
- 与 `enable-bounded-stock-list-research-refresh` 分工：本 Change 提供可复用的内容、等待、进度及 usage 接缝；后者负责两类列表输入、增删刷新、严格增量/失效计划和批次归集。此处不新建列表入口、持久化平台或第二套编排器。

## Capabilities

### New Capabilities

无。只加固现有研究与运行边界，不新增 Agent 职责或通用基础设施。

### Modified Capabilities

- `common-stock-holding-analysis`：新版普通股 Company 章节定位、缺口/支持核对与可信有界任务状态，覆盖单股及已确认持仓研究。
- `multi-dimensional-holding-research`：新版 Fundamental/Technical 逐条支持、最小依赖失效闭包及多维有界依赖等待。
- `portfolio-council-orchestration`：新版研究级 CIO 处置/计算/渲染，以及四阶段固定预算、真实进度、usage 核算和无损重复消减。
- `single-stock-research`：ALB 原错误逐项实质验收、跨证券泛化验证和分阶段授权，不沿用旧限定版例外。

## Impact

涉及现有 `common_stock_stage.py`、`multidimensional_stage.py`、`independent_skeptic_stage.py`、`predecision_cio_stage.py`、`fixture_mcp.py`、`cio_handoff.py`、计算/提交/状态验证和原宿主参数接线；新增批准的交付、CIO、计时/进度/usage 版本，更新对应 Skill 与任务指引、中文消费者及聚焦测试。复用原 read/query、可信装配和有界局部纠正，不新增模型评委、CIO 子 Agent、搜索/计算权限、监控服务或自动模型修复循环。

原依据为 `.codex-local/alb-report-cio6-20261003/README.md` 及旧单股归档证据。原 5166.903 秒是 started_at 至 generated_at 差额，不是已确认通信耗时；22 条连接错误不构成完整定因。原第五稿 FAIL、第六稿限定人工验收及原 Reviewer 未给第六稿 PASS 的事实保留。

2026-10-04 批准仅覆盖本 Change 规划更新与新列表 Change 的四类规划创建；不授予 apply、数据获取或真实模型调用。实际等待、token 与调用预算在确定性准备后列明并另获批准；外部服务和不可抢占 OS/I/O 仍可能慢，承诺的是可观察、有界处理，不是永远快。独立内容裁定与人工最终完成批准后才限定归档/提交/推送，不切分支、合入 main、建 PR 或隐式运行 Eval/Replay/Regression/Calibration/Ablation/Promotion。不编辑其他活跃 Change。
