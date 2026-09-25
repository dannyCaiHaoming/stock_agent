## Why

真实 Company、Macro、Market 多维研究与 Independent Skeptic 已形成 MRVL 的 `PreDecisionResearchPackage`，但旧 CIO 入口不能直接消费这些报告。用户现已清仓 MRVL，本 Change 只完成可审计、非动作的 CIO 正反研究综合；不把历史持仓包装成当前建议，也不为完成验收索取新账户或期权资料。

## What Changes

- 保留显式 `PREDECISION_CIO_SYNTHESIS` 宿主阶段：重验并冻结已完成的 MRVL 正向与独立反证报告，由主线程 CIO 一次综合，不重新派发 Specialist，也不改写来源运行。
- 本次唯一产品交付级别为 `RESEARCH_SYNTHESIS`：回答判断与分析期限、关键事实推导、重要反证取舍、Macro/Market 传导、推翻条件和观察计划。明确它基于原研究截止点，当前个人账户适配未评估。
- 研究输出禁止 HOLD/TRIM/EXIT/NO_TRADE、目标仓位、现金安排、最大金额、`decision.json` 和 Risk 通过声明；`Risk=NOT_RUN`。既有完整 Council/fixture 风控能力保持原样。
- 撤出本新阶段尚未真实验收的 `PORTFOLIO_ADVICE` 宿主入口及仅服务该分支的实现/契约；不借缺失的当前 MRVL 持仓合成历史建议。未来若需当前持仓建议、再买入建议或回测，应独立定义范围和验收。
- 复用原始研究包身份、Evidence Gate 查询、模型执行证明、同源中文报告和 Trace；继续拒绝不合格来源包、篡改、未查询引用或把 Skeptic `INSUFFICIENT_EVIDENCE` 当完成。
- 复用已有真实 MRVL 研究级验收的有效部分；阶段代码/锁定指令调整后补受影响的宿主真实 Smoke 与独立内容复核，不能把旧运行的 PASS 冒充新版本验收。
- 收尾限定为既有运行证据闭环：事后检查必须核对宿主进程结果；源码保护采用原生沙箱、仓库外工作区、受保护产品文件前后完整性检查及漂移拒绝。全进程 OS 强制只读仍为未验证边界，不作为本 Change 新增交付，也不建设权限探针平台。
- 最终会话直接展示同源核心结论、主要反证及限制并附报告链接。本次不实现回测、Outcome、收益曲线、买入/加仓、ETF/期权研究、网页改版或晋升。

## Capabilities

### New Capabilities

无；扩展既有编排、建议输出与风控能力。

### Modified Capabilities

- `portfolio-council-orchestration`：新增从正反交接包显式启动的研究级 CIO 阶段、来源绑定、失败边界和真实验收。
- `advisory-decision-output`：定义多维正反报告的非动作 CIO 综合和同源中文输出。
- `deterministic-portfolio-risk`：明确本研究级阶段不运行 Risk、不输出组合建议，不改变既有 Risk 能力。

## Impact

- 收敛 `product/runtime/predecision_cio_stage.py`、阶段 Schema/Trace、宿主 CLI/脚本及报告，禁用并清理本阶段尚未验收的建议分支；保留既有 fixture Risk 与其他 Change 文件。
- 对齐 `product/.codex/agents/runtime_cio.toml`、`product/skills/portfolio-council/SKILL.md`、版本锁及产品/运行文档；不批量迁移历史产物或恢复已退役 live profile。
- 聚焦 Skeptic、多维研究、研究级 CIO、旧 Risk 和宿主入口回归；不新增服务、数据库、模型编排后端或外部付费依赖。
- 老虎证券 Change 与其未提交修改不属于本次范围。发布时仅纳入 CIO 必需且已审阅的共享模型路由依赖，不顺带归档其他 Change。
