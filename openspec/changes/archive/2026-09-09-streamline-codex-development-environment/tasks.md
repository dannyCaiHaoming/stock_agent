## 1. 前置条件与证据边界

- [x] 1.1 确认旧 `runtime-replay-and-eval-hardening` 已按原批准完成安全发布收尾；验证其归档、批准和 scoped commit/push 记录，保留 NOT_PROMOTABLE。若私人会话数据库问题仍未处理则停止实施，仅报告依赖，不在本任务清理或重开旧 Change。
- [x] 1.2 在本 Change 验收记录中锁定起始源码快照、候选及已有证据完整 hash，逐项建立 Specs → diff/依赖 → 复用理由 → 新增证明映射；验证 Design D7 的有限验收与现有主规格无冲突，未解决冲突不得进入真实运行。

## 2. 指令与文档整理

- [x] 2.1 整理根/产品 AGENTS.md，新增 workflow/environment 两份专项文档并更新现有 runbook；用治理检查及差异评审验证中文默认、条件读取、开发不担任 CIO、产品不归档/Git，以及原安全规则和归档推送停止条件均保留。
- [x] 2.2 按现有 model-routing 策略落实受支持的开发/评估配置；保存本机版本、help/配置解析依据及请求模型来源，验证 Sol/Terra/Astra 无静默替换，Desktop 无法切换时明确提示，不启动额外模型探测。

## 3. 路径与统一入口

- [x] 3.1 实现 Design D2 的最小开发薄入口，继续调用现有 CLI 与 launcher；用零 LLM 路由测试验证 Smoke、Execution Replay、Regression 新执行共用同一实现，Artifact Replay、确定性案例及缓存验证不启动模型，既有命令保持兼容。
- [x] 3.2 统一 repo/product/run/state 路径来源并保存解析记录；用零 LLM 测试覆盖根/product/外部 cwd、空格、相对参数、冻结 workspace、根冲突、越界链接与重复 run 身份，验证产品/MCP 实际 cwd 固定且冲突在模型前拒绝。
- [x] 3.3 移除活跃 smoke/Eval Prompt 与操作示例中的个人 sessions 路径，复用 run-scoped 事件或显式 sessions-root；用模板和命令生成测试确认无个人路径、无临时源码/凭据复制，密封 Capsule 重放与历史产物不被改写。

## 4. 模式分离与最小诊断

范围批准见 `reviews/development/streamline-codex-development-environment-scope-approval.md`。4.1–4.4 的勾选仅保留历史工作记录，不构成当前全进程隔离 PASS；全进程源码强制只读独立状态为 **UNVERIFIED**，排除在本 Change 完成保证之外。

- [x] 4.1 基于本机支持的 sandbox 接口落实开发与测试/复核的权限配置，覆盖外层 launcher、内层 Codex、MCP、Hook；保存零 LLM 配置解析结果，验证 unsupported/外层权限不足时 BLOCKED，并输出具体最小授权而非自动提权或全局放权。
- [x] 4.2 在实际受限进程中执行零 LLM 安全探针，验证源码保护区拒写、指定产物及 TMPDIR 可写、越界拒写和后代继承；保存命令、有效策略及原始结果，分别报告环境错误与断言失败，不以事后 hash 代替权限证明。
- [x] 4.3 复用已有可写检查及本机 doctor，增加最小 environment_preflight 与诊断输出；用零 LLM 测试验证缺目录、配置不支持、模型待确认、权限不足、prepare-only、加载证明缺失的分类，输出 preflight.json/md 与明确 failure_code，正常 preflight 的 llm_calls 为零。
- [x] 4.4 增加开发专用 codex-development-diagnostics Skill，引用检查器与指定运行事件；通过 Skill 内容和调用边界检查确认不进入产品包、不自动修复/重跑/推送，不读取全局用户消息、不导出凭据或会话数据库。
- [x] 4.5 将资源发现、配置解析、实际加载证明分层绑定到既有 invocation/execution-proof；复用已有模型运行证据，历史 COMMAND_NETWORK_STATUS/NESTED_CODEX_STATUS 按原配置保留，不再要求新探针；用正负事件测试验证文件存在不能冒充加载、hash 漂移/缺证明仍非零、合法前置终止按原规则处理，并核对 Hook 信任来源与授权，无自动扩大豁免。

## 5. 有限集成验证

- [x] 5.1 执行证据映射内受影响的确定性测试和 `openspec validate streamline-codex-development-environment --strict`；保留命令、计数、独立 TMPDIR、结果与 hash，确认无顺手扩展全量产品验收；未通过则不启动真实 Smoke。
- [x] 5.2 在当前配置锁下复用宿主入口已完成的 Terra normal Smoke 功能证据，使用全新 run_id；核验 AGENTS/Skill/Agent/MCP/Hook 的真实加载事件、Specialist/CIO/Risk、decision.json/report.md/decision_trace.json/eval/result.json 与 launcher 完成判定。失败立即保留首处分歧并停止后续 LLM。关闭证据见验收记录第 6 节及最终独立补充复核；不覆盖全进程隔离。
- [x] 5.3 使用 5.2 的密封 Capsule，经宿主入口和同一 launcher 完成一次 Terra Execution Replay Smoke，使用新 run_id；验证冻结根选择、实际配置等价性、完整终态和原 finalizer 结果，不改写旧证据、不新增完整 Replay 框架；失败停止，不自动重试。 关闭证据见验收记录第 8 节。
- [x] 5.4 针对受影响的 Regression 入口/证据消费/缓存接缝执行零 LLM 子集，引用新 Smoke 的实际运行证明；报告验证的案例/依赖及其余证据复用理由，不以子集冒充 12-case 新候选全量验收，不重新运行六个 LLM 案例。

## 6. 独立复核与人工收尾

本次宿主代理适配补充：只读系统检测、两个薄脚本与零 LLM 聚焦测试。
历史范围调整本身没有关闭任务；后续按实际证据已关闭 4.5、5.2、5.3、5.4（见验收记录第 6、8、9 节），不将功能证据扩展为隔离证明。

- [x] 6.1 生成限定验收报告：每项列明 Specs/Tasks、实际命令、execution/run ID、输入输出路径、完整 hash/版本、结果、复用依据与局限；核对只有两次已声明 Council 运行，缺证据或超范围问题明确记录，不启动 Calibration/Ablation/Promotion 或完整 Release Gate。
- [x] 6.2 委派未参与实现的独立 Reviewer，只读复核本次差异、原生权限声明、隔离 UNVERIFIED 边界、原始加载/执行事件及证据映射；需补跑只报告缺口，由宿主入口另行授权执行；产出独立记录和完整快照标识，不默认重复测试；明确 Change 结论不构成候选 Promotion PASS。
- [x] 6.3 向用户提交本 Change 人工批准申请；只有明确批准后记录完成，不自动归档/提交/推送或更新生产指针。后续归档发布按仓库规则另行执行，敏感信息、未审阅实现或校验失败均停止。

## 本轮限定交付（不替代以上任务关闭）

Task 5.3 的非 Git 冻结目录接缝已获专项修复授权：只改宿主 transport，新增来源绑定/密封校验与确定性测试，不改历史锁。后续真实 Execution Replay 已通过并关闭 5.3，见验收记录第 8 节。

同步批准与规划；拒绝旧 --review 和项目沙箱薄入口；开发自检白名单；宿主产品统一启动；更新诊断 Skill/环境文档/验收记录；只运行入口分流、禁止隐式启动和失败传播的确定性接缝测试。全进程隔离 UNVERIFIED 不列为已完成能力。

## 独立复核后状态

独立记录见 reviews/development/streamline-codex-development-environment-independent-review.md，结论 FAIL。R1：AGENTS.md 实际加载链缺失，4.5/5.2 重新打开（normal 功能运行仍成功）；R2：重放手册准备命令与宿主来源绑定要求不一致，治理测试仍断言旧文案，2.1/5.1 重新打开（历史执行事实保留）。5.3/5.4 的有效证据不撤销。6.2 已执行但未通过，保留未勾选；6.3 不申请。未自动修复、补测、归档或推送。

## R1/R2 获批限定修复后状态

见 `reviews/development/streamline-codex-development-environment-r1-r2-fix.md`。
R2 手册入口与治理测试已同步；R1 新运行已加入真实 AGENTS 读取、invocation/版本/事件绑定和完成检查重验。
25 项聚焦确定性测试与 OpenSpec strict 均通过，2.1/5.1 恢复完成，当前 15/19。
4.5/5.2 仍缺新加载逻辑的真实宿主 normal 证明，不把合成事件或旧 normal 当作该证明。
6.2 等待证据齐备后限定复核；6.3 等待最终人工批准。旧 Replay 仅按旧锁证明其执行能力，不需为本次两项修复自动重跑。
未调用模型、未改写历史证据、未归档或发布；全进程源码强制只读继续 UNVERIFIED。

## 最终人工批准（当前状态）

2026-09-09：新增宿主 normal `host-normal-9fb6a10a-66f7-4038-bb1b-b434c455ce73` 已通过；Dalton 限定补充复核关闭 R1/R2，CHANGE_REVIEW 为 PASS。用户随后明确“批准”，关闭 4.5/5.2/6.2/6.3，当前 **19/19**。前述计数与缺口是历史记录。
独立补充记录：`reviews/development/streamline-codex-development-environment-independent-review-final.md`。
人工批准及完整源码/证据标识：`reviews/development/streamline-codex-development-environment-approval.md`。
CANDIDATE_PROMOTION 仍为 NOT_PROMOTABLE；全进程隔离仍为 UNVERIFIED。本轮只记录完成，不归档、提交或推送。
