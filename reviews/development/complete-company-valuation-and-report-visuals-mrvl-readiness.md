# MRVL 零模型运行门槛

## 结论

`complete-company-valuation-and-report-visuals` 的第 7 组零模型门槛已通过。此次只使用用户确认的 MRVL 冻结输入，不启动模型，也没有消费新的专项模型批次。旧批次仍保持 `HARD_TIMEOUT`，不能被本次确定性检查改写为成功。

## 已验证结果

- Hook 实际使用的紧凑 UTF-8 JSON 为 188,710 bytes，低于 256 KiB 上限 73,434 bytes。包中保留 43 个语义字段组、568 条有期间/单位/上下文的 Evidence 索引；逐日技术序列、完整附件正文和重复白名单没有进入启动上下文。
- `equity_research_attachments.query` 已出现在实际 fixture MCP `tools/list`，实际 `tools/call` 一次读取 `valuation_snapshot`、`valuation_history`、`fundamental_supplement`、`peer_comparison` 四类附件。`visual_bundle` 仍只供确定性渲染，不暴露给模型。
- MRVL 历史估值文件不再缺失。冻结资料不足以构造 PIT TTM EPS，因此它明确记录 `CURRENT_VALUE_UNAVAILABLE / PIT_EPS_MISSING`、0 个有效点和 0 覆盖率；没有伪造历史 PE 或分位。
- 附件查询事件记录实际返回的 Evidence、附件 hash 和三个 `FROZEN_CALCULATION`。报告引用闭合测试同时覆盖冻结计算、本次 `LIVE_CALCULATION`、未实际返回 Evidence 和未实际返回计算的正负例。
- launcher 从隔离的可丢弃源码副本启动；源码写入哨兵证明当前开发工作区不变，隔离副本漂移可被记录并在结束后丢弃。超时使用独立进程组，有界 TERM/KILL 本地父子进程，远端取消状态保持 `UNKNOWN`，不自动重试。
- timeout、nonzero、缺 Stop/报告路径会原子更新 ResearchCoverage v1、stage 和 process；单证券无成功报告时 stage 为 `FAILED`，不再残留 `QUEUED`。

## 证据与限制

机器可读清单见 `complete-company-valuation-and-report-visuals-mrvl-readiness.json`。本轮受影响的运行与附件测试 92 项通过，估值与图表同源测试 38 项通过，OpenSpec strict validate 通过。

这只证明新的真实模型批次已具备启动前条件，不证明模型能够在时限内完成，也不证明历史估值为 AVAILABLE。任务 6.4 仍须新的明确宿主模型授权；失败后不得自动追加重试。
