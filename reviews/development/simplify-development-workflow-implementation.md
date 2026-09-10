# simplify-development-workflow：限定实施记录

## 授权与范围

用户于本次对话明确批准规划并授权 apply；不是最终完成批准。纳入其最后澄清：保留 Sol 常规开发、Astra 复杂分析、Terra 产品开发期 LLM 测试分工和成本控制；开发子 Agent 按职责与已有配置，Reviewer 按实际生效配置，不承诺自动跟随主会话。仅移除手动开发选模的产品 dispute_id/批准凭证前置和根开发默认值等于产品 development_default 的断言。

使用 openspec-apply-change，在批准白名单内实施。受保护的两个开发配置通过宿主授权仅修改 Reviewer 描述/指令。未删除、修改任何模型设置，未修改产品路由、预算、权限或锁。

## 证据与 Task 映射

| Task | 实际证据 | 结果与适用范围 |
| --- | --- | --- |
| 1.1 | [现场记录](simplify-development-workflow-baseline.json)、[保留核对](simplify-development-workflow-checks.json) | 149 项既有差异；148 文件完全不变，共享测试除本次三行模型接缝外还原后 hash 等于原值；index 未变。只保护工作现场，不是产品版本锁/晋升门禁 |
| 2.1 | checks.json 的 AGENTS.md/workflow.md 增量与完整 hash | 连续实施、真实阻断、三层检查；保留安全、预算、apply、人工完成批准与 scoped commit/push |
| 2.2 | environment.md 增量；产品 model-routing.json/model_routing.py 和 dev_eval 原 hash 对照 | 只改模型/诊断适用文字；路径、代理、权限章节不变，产品 dispute 路由校验仍保留 |
| 2.3 | 两份 TOML 增量、解析及去除授权字段后的结构比较 | 根配置仅 Reviewer 描述改变；角色仅描述/指令改变，read-only 保留；实际 Reviewer 模型未经观测不得从文件推断 |
| 2.4 | checks.json 的实际命令与完整 unittest 输出 | 8/8：6 项配置/链接/边界检查，2 项原有产品模型策略检查；没有大段中文逐字断言 |
| 3.1 | [限定校验](simplify-development-workflow-validation.json)、checks.json 完整命令、hash、增量 | OpenSpec strict 与限定 diff 空白检查通过；无白名单外新差异，无产品/股票/历史证据/锁变更 |
| 3.2 | 独立 Reviewer 记录，完成后单独落盘 | 只读本次规格、增量与底层证据，不启动产品或完整 Gate |
| 3.3 | 尚未取得最终人工批准 | 保持未完成；apply 批准不能代替 |

实施文件快照：`d68cd0c22766864d52aa3d3ac16eacf7f5e268f1e711457be16aa3bcdd7fea9e`，计算方式为 checks.json 中 implementation_hashes 按键排序、紧凑 JSON 的 SHA-256。各文件完整 SHA-256 和本次增量均在同一记录，可直接复核，不只依赖 PASS。

现场记录 SHA-256：`e685cbbfb647236c9a42d195ea9d61ed46aa7965f9f62ae83371d56a1167bc20`。记录包含已有股票 hunk，未来提交共享测试只能暂存本次模型接缝，禁止整文件夹带。

## 检查边界与保留状态

- 测试使用独立 TMPDIR；命令和 stdout/stderr 合并输出保存在 checks.json。本轮 8 项无断言失败或测试环境错误。
- 实施记录收集曾因工具输出过长导致 JSON 读取失败，改为限定读取后成功；一次规划补丁因整行匹配失败，按原段落修正后成功。均非产品/测试失败，无产品重试。
- 配置测试只证明 TOML、链接、关键权限标记与结构；文字检查不是权限执行证明，更不证明 Agent 永远遵循规则。模型可用性、产品实际加载与全进程源码隔离均未验证；既有全进程强制只读仍为 UNVERIFIED。
- 不执行产品 LLM、Smoke、Replay、Regression、Calibration、Ablation、Promotion 或完整 Gate；不安装依赖、不修改系统代理。
- 股票 Change 保持暂停 19/24，Tasks 2.6、5.2–5.5 未完成。现场记录列出的股票证据仅用于恢复定位，不作为本 Change 通过或股票验收通过的证明。
- 本次 Change 通过不代表 Promotion PASS，未触碰生产指针。未归档、暂存、提交或推送。最终人工批准与规定收尾完成后，才重读新规则、原股票四类规划并恢复未完成任务。
