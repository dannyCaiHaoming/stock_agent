# 最小修复与独立候选接线结果

- `source_id`: `native-package-minimal-repair-readiness:20261008`
- `as_of`: `2026-10-08T11:48:26.566637+00:00`
- `retrieved_at`: `2026-10-08T11:48:42.021620+00:00`
- Change：`simplify-agent-package-for-native-hosts`，仍 **24/31**；七项验收、内容、人工完成及发布任务未勾选。
- 状态：确定性最小修复和新候选接线通过；新候选原生执行 `NOT_RUN`，内容 `NOT_REVIEWED`，未归档或发布。

## 1. 已实施的最小修复

| 既定设计/规格 | 实现与有效检查 | 不改变的边界 |
| --- | --- | --- |
| D3.4.1：计算目录与精确输入血缘有界交付 | `ResearchTools.calculations` 与原 `research_calculations` 增加显式目录页/精确 k 血缘页；完整 JSON 信封受 65,536 UTF-8 字节限制 | 内部完整目录、原数值/单位/方法、精确 k/receipt hash、完整提交血缘保持；不自动选指标、翻页或新增运算 |
| D3.4.1：大型报告无损精确回读 | 既有 MCP `research_read_submission` 路由至 `read_submission_page`；canonical JSON 片段按 Unicode code point 偏移，保留原回执/report hash/完整 payload hash | 内部 `read_submission`、正式报告、依赖及归档消费者继续读取完整对象；不摘要、不删血缘、不把单页当完整报告 |
| D2.5：Claude 已有 Market/Skeptic 固定原生绑定 | 两个薄 `context: fork` Skill 固定原角色；项目角色引用各自已有 MCP；导出映射与缺源/漂移/冲突拒绝同步 | 精确工具、Skills、`model: inherit`、Skeptic 无正向报告读取保持；没有新的 Agent、SDK、Hook、派发器或自动回退 |
| 专业 Skill/工具及当前窗口停止要求 | 共享角色明确实际加载所需 Skill、本角色工具前缀、当前窗口首错停止优先 | 指引不等于实际遵从；不以配置或模型自报证明加载、隔离、模型或停止成功 |

本轮不新增 Fed 离线正文、数据源、文档类型、材料准备能力或执行控制框架。完整公开研究原有依赖、安全与内容门禁不放宽。

## 2. 确定性检查与旧失败保留

[精确检查记录](minimal-repair-check.json)绑定 16 个受影响模块：**191 项、69.576 秒、exit 0**。新增 15 个计算/报告分页测试方法已包含在 191 项中，不另外相加；38 项指定源码/测试文件运行前后 hash 一致。

检查包含大型合成目录/报告经真实 routed stdio 无损读取、Unicode/UTF-8 完整信封边界、小响应兼容、正式提交展开完整血缘，以及权限、跨任务、参数、PIT、输入、资源和报告漂移负例。不是全仓测试、真实原生研究、专项 Eval/Execution Replay/Regression/Calibration/Ablation 或 Promotion。

两个较晚失败批次均保留原日志，不覆盖：

- 44 项中的两处失败：输入漂移夹具改变 `research_question` 却未重算请求自身 hash，先被原完整性门禁拒绝。修正夹具，使其先合法再测试外层绑定；生产门禁不改。
- 原 191 项、68.798 秒中的一处失败：`mkdir(mode=0o755)` 受 `umask 077` 影响，实际生成 0700。夹具显式 `chmod(0o755)` 后，同一 umask 单方法 **1 项、1.058 秒、exit 0**，最终同组 191 项通过；生产权限检查不改。

hash 一致只证明列明文件的字节观察，不是全仓或 OS 强制只读证明。

## 3. 精确新候选与真实确定性接线

外置根：`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006/minimal-repair-current-20261008`。

[候选证据](minimal-repair-candidates-readiness.json)记录：逐项验证原 272 项批准基线，只覆盖本次审阅的 10 项包内文件并增加两份 Claude 原生 Skill，共 **274 项来源**；并行 `product/intake/__init__.py` 使用原批准字节，当前工作树并行修改不混入。导出器本身按本次审阅/测试后的 hash 使用，不额外装入运行包。

| 宿主 | 导出文件数（含 manifest） | 实际候选准备 | 实际 stdio 结果 |
| --- | --- | --- | --- |
| Codex | 305 | 独立 Company/Skeptic/Market 各一任务，CIO 连接 | initialize/list、合法 context、错误任务能力拒绝、Skeptic 禁读、分页 Schema/目录/血缘首个页通过 |
| Claude Code | 308 | 同上，四项私有文件绑定；三个固定原生 Skill 已导出 | 按该候选实际 `.mcp.json` 命令检查上述路径通过；不是原生父/子工具池证明 |
| OpenCode | 301 | 同上 | 上述确定性路径通过；disabled 模板未原生激活 |

两类输入仍分开绑定：

- 原 `normal-research.json` fixture：`SEC-AAA`、`2026-01-31T23:59:59Z`，用于 `FIXTURE_COMPANY_RESEARCH`、`INDEPENDENT_FIRST_PASS` 及后续明确综合阶段的主线程 `FIXTURE_COUNCIL_DECISION`/原 Risk。
- 原 MRVL 公开冻结资料：`US:COMMON_STOCK:MRVL`、`2026-09-28T12:35:32.208143Z`，只准备 `TECHNICAL_STRUCTURE`，基准 `US:ETF:SPY`；不混入 fixture CIO 依赖。

三个宿主从原 MRVL 统计生成的计算目录均完整返回 **27 项/16,663 字节**。仅作传输检查的首个精确 k 血缘页返回 **64/1,518 个 ID**，未宣称完整血缘已消费，也未替作者选择指标。没有事实 query、calculate、submit 或新报告；任务文件在 stdio 前后完全一致。CIO 必须等新的真实正反报告再创建任务，不使用旧回执或合成稿补依赖。

包来源及导出完整性通过；38 项指定源码/测试、原 query 候选/minimal-slice 任务/公共样本及原生结果的 **1,689 个指定旧文件**前后 hash 一致。该保护范围不扩展为所有历史目录或 OS 隔离。公开候选证据扫描排除了本次 21 个已知连接/任务凭据值；原工具转录和私有授权未发布。

## 4. 实际未完成项与下一次运行边界

本次只补 6.1 的确定性准备，不勾 6.1–6.4/7.1/7.2/8.1。旧原生失败、四份旧报告及[旧结果](minimal-native-result.md)保持：

- **Codex**：Folder trust 仍是用户决定，不能代写信任；实际角色、Skill、作者及研究链尚未通过。
- **Claude Code**：新两个固定入口尚未原生执行；Company 旧 zero tools 未有成功反证；旧配置/回告 `claude-opus-5` 与原转录 `gpt-6.1-sol` 的冲突未消除，不能用配置改写实际模型身份。
- **OpenCode**：旧首错后继续调用、Skill 加载缺证及 Market 截断/空选择不被本次确定性检查回签为通过；须由新合法作者实际使用分页并明确选择、提交及精确回读。

后续真实验收仅在各自当前原生产品会话及新的有效有界授权中执行。沿现有最小组合提出的上限仍为每宿主一次、最多 **5 个原生模型任务/30 分钟**：主线程 1、Company 1、独立 Skeptic 1、Market 1；第五项仅容纳宿主自动辅助任务，不用于重派。实际模型须在研究前确认，未知或冲突即停；窗口从首次原生尝试计时，失败计入。该段是下一次运行约束，不是新窗口已批准或已激活。

首个 native/task/Skill/业务工具错误、权限/加载/模型未知、源码/旧产物变化、隔离不可证或截止到达，即停止该窗口后续调用；不改参数重试、不修订提交、不派第二作者、不换入口或续期。所有旧窗口保持停止。本次产品模型、研究来源网络、账户调用均为 **0**。

三宿主必要切片、原报告内容裁定及一次人工最终完成批准齐备后，才可同步主规格、归档并限定提交/推送。当前没有完成批准，未暂存、提交、推送或修改生产版本指针。
