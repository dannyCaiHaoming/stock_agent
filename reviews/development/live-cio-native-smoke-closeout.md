# 单股真实闭环与语义 Eval：通过

本轮授权见 [续跑批准](live-cio-native-smoke-approval.md)。完整命令、执行标识、源码/输入/输出 hash 和实际检查结果见 [原始证据摘要](live-cio-native-smoke-result.json)。没有重跑 Council 或修改业务实现，只刷新了既有插件安装版本并执行一次单股、一次独立语义评分。

## 实际产物

- Run：`live-7ba28fd5-ede7-4d0a-8e43-45b6e702b5b3`。
- 单股目录：`/private/tmp/stock-agent-cio-native.kmoxeR/single/batch/runs/live-7ba28fd5-ede7-4d0a-8e43-45b6e702b5b3`。
- Eval：`live-cio-native-semantic-7ba28fd5`。
- 语义评分目录：`/private/tmp/stock-agent-cio-native.kmoxeR/semantic-eval`。
- 当前锁：`d16313d1258d716e09eb0650f06438c674154a431720e155113873a8c586373d`。
- 运行前/全部评分后受保护源码快照相同：`6617a8dbf838f940ae904ba4426bfaf8d9df959ce2f9a606a3e3e1996581af4c`。
- 插件：`0.3.0+codex.20260910163141`，安装文件与源码一致；真实运行验证加载，不仅检查文件存在。

## PASS/FAIL 矩阵

| 阶段 | 结果 | 实际证明 |
| --- | --- | --- |
| 数据采集/冻结 | PASS | MSFT 合成持仓；Yahoo/yfinance 主行情及 SEC，唯一冻结快照；NASDAQ 目录明确 PARTIAL |
| Skill、Agent、MCP | PASS | 实际读取、独立 Specialist Start/Stop、MCP 事件和重验通过；模型 Terra |
| CIO 原生输出 | PASS | 实际命令含 --output-schema；最终响应与保存草案逐字相同，未修补 ID |
| 引用与 PIT | PASS | 重验引用9/9有效，无悬空；未来泄漏0 |
| Risk 与终态 | PASS | 一次真实 Risk，APPROVED；SAFE_NO_TRADE；两个 NO_TRADE 执行字段均为 null |
| 最终产物 | PASS | decision.json、report.md、decision_trace.json、eval/result.json 齐全；launcher与宿主均成功 |
| 真实语义 Eval | PASS | 独立 dev_eval/Terra；五维度均通过，有实际评分会话及执行证明 |
| 持久化 Eval 重验 | PASS | 既有 verify_runtime_eval_job 从源 Run、输入、评分和执行证明重新验证，不仅读取 PASS 摘要 |
| 三股/独立 Change 收尾复核/人工批准 | NOT_RUN | 不属于本轮一次单股额度，不冒充已完成 |

单股 Council 用时341.706秒。语义评分为独立作业，不再次生成投资决策；评分子会话 `01a08c31-761e-7d63-8f21-5173579408c2`，协调会话 `01a08c31-0808-71a3-aa5e-850f13a96cbc`，实际均为 Terra。执行证明 hash：`8c9f49a1f3526708e1054471888f7e24a6bdf7f3d2edc46acabbf1ece606de0f`；最终 Eval hash：`3cf2e237e1596df77d34506b111eacc3e320702284f8b9ad7ee2b154ae1433d3`。

## 研究质量与非阻断问题

本次 NO_TRADE 有公司特定业绩事实、RPO转化假设、AI竞争/成本和合作条款反证，并联系完整组合约32.96%的MSFT权重及6–12个月期限，给出可观察的重评条件。这里描述已执行报告，不是针对用户真实持仓的建议。

独立评分：Analyst grounding 2/3，其余四项3/3。降分原因明确保留：一条额外引用 `ev-sec-text-a56831f83e66efc08ab4deb96fb52b96a667e60c36a967c9051724220556b514` 实际只有目录标题，不能支撑相应技术栈/成本优势细节；财务选择和估值输入也有已披露缺口。该 ID 存在，不是悬空引用，但存在支持力度不足。评分依据现行 rubric 判断基本合格，不宣称每个陈述完美有据；不回写报告或改变评分追求满分。

## Task 映射及停止边界

- 2.6完成：最终真实报告的来源选择展示已核对，配合未受影响来源测试与实际 live_source_binding。
- 5.2完成：一次真实单股完整链路、实际语义评分与输入输出/执行证明齐全；不是空泛 NO_TRADE 验收。
- 5.3、5.4、5.5保留未完成：下一步是获批预算下的一次三股批次及各自语义 Eval，然后独立差异复核和人工完成批准。

当前21/24项，不具备整个 Change 的最终完成批准条件。不重跑全套 Regression/Calibration/Ablation/Gate，不归档、提交、推送或修改生产指针。全进程隔离继续 `UNVERIFIED`；源码 hash 未变不是权限隔离证明。原始包、会话和访问配置只保存在私有外置目录，Git记录仅为脱敏摘要/hash，不承诺仅凭Git可重算所有私有字节。
