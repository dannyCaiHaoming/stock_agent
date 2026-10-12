# 三宿主最小原生验收结果（未通过，窗口均停止）

- `source_id`: `native-package-minimal-native-summary:20261008`
- `as_of`: `2026-10-08T10:03:31.019729+00:00`
- `retrieved_at`: `2026-10-08T10:03:31.019729+00:00`
- Change：`simplify-agent-package-for-native-hosts`，**24/31，尚未完成**。
- 结构化证据：[minimal-native-result.json](minimal-native-result.json)。

## 结论与范围

本轮不再停于零模型准备：三个宿主均实际进入原生准入或执行。Codex 停在模型前的目录信任界面；Claude Code 成功消费三项新任务 context，但首次专业派发失败；OpenCode 创建了三个原生专业作者，保存并精确回读四份真实报告。然而，OpenCode 的 Company 首错后仍继续，Market 统计输出被截断且未选择计算引用，不能以报告业务校验成功覆盖运行条件失败。

三宿主目标和七项未完成任务保留，不勾选 6.1–6.4、7.1、7.2、8.1。没有新增产品源码、测试、Schema、Fed 接缝、来源准备、Agent、模型后端或停止控制器；没有归档、暂存、提交、推送或改生产指针。

## 本次授权及固定窗口

在已经展示“三宿主各一次、每宿主最多 5 原生任务／30 分钟”具体提案后，用户再次要求继续完成并同意授权，本轮据此执行该有界方案。用户没有另逐项填写参数或作出新的 AskUserQuestion 选择，不把执行解释改写成这些不存在的记录。此前“新提案尚未授权／新增模型 0”的准备报告仅适用于其原时点。

| 宿主 | 固定首次尝试至截止（UTC） | 实际计数与停止结果 |
| --- | --- | --- |
| Claude Code | 09:19:10.520391—09:49:10.520391 | 主线程 1＋失败 Skeptic 派发 1＝2/5；实际专业作者 0，首错后停止 |
| OpenCode | 09:29:08.313040—09:59:08.313040 | 同一 primary 1＋Company/Skeptic/Market 各 1＝4/5；已确认本地终端回到 shell，不晚于 09:55:45.067535 |
| Codex | 09:30:07.127065—10:00:07.127065 | 原生入口尝试 1，模型任务／专业作者／业务调用均 0；目录信任前停止 |

原生任务数不是 API 请求、token 或费用测量。第五项不用于重派；所有窗口均已停止，不借余量、不重开或续期。操作方停止本地终端不等于 Provider 取消已验证。

输入仍分别绑定：既有 `normal-research.json` 合成 fixture 的 SEC-AAA、cutoff `2026-01-31T23:59:59Z`，用于 Company、独立 Skeptic、明确主线程 CIO 和原 fixture Risk；既有 MRVL 冻结公开资料的 `TECHNICAL_STRUCTURE`、cutoff `2026-09-28T12:35:32.208143Z`、benchmark `US:ETF:SPY`，仅用于独立 Market 技术切片。两类报告／动作权限不混用。

## Codex：真实准入阻断，模型未开始

仅本次进程的原生配置解析已显示四个研究 MCP 服务均 enabled；这不等于角色加载。第一次 Terminal 命令在启动前被解析 Hook 拦截，依其明确语法反馈修正后，同一固定窗口真正进入 Codex 原生 `Trust this folder?` 界面。该界面说明决定会保存，未自动选择信任、写全局 `projects.trust_level` 或复制认证。

已用 Ctrl-C 停止，本次模型／专家／研究业务调用均 0。这个准入观察不能直接解释历史 `unknown agent_type` 的全部根因，也不能据此勾选 6.2。

**最小剩余动作：**用户在 Codex 原生界面对精确审阅的候选目录作出信任决定；具备有效的新有界窗口后，再验证角色、工具、专业首轮及主线程链路。当前不代替用户作出信任决定或恢复旧窗口。

## Claude Code：新连接成功，Skeptic 调用误参

产品会话已实际切入新四连接候选。官方导出的当前窗口转录确认：

- 09:37:14.691，Company `research_context` 成功，使用本次 Company task_ref。
- 09:37:41.949，Skeptic `research_context` 成功，使用本次 Skeptic task_ref。
- 09:37:58.437，Market `research_context` 成功，使用本次 Market task_ref。
- 09:41:20.621，实际 `Agent` 调用选择 `runtime_skeptic`，但仍带 `isolation=worktree`、`model=opus`。
- 09:41:20.627，返回 `Cannot create agent worktree: not in a git repository and no WorktreeCreate hooks are configured.`，作者创建前失败。

原始参数键为 description、isolation、model、prompt、run_in_background、subagent_type。本次没有实际省略这些可选参数，不能宣称宿主拒绝省略。此前真实 Schema 的可选性证据保留，不因这次失败改写成强制字段。没有初始化 Git、配置 WorktreeCreate、重派、换入口或续期。

实际专业作者、专业 query/calculate/submit/read_submission、报告均 0；Company-native、Market 作者、CIO 准备及 Risk 未运行。三次成功 context 只证明新业务连接绑定，不能当作子作者工具池、Company-native zero tools 修复或完整 6.3 通过。

**模型证据差异：**桌面会话配置／同行回告为 `claude-opus-5/high`，但官方导出当前窗口的 26 条 assistant `message.model` 均为 `gpt-6.1-sol`。两类元数据不一致，实际 Provider 模型身份继续 `UNVERIFIED`；不据任一项推定另一项必然错误，不擅自换模或修改桥接。原始转录仅本地保留；本次只读取官方导出的两份同内容 transcript JSONL 成员，没有读取 local-session-state 或扫描私人数据库。

**最小剩余动作：**取得正确原生 Skeptic 调用和一致的运行模型观察，再在另有有效窗口时验收 Company-native 及剩余链路。本轮不新增未经修订批准的 fork Skills、派发包装器或权限回退。

## OpenCode：真实业务链路与失败同时保留

### 已观察的原生事实

原生内联配置 `OPENCODE_CONFIG_CONTENT` 经实际解析生效，避免较低优先级 `OPENCODE_CONFIG` 被项目配置覆盖：主线程三项专业 prepare_task 为 deny，仅允许 CIO 业务、指定 Skill 和三个专业委派；四服务 enabled。没有修改全局或候选配置。主线程和三个子作者的原生 metadata 均为 `aliyun-bailian/glm-5.2`，不是 Provider wire 身份认证。

Company、Skeptic 两项 task 来自同一 parent assistant 消息，分别于 09:37:34.851 和 09:37:48.176 开始，均早于任何一份报告完成。各子会话仅有一条初始用户消息，精确等于本角色 dispatch prompt，只含自己 grant，没有其他专业或 operator 凭据。Skeptic 没有收到正向报告；实际调用也未读取正向报告。这个证据范围不外推为所有系统上下文或 Provider wire 的保证。

实际 Skill 调用：primary `portfolio-council`；Skeptic `counter-thesis`；Market `technical-structure`。Company 没有任何 Skill 工具调用；Skeptic 的 `evidence-grounding` 实际加载证据仍缺。父线程三个专家 workflow 还误写了 `cio_research_*` 前缀；实际作者使用了自己的 company/skeptic/market 工具，不把这项指令错误掩盖为成功。

### 首错与后续越过停止点

Company 合法读取全部 5 项 fixture 事实，并成功计算 debt/revenue＝0.15。随后：

1. 09:38:10.869，针对 `ev-normal-revenue` 的 `monetary_scale` 返回 `MONETARY_MENTION_NOT_FOUND`。
2. 09:38:11.828，针对 `ev-normal-debt` 的另一次换算返回同一错误。
3. 作者仍继续 calculations、submit、read_submission；主线程随后进入 Market 和 CIO。首错后共观察到 **19 次业务工具调用**。

原 fixture 两个金额为数值 scalar；当前 monetary_scale 只接受已支持的金额正文或受限 SEC amount 对象，这次拒绝符合现有契约。不能为让验收通过而扩展任意数值／单位权限，也不是 SEC 对象接缝修复回退的证明。作者“所有步骤成功”的自报与原始工具错误不符，按实际转录裁定。

首次结构化采集记录的 as_of 为 09:46:52；本地 Ctrl-C／回到 shell 已确认不晚于 09:55:45.067535。最后 CIO 精确回读于 09:53:10.090 完成。不得把这段观察差额写成运行时即时停止已实现；本 Change 不新增监控／停止平台来掩盖它。Provider 取消保持 `UNVERIFIED`。

### 四份真实回执

| 作者／能力 | 精确回执 | 实际业务状态与限制 |
| --- | --- | --- |
| Company／FIXTURE_COMPANY_RESEARCH | `r1.9vCzw3O7IwyZMfGpgFi3FF_3` | VALIDATED，精确回读；首错后提交，Skill 加载缺证 |
| Skeptic／INDEPENDENT_FIRST_PASS | `r1.sVekzBmnDg4pKPBdptTMlkdx` | VALIDATED，精确回读；独立初始输入已观察，不代表全窗口合格 |
| Market／TECHNICAL_STRUCTURE | `r1.qQUms_uumg65rw7yOSgBFPfO` | VALIDATED，精确回读；两次统计输出截断，计算选择为空 |
| 当前主线程 CIO／FIXTURE_COUNCIL_DECISION | `r1.1bDu460N3H1Lf28c4u53Gsa5` | 实际 prepare/context/read_reports/query/submit/read；原 Risk APPROVED，终态 SAFE_NO_TRADE |

CIO 没有子 Agent；实际 read_reports 消费本次 fixture 正反两稿，独立 Market 不混入其依赖。四份原报告均 `advisory_only=true`，信封中的 `host_execution=UNVERIFIED`、`content_verdict=NOT_REVIEWED` 保持不改。报告的业务有效不抹除首错后的运行失格，原 Risk APPROVED 也不是真实账户、研究内容或 Promotion PASS。

### Market 统计消费缺口

两次 `market_research_calculations` 的原生状态均 completed，但 metadata `truncated=true`，提示各截断 3,537,664 字节，只留下截断通知。开发未读取宿主全局 tool-output 文件、开放 Read/Bash 或让作者换通用工具绕过限制。

最终提交 `calculation_selections=[]`；作者在报告中披露无法取得精确 k 引用及未读取原始 OHLCV。`research_catalog` 的 0 条是原契约事实允许集为空，不等于本任务统计对象不存在。不能用再次调用同一大结果、摘要中的数字或 Schema VALIDATED 代替统计选择／完整消费证明。

**最小剩余动作：**先处理已有原生指令／Skill 加载、首错遵从和有界统计消费缺口，再在明确的新窗口验收；不新增来源、统一 Runtime、模型后端或生命周期控制器，也不重派本窗口。

## 内容核对与保护范围

本轮已做开发侧原稿核对，未回写或升级内容裁定：

- Company/CIO 的 debt 150,000 USD、TTM revenue 1,000,000 USD、margin 0.18、close 100 USD/share 和 ratio 0.15，与本次实际 query 及合法 ratio 一致；来源时点、单位和合成性质有披露。
- Skeptic 四项疑问针对单期趋势、偿债能力、产能计划语义及估值未知；CIO 实际读取并逐项回应。Company 的“moderate leverage”仍是缺少独立比较支持的解释，不能升级为确定事实。
- Market 披露统计截断和空计算选择；相对收益差 209.82 应区分百分点与收益率，不能因数字出现就判完整内容通过。
- Codex／Claude 本窗口没有专业原报告；7.1 的三宿主内容门禁未满足，不默认另启 Reviewer 或模型评委。

三个实际候选分别 **303／304／299** 个文件，共 **906** 项，完整前后 hash 相同，无新增、缺失或字节变化。只证明精确保护集未变，不证明 OS 强制只读；旧 1,219 项准备保护结果只保留其原时点，不冒充本次扩大核验。

结构化公开证据仅保留白名单字段、时间、回执、hash 与错误，已排除本轮已知 21 个能力凭据值。原始转录、私有 packet、连接文件、宿主导出和无关用户消息不复制到仓库。

原 28 项聚焦确定性检查复用，本轮没有产品源码／测试变化，未为记录同步重跑全仓或启动服务。另做 OpenSpec strict、文档链接／格式及限定敏感信息检查，具体结果以本轮检查输出为准。Runtime Eval、Execution Replay、Regression、Calibration、Ablation、Promotion 均未运行。

## 任务与发布边界

6.1 的三宿主实际准入／权限仍不齐；6.2 Codex 模型前停止；6.3 Claude 作者前失败且模型元数据冲突；6.4 OpenCode 首错后继续、Skill／统计消费缺证。7.1 缺三宿主内容材料；7.2 的映射已更新但三宿主验收和最终人工完成批准尚缺；8.1 因此不执行。

这些是真实宿主准入及执行结果的阻断，不是缺少 Fed 正文或需要扩建 Agent 框架。停止相应运行不等于放弃三宿主目标。保留全部已有修改和失败证据，**不宣布 Change 完成，不归档或发布**。

## 本轮记录检查

- `source_id`: `native-package-minimal-native-record-check:20261008`
- `as_of`: `2026-10-08T10:09:25.634665+00:00`
- `retrieved_at`: `2026-10-08T10:09:25.634665+00:00`

OpenSpec strict、git diff --check 通过；11 份本 Change 规划／记录的格式及 JSON、128 个相对链接检查通过；21 个已知能力凭据值未进入这些文件。四份真实报告、首错后 19 次业务调用、906 项候选保护及独立初始输入计数一致性检查通过。复读 apply instructions 仍为 spec-driven／ready／24/31，暂存区为空。本会话创建的两个已停止 Terminal tab 已关闭，不留下新的模型运行。这些是记录与证据一致性检查，不是原生验收、全仓测试或 Promotion PASS。
