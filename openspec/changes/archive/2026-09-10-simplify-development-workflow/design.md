## Context

动机见 proposal.md。本轮只读盘点发现：

| 位置 | 已有机制 | 本次缺口 |
| --- | --- | --- |
| 根 AGENTS.md | 三平面边界、聚焦测试、宿主入口、条件读取 | 没有明确授权内持续实施和阶段汇报不结束任务 |
| docs/development/workflow.md | 证据复用、Change/Promotion 分离、人工批准和 scoped commit | 缺少日常开发层及普通错误/真实阻断的明确处置；容易把验收准备当作每步前置 |
| dev_reviewer.toml | read-only，禁止投资决策、账户修改与生产晋升 | 无条件要求晋升人工批准，职责描述未区分评审类型 |
| environment.md 模型节 | 指向 product/model-routing.json，强调实际模型不由 Prompt 切换 | 将产品路由中的争议 ID/批准约束推广到手动开发会话 |
| tests/test_development_environment.py:ModelConfigurationTests | 保留产品路由拒绝与 dev_eval 模型验证 | 一个测试强制根开发默认模型等于产品 development_default；需移除这一跨平面断言，保留其余产品验证 |

股票 Change `us-equity-live-advisory-slice` 暂停在 19/24；Tasks 2.6、5.2、5.3、5.4、5.5 未完成。最新记录为 `reviews/development/live-dispatch-routing-fix.md`：双专业报告已通过只读 Validator；派发 Hook 覆盖、Python 绑定修复的真实补证及研究材料充分性尚未完成。该记录仅是恢复线索，不在本次重审或修复。创建规划时已读取并记录 149 个既有未提交文件的 hash，禁止借小 Change 清理或提交这些工作。该记录仅用于保护工作现场，不新增产品版本锁或晋升门禁。

## Goals / Non-Goals

**Goals:** 用少量现有文档定义持续推进、分层验证、范围化 Reviewer 和手动开发模型选择；以少量静态/确定性检查证明规则一致，并安全保留暂停工作。

**Non-Goals:** 不建立工作流执行器、自动批准系统、新探针/Agent/Skill 或测试平台；不改变 OpenSpec 显式 apply 与人工完成批准。开发模型自由不意味着改变产品路由/费用预算或运行模型锁；不证明模型可用性、真实加载或全进程隔离。

## Decisions

### 1. 三层流程集中在既有 workflow.md

| 层次 | 默认动作 | 何时停止 |
| --- | --- | --- |
| 日常开发 | 授权内实现、普通错误修复、受影响聚焦测试；阶段消息后继续 | 已完成授权目标，或需要新权限、用户关键选择、范围变更、不可在现有约束内解决的外部依赖等真实阻断 |
| Change 验收 | 按当前 Specs/Tasks 收集有效证据，针对缺口补验，独立差异复核 | 等待人工完成批准；证据未齐不能宣称完成，但可继续授权内修复 |
| 版本晋升 | 执行完整既有安全、测试、评估和人工晋升门禁 | 任一晋升门禁失败，停止晋升；不能因此阻止无依赖的日常开发 |

不添加第四层或新的机器状态协议。根文件只给连续实施原则及入口链接；详细分类只维护在 workflow.md。阶段汇报使用 commentary，不能仅因“做完一个步骤”“需要运行已授权聚焦测试”而结束任务等用户回复。普通错误如导入、路径、类型、断言失败在既定范围内自行修复；失败仍原样保留，不以继续工作为由绕过校验或改写历史证据。

涉及新权限时使用宿主提供的授权机制；不把允许持续实施解释为无限 LLM 重试、购买、系统配置修改或越过旧 Change 的次数/来源限制。仅授权诊断时仍不实施修复。遇真实阻断只暂停依赖它的步骤，其他已授权且无依赖的工作可继续；必须给出具体缺口及最小用户动作。

### 2. Reviewer 按当前目的复核

在 `.codex/agents/dev_reviewer.toml` 的描述和开发指令中区分“日常差异复核 / Change 验收 / 候选晋升”，根注册描述同步。未明确请求晋升时不得默认要求 Promotion PASS 或生产批准；安全检查针对实际影响面，发现相关安全缺陷仍报告阻断。

保留 read-only 和现有禁止权限，不启用写源码或产品执行权限。Reviewer 默认读差异、规格、已有证据；必要补验列明理由交主开发处理，不自行启动产品、完整 Gate 或沙箱。报告可先返回主线程；需要落盘由已有授权的开发主线程完成，不为评审创建额外权限机制。

### 3. 开发模型由用户选择，产品路由保持原样

环境文档保留 Sol 常规开发、Astra 复杂分析、Terra 产品开发期 LLM 测试分工与成本控制；用户明确指定时尊重主会话选择，不要求产品 dispute_id/批准凭证。开发子 Agent 按职责和已有配置选模，Reviewer 使用自身实际生效配置，不承诺自动跟随主会话。不会自动修改根 model 值、用户配置或当前会话模型，也不声明改 Prompt 能切换模型。界面/CLI 手动选择已有官方支持，参见 [OpenAI 官方 CLI 文档](https://learn.chatgpt.com/zh-Hans/docs/codex/cli)；本 Change 不验证账户具体模型可用性。

`product/model-routing.json`、`product/runtime/model_routing.py`、dev_eval 的真实 Runtime Eval 路由及锁保持原样。其 `architecture_dispute` 路由的旧显式调用校验不删除，也不再作为开发会话选择模型的前置。环境模型段必须直接注明这一适用边界，避免形成两套产品模型策略。

只调整 ModelConfigurationTests 中“根开发默认值必须等于 product development_default”的断言，保留产品 route 拒绝和 dev_eval 配置的测试。不采用修改产品策略并重生成所有锁的方案。

### 4. 最小交付和检查

实施白名单：

- `AGENTS.md`：短原则、分层检查与条件读取，保留金融/隐私/发布安全边界。
- `docs/development/workflow.md`：连续实施、普通错误与阻断、三层检查、当前人工收尾和恢复步骤。
- `docs/development/environment.md`：仅开发模型和诊断适用范围的必要同步，路径/代理/产品权限不改。
- `.codex/agents/dev_reviewer.toml`：只调整评审职责与条件，不改权限；`.codex/config.toml` 只改 dev_reviewer 注册描述。
- `tests/test_development_workflow.py`（新增）：以相关文件链接、Reviewer TOML 解析、模型配置结构与只读禁止项正负样例为主；三层规则、人工批准和选模适用边界通过差异复核确认，不用大量固定中文措辞逐字匹配。不把文本匹配称为真实 Agent 行为证明。
- `tests/test_development_environment.py`：仅上述跨平面模型断言的隔离修改。
- 本 Change 规划、`reviews/development/simplify-development-workflow-*.md/json`：有限验证、独立复核与人工批准记录。

仅运行新测试模块和受影响的 ModelConfigurationTests、TOML/链接检查、OpenSpec strict validate；不默认运行整套已有环境测试，更不启动产品 LLM 或完整 Gate。一个未改的启动/产品文件不会因文档改写产生新的真实 Smoke 验收要求。本次开发 Reviewer 文案与注册描述更新只验配置一致性，不宣称产品运行资源加载成功。

### 5. 保留、限定提交与恢复

实施前保存既有差异清单，特别标记已经被股票 Change 修改的测试文件。不要 stash、reset、restore、改写股票 Tasks 或删除未跟踪文件。独立复核只看本次增量；不把未完成股票代码计入该 Change 的验证或批准范围。

人工完成批准后按原流程同步主规格、归档并提交本 Change。使用文件白名单；重叠测试文件只能按本次 hunk 暂存，复核暂存 diff 与工作树剩余差异。不能使用 `git add .`，不能因路径在白名单就把同文件的股票修改一起提交；不能安全分离时停止发布并说明具体 hunk。已有不相关暂存内容保持原样，必须采取隔离本次提交的方法，不能直接整份 index 提交。

本次新增主规格变化只限两个开发治理能力，不改股票 delta specs 或产品版本锁。收尾输出 commit/push 与保留差异，再重新读取更新的 AGENTS.md、workflow.md 和原股票 Proposal/Specs/Design/Tasks，恢复未完成任务。恢复后若开发指令/config 的 hash 被旧真实运行锁覆盖，按实际差异标记证据适用范围，不补写旧锁、不为了复用而伪造等价；该问题留给原股票任务处理，不扩成本次运行验收。

## Risks / Trade-offs

- [持续推进被误解为扩大权限] → 明确 apply、范围、预算、权限和人工完成批准仍独立；仅诊断不带修复授权。
- [文本变少却漏掉硬安全要求] → 保留业务边界与晋升条款，逐项文档/Reviewer 一致性复核；不删除 Risk/PIT 或当前股票验收条件。
- [模型手动选择被误用来修改产品锁] → 不改产品路由/锁，测试只删除开发默认值与产品策略的错误绑定。
- [共享脏工作树夹带股票实现] → 保留基线、仅审本次增量、逐 hunk 暂存并检查暂存内容；不能分离即停发布。
- [静态规则不能保证未来 Agent 永不误判] → 只报告文档/配置一致性，不启动行为评测平台或宣称隔离证明。

## Migration Plan

规划 → 显式 apply → 修改白名单文件 → 有限确定性检查 → 独立本次差异复核 → 人工完成批准 → 主规格同步/归档 → scoped commit/push → 重读规则并恢复股票 Change。小 Change 未批准收尾前不自动恢复股票功能。归档、敏感信息或已审阅范围检查失败时只停相关发布，不回退股票代码或扩展修复范围。没有数据迁移、产品部署或生产指针更新。
