# Agent Package 最小验收准备结果

- `source_id`: `native-package-minimal-slice-summary:20261008`
- `as_of`: `2026-10-08T08:54:32.124980+00:00`
- `retrieved_at`: `2026-10-08T08:54:32.124980+00:00`
- 状态：**范围修订及零模型准备完成，原生验收未完成，24/31**。
- 结构化证据：[minimal-slice-readiness.json](minimal-slice-readiness.json)。

## 已实际完成

1. Proposal、Design、两份相关 delta specs 和 Tasks 已收敛到共享 Skills、四职责正文、三宿主薄配置/安装映射、既有受限确定性工具和旧控制层退役。OpenSpec strict 通过；31 项任务不删，未完成项不勾。Fed 离线正文、新文档类型和材料扩建不再是本 Change 的前置，正式研究原依赖不变。
2. 复用同一 272 项已批准包源，三宿主分别用实际候选的 `product.tools.prepare` 准备 3 个专业任务，共 9 个；不是静态模板或手写任务信封。既有合成 `normal-research.json` 与 MRVL 冻结公开资料分别绑定，不混用报告或动作权限。
3. 每宿主 Company / Skeptic / Market 的真实 stdio 初始化、工具目录、合法 context 和错误任务凭据拒绝通过。Skeptic 无依赖报告且实际调用 `research_read_reports` 被拒绝；这证明服务端边界，不证明宿主上下文隔离。
4. 三宿主各自 CIO 连接已绑定本宿主 Company/Skeptic 连接，尚未创建 CIO 任务。必须等待真实作者的合法报告与精确回执，不以开发合成稿填充依赖。
5. Claude 新候选含四个明确文件绑定的服务，304 个导出文件（含 manifest）。按新项目声明的四条 MCP 命令检查通过；三项专业任务 hash 与原准备一致，未重签。旧候选及原私有任务 1,219 个文件前后 hash 相同；不等同 OS 强制只读。
6. 本次 28 项 fixture、完整范围、报告读取和连接聚焦确定性测试通过；230 项产品 Python/焦点测试字节前后相同。与历史 174 项不累加为独立覆盖数。无新增产品源码、测试或 Schema。

## 最小合法场景

| 场景 | 输入及职责 | 停止点与限制 |
| --- | --- | --- |
| 合成 Council | 既有 `normal-research.json`；`SEC-AAA`，cutoff `2026-01-31T23:59:59Z`；Company、独立 Skeptic、明确综合阶段的主线程 CIO | 合法报告、实际读取及原 fixture Risk；只说明合成场景，不形成真实证券/账户建议 |
| Market 技术切片 | 既有 MRVL Gate；`US:COMMON_STOCK:MRVL`，cutoff `2026-09-28T12:35:32.208143Z`；基准 `US:ETF:SPY`；`TECHNICAL_STRUCTURE` | 仅技术报告和精确读取，不进入完整八维、公开股票综合或账户建议 |

TECHNICAL_STRUCTURE 的既有统计准备生成 1 项预计算对象，事实允许集按原契约为空；作者通过已有 calculation catalog 选择和解释，不为这次验收修改事实或工具规则。fixture 的事实查询/所需计算由作者自主选择。

私有授权仅留在已准入外置根 `minimal-slice-20261008/{codex,claude-code,opencode}`，不随本报告交付。专业短包分别 495/485/517 字节，未含连接凭据；操作方授权、私有连接和原始输出不提交。

## 原生接线的当前限制

- **Claude Code**：产品会话仍 idle 在旧 companymcp 项目，最后活动 `2026-10-08T03:35:49.728Z`，会话模型元数据 `claude-opus-5` / high。新四连接候选尚未被该会话加载；stdio 目录完整不能证明父/子工具池已注册或 zero tools 已修复。须先取得新项目实际连接/精确工具池及角色来源观察，再派专业作者，不用同一失败声明盲派。
- **Codex**：CLI 0.160.1 的零模型检查显示 multi_agent=true，但从候选目录执行 `mcp list --json` 未列出该项目四个研究服务。项目配置实物存在且无解析警告；这不能单独确定是命令作用域、项目准入还是历史角色失败根因。未读取或修改全局信任、认证或安装。官方配置文档区分 trusted project 配置加载与实际 Agent 发现，不能自动更改信任以求通过。
- **OpenCode**：CLI 1.18.34；既有结果证明曾创建 Company 作者，但未得到合法报告。新最小切片尚未激活；独立首轮隔离、实际工具权限与提交/读取仍需原生观察。

## 下一次原生运行的具体有界提案（尚未启动）

此处是新的提案，不续期任何旧窗口，不把一般 apply 或“所有授权”回填成已批准的具体新额度。

- 三宿主各一次；每宿主最多 **5 个原生模型任务、30 分钟**。正常计划是当前主线程 1、Company 1、Skeptic 1、Market 1；第五项只容纳宿主自动标题等实际可观察辅助任务，不用于重派或换模。三个宿主总上限 15 项/各窗口累计 90 分钟；原生任务数不是 API 请求数、token 或费用测量。
- Claude 使用其产品会话当前 `claude-opus-5`，专业角色 inherit；Codex/OpenCode 使用用户当前原生合法默认，在首次研究前记录实际可观察值，不能确认即停，不通过 Prompt 换模。
- 首次原生模型尝试开始计时，记录实际 UTC 截止；先核对精确新项目、专业角色、MCP 工具池和权限，再研究。每宿主独立预算，不借用其他宿主或旧窗口余量。
- Company 和 Skeptic 使用 fixture 独立初始输入；Skeptic 不接收正向结论或父研究历史，且无正向读取工具。Market 使用独立 MRVL 任务。只有真实正反报告合法后，明确进入主线程 fixture CIO，按原工具创建任务、实际读取并提交；不得另建 CIO 子 Agent。
- 任一原生加载/授权/工具错误、隔离不可证、源码/旧产物变化、模型不可确认或达到上限，停止该宿主后续调用并保留原错误；不自动重试、换入口或续期，不新增停止控制器。
- 不联网补采、不访问账户、不运行专项 Eval/Replay/Promotion。fixture 原 Risk 与两稿上限不变；公开技术切片无动作/仓位/金额。
- 对应产品会话准入与本提案获得明确运行授权前，新增产品模型调用保持 0。完成三宿主切片及内容核对后，仍单列最终人工完成批准。

## 未完成与排除项

6.1 仍缺当前原生权限/加载确认和上述新有界运行授权，6.2–6.4、7.1、7.2、8.1 保持未完成。旧完整研究、Macro BLOCKED_CONFIGURATION、zero tools、角色不可见、fail-fast 偏差和 Provider 取消未验证等历史记录不改。

本次没有产品模型任务、作者 query/calculate/submit、原生报告、研究来源网络或账户调用；没有 Runtime Eval、Execution Replay、Regression、Calibration、Ablation、Promotion、开发归档、Git 暂存、提交、推送或生产指针变更。未声称全仓测试通过。
