# 产品交付优先：本轮实施结果

本记录不是 Change 完成批准。范围依据 `live-product-focus-approval.md`；保留历史任务及全部失败包，不归档、不提交、不推送。

## 已实施

- 新 live v2 派发不比较自然语言消息全文，不要求 Specialist 回传 context_receipt。角色、独立上下文、实际启动、冻结输入及 MCP 绑定仍校验。v1 保留原验证语义。
- NASDAQ 目录明确可用性故障只停止目录请求；已知持仓仍须通过行情/SEC 独立身份校验。损坏原文、身份冲突、来源准入、PIT 和 Risk 不放宽。
- 当前任务清单与历史记录分离；更新运行说明，复用现有研究 Skills 和宿主入口。
- 实际运行后修复两处直接接缝：外层 stdout/stderr 改存批次的 `launch-logs/<run_id>/`，避免封存后日志写入使子 Trace 漂移；live 主线程不再重复完整读取 Specialist 的准备包，由既有交付机制提供材料。

## 测试与版本范围

完整命令、输出和文件 hash 在 `live-product-focus-tests.json`。

| Task | 本轮证据 | 适用边界 |
| --- | --- | --- |
| 3.2 | v1/v2 上下文正负测试；实际双 Agent Start、MCP 查询和执行证明 | 实际运行证明专业研究与 CIO 调用，不证明最终决策通过 |
| 3.5 | 目录403/超时继续、损坏与身份冲突拒绝；宿主/批次失败传播；封存后外层日志写入测试 | 最新日志落点仅确定性验证，未再启动模型 |
| 4.3 | 当前任务、Design、数据规格和运行说明同步；OpenSpec strict validate | 不改历史证据或上游许可状态 |
| 5.1 | 运行前79项通过；运行后两处接缝48项通过；插件验证通过 | 两组有重叠，不能相加为127个独立案例；合成事件不是实际LLM证据 |
| 2.6、5.2 | 真实采集和研究已执行，但 CIO 引用失败 | 保持未完成，无最终报告、Risk 或实际语义Eval |
| 5.3–5.5 | 未执行 | 单股未过，不启动三股/独立收尾或勾选人工批准 |

单股运行源码快照：`30fc2edeac6616ebd9c18607748d70c08343a62ff976d2db973ceb72c262b5a9`。
candidate lock canonical hash：`89f95cf456b50997b4ec3d5f01f12b4e1bcd0cfbbc158858a9c6e7b0234d1244`。
插件：`0.3.0+codex.20260910155529`；已确认安装的 invocation/Hook 文件与运行前源码一致。
运行后小修复源码快照：`19a6fa19467c91cd67b5577b9f684e4183437f4381f17ff30793821d03f8c30f`。
快照沿用仓库受保护产品文件定义，不代表整个工作区或全进程隔离。后续真实运行前仍须按既有流程刷新插件；本轮真实包不能冒充运行后快照的全链路证据。

79项中目录/路由/输入契约代码在后两处修复中未变，继续适用；受影响的派发 Prompt、宿主批次及关联终态接缝由48项覆盖。此前120项仅按 `live-start-context-tests.json` 的旧版本解释，不证明本轮新增行为。没有运行全套 Regression、Calibration、Ablation 或 Gate。

## 一次真实单股结果：FAILED

底层 hash、运行事件与真实状态见 `live-product-focus-smoke-result.json`。外置包：
`/private/tmp/stock-agent-product-focus.f8Ghth/live-single/batch/runs/live-46da6307-5a1c-4b70-b091-e32d967b20c9`。

- 真实数据冻结、PIT 输入、Skill/Agent 加载、独立 Analyst/Skeptic、实际 MCP、专业报告校验、CIO 综合及执行证明均已发生。
- 两份专业报告形成了具体业务与财务解释、公司特定反证和估值缺口；尚无实际语义评分，不预先宣称研究质量通过。
- FIRST_DIVERGENCE：CIO 草案引用 `ev-yahoo-c5336d9cb5a05e53dbe04b0f076c6c3687d8e7712c350187f78792c127ca88e79`，不在允许集合。相应合法 ID 为 `ev-yahoo-c5336d9cb5a05e53be04b0f076c6c3687d8e7712c350187f78792c127ca88e79`；错误串多了一个字符。此比较只用于诊断，不自动替换或回写草案。
- 终态 `FAILED_VALIDATION`，阶段 `CIO_VALIDATION`，错误 `CIO_VALIDATION_FAILED/EVIDENCE_CLOSURE_FAILED`；未到 Risk，没有 decision.json/report.md/运行Eval或语义Eval。LLM exit=0，launcher失败，宿主exit=5，不能算产品完成。
- 第二处确定性问题：宿主收集 stdout 的文件原先位于子 run 内，内层封存时为空，内层结束后被写入，导致外层检查报 `TRACE_ARTIFACT_UNRESOLVED:host-launch.stdout.log`，掩盖先发生的 CIO 错误。已对未来运行修复落点，旧包不修改。
- 运行中源码完整性未变；不等于强制只读隔离。`ISOLATION: UNVERIFIED`。

## 具体剩余事项

当前产品阻断是 CIO 合法引用的可靠输出，不是数据源、代理或 Specialist 派发。后续应只处理该输出接缝，保留严格 Evidence Closure，不能截断/猜测修复引用或改变投资判断。运行前的准备负担与日志问题已有本轮确定性修复。

本次获批单股尝试已使用，未自动增加付费重跑。下一次真实模型验证需明确续批；单股最终报告及实际 Eval 合格后才进入既定三股验收。当前不具备最终人工完成批准条件，不代表 Promotion PASS。
