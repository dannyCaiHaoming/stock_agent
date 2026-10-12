## Why

用户需要换证券以及刷新已确认持仓列表、无账户自选股列表后，研究系统能够在明确预算内推进或结束，而不是整批重跑、丢失已完成成果或无期限等待。现有单股请求和 PortfolioHandoff 不能表达任意无账户多代码列表；已有数据增量与 Company 复用也不足以证明全研究链批量刷新，因此需要沿原调度补全输入、失效计划和归集契约。

## What Changes

- 新增显式 `STOCK_LIST_RESEARCH` 自选股输入契约，逐项核实受支持普通股身份、问题、cutoff 和来源血缘；禁止伪造空 PortfolioHandoff、现金、持仓或账户。已确认持仓沿原 Handoff 加独立 CouncilRequest，不修改 Intake 确认和完整性规则。
- 新增版本化列表请求、刷新计划与结果索引，保留完整输入与逐项覆盖；增删/顺序变化、资料/cutoff/版本/依赖变化均有可审计复用或失效理由，不按 ticker/TTL/文件存在猜缓存有效。
- 沿既有 Company、多维、独立 Skeptic、研究级 CIO 主线程调度透明分批，共享有界并发和批次预算，逐证券输出研究成果与限制；不新增 Agent、后台刷新服务或第二套编排器，不扩展交易/账户决策。
- 单项身份、来源、执行或研究失败只阻断实际依赖；无依赖任务在批准剩余预算内继续，保留已完成原件。预算用尽、中断和共享基础设施故障明确归集，不自动重试、换模型或整批重跑；后续显式恢复重新验证，仅处理必要闭包。
- 复用现有 Research Memory 的数据增量/checkpoint 与报告保存边界；扩展必要的已验证多维/反证/综合报告复用记录与依赖证明，不另建历史库，原报告可读且不升级为当前事实或当前账户建议。
- 依赖 `repair-single-stock-evidence-consumption` 的通用内容修复、有界等待、进度与可信 usage 接缝；本 Change 只接线列表级计划/预算/进度汇总，不重复实现底层协议或将 ALB 成功当两类列表稳定证明。

## Capabilities

### New Capabilities

- `stock-list-research-refresh`：两类列表的明确输入、逐项身份/覆盖、刷新失效计划、有界批次执行、局部失败和显式恢复验收。

### Modified Capabilities

- `single-stock-research`：单股与无账户列表模式必须显式分离，列表内研究仍为逐证券 RESEARCH_SYNTHESIS，不冒充持仓或自动组合动作。
- `portfolio-council-orchestration`：原调度消费版本化列表/刷新计划，共享并发和预算、可信状态与依赖归集，不自动启动未授权阶段。
- `persistent-company-research-memory`：两类列表复用现有逐证券增量资料，研究报告复用由严格输入/版本/依赖及隔离证明决定，历史与当前有效性分离。

## Impact

预计涉及 `research_input.py`、原单股身份核实与准备工具、Company/多维/独立 Skeptic/CIO 的显式输入版本分支、现有报告包/Memory 读取校验、Runtime CLI 与宿主 launcher 的参数/记录接线，以及 portfolio-council 的列表阶段指引、中文结果/进度读取和聚焦测试。新增列表契约不原地改旧 Schema；列表 CIO 新请求版本复用前置 Change 的 synthesis v3/native v2。不开放 PORTFOLIO_ADVICE，不改变账户确认，不新接券商/网络来源/ETF 或期权研究，未支持项完整保留为覆盖限制。

本 Change 规划创建不授权 apply、真实股票资料获取、模型调用、专项 Eval/Replay 或发布；准备完成后另列实际列表、cutoff、阶段、父子数、完整版本锁、数据/时间/usage 预算和停止条件供批准。列表真实验收须覆盖持仓和自选股两种模式及刷新，不单凭 ALB/MRVL 历史稿或合成测试宣布完成。独立复核与人工完成批准后才按开发流程归档/限定发布。不得编辑其他活跃 Change、私人运行原件或用户已有修改，不切分支、合入 main 或创建 PR。
