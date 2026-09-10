## 1. 保留当前股票工作

- [x] 1.1 在本 Change 的实施记录保存开始时的差异清单、相关文件 hash、原股票 19/24 与未完成 Task IDs、最新证据路径及提交白名单；核对共享测试文件的已有股票 hunk。验证不修改原股票 Tasks、任何产品文件、历史证据或版本锁，不清理未提交工作。

## 2. 精简开发规则与 Reviewer

- [x] 2.1 修改 AGENTS.md 和 workflow.md：授权内持续实施、阶段消息不结束任务、普通错误自行处理、真实阻断暂停受影响步骤，区分日常开发/Change 验收/候选晋升。逐项核对金融业务边界、预算、显式 apply、人工完成批准及 scoped commit/push 条款仍保留；无新增发布级日常前置。
- [x] 2.2 仅同步 environment.md 的开发模型与诊断适用说明：保留 Sol/Astra/Terra 分工、成本控制和开发子 Agent 既有配置，尊重主会话明确选模，不需要产品争议证明；Reviewer 按实际生效配置，不承诺自动跟随；产品路由和真实 Runtime Eval 保持原锁，纯诊断不自动获得修复权限。通过与 Proposal/Specs、当前产品路由的只读对照验证，不修改 model-routing.json、实际模型配置、产品权限或锁。
- [x] 2.3 精简 dev_reviewer.toml 指令并同步根配置中的 Reviewer 描述：按开发差异/Change/晋升目的评审，非晋升任务不默认要求生产批准，不自动启动产品或完整 Gate。通过 TOML 解析和 diff 验证 read-only、禁止投资/账户/生产修改权限以及根配置其他字段语义完全不变；需要写配置授权时只申请本次文件的最小权限。
- [x] 2.4 新增 tests/test_development_workflow.py 的配置解析、链接和关键边界正负样例，不用大量固定中文措辞逐字断言；只调整原 ModelConfigurationTests 中根开发模型必须等于产品默认值的断言，保留 dev_eval 和产品路由测试。仅执行新模块与 ModelConfigurationTests，保存命令、输出、hash；不得导入本次无关修改到暂存范围，不执行产品 LLM、真实 Smoke 或完整 Gate。

## 3. 限定验收与人工批准

- [x] 3.1 归集本次差异与 2.4 的实际结果，检查链接、Reviewer 配置一致性和白名单外文件保留情况；运行 `openspec validate simplify-development-workflow --strict`。验证产品/股票任务/历史证据/版本锁未变，输出静态检查的明确适用边界，不宣称真实行为、产品加载或晋升通过。
- [x] 3.2 由未参与本次修改的独立 Reviewer 只读核对本 Change 规格、实际增量和限定证据，记录 PASS/FAIL、具体阻断及核对范围；不审未完成股票实现、不重新启动产品或完整 Gate。发现本次普通问题交主线程在授权范围修复，不将独立评审变为新一轮平台验收。
- [x] 3.3 提交本次限定完成摘要供用户人工批准；获得明确完成批准后保存批准记录与所引用证据标识并标记本项。确认不是 Promotion PASS，不自动批准股票 Change，也不将当前提案创建请求当作完成批准。

## 4. 批准后的收尾与恢复顺序

本节是人工批准后的发布/交接流程，不作为要求“归档之前先完成归档”的循环前置：

1. 按既有 OpenSpec 流程同步两个开发主规格并归档本 Change；不操作股票 Change 或任何历史归档。
2. 检查本次归档和暂存差异、敏感信息；仅提交批准白名单中的本次内容，共享测试文件按 hunk 分离。不能安全分离、出现未审阅变更或校验失败则停止发布并报告，不自动回退其他修改。
3. scoped commit 并推送既有远端，输出归档路径、commit、push 结果和仍保留的股票差异；不修改生产版本指针。
4. 重新读取更新后的 AGENTS.md、workflow.md 及原 `us-equity-live-advisory-slice` 四类规划文件，按用户已要求的顺序恢复 Tasks 2.6、5.2–5.5。继续适用股票原有来源、真实运行次数、研究质量、安全及人工批准标准；原失败和旧锁不回写。

用户已明确批准本 Change 完成及 Task 3.3，批准记录见 `reviews/development/simplify-development-workflow-human-approval.md`；股票 Change 的验收状态不变。
