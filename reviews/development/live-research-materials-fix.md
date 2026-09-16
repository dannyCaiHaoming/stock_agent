# Live 研究材料与 CIO 失败终态修复

Change：`us-equity-live-advisory-slice`。本轮按恢复 apply 授权处理普通实现错误；不更改数据准入、代理、原生权限、Risk/PIT 或历史包，不启动模型和完整 Gate。

## 根因、修改与证据

| 问题 | 实际修复 | 证据及限制 |
| --- | --- | --- |
| SEC 正文标题被 HTML 文本节点拆开，旧规则只读到目录；正文中的 Item 引用和页眉又被误作章节终点 | 标题匹配接受单词内部空白及拆分撇号；裸页眉和正文引用不再自动切断章节。原文、字符范围、截断及总量上限保留 | 历史真实文档原 hash 核对通过。原来只有 63/25 字符目录条目，现在另有 Business 7937、Risk 7975、MD&A 3901 字符正文；总计仍受 20000 字符限制，明确不是完整财报 |
| 相同财务值在不同 accession 重复披露，合法比较被误判为多候选冲突 | 数学比较结果一致时保留每对派生结果及各自原始父 ID/hash；金额按 Decimal 比较，不合并来源。不同值仍记歧义、不静默择一 | 原快照已选的 88 条 financial metadata 离线处理得到 41 个有父证据的比较；仍有一项不可比缺口。未扩大每组 8 条输入上限、未隐藏截断；不是全量原始 companyfacts 重采集证明 |
| prepare-cio 的缺依赖异常没有持久化合法失败，运行只留下半成品 | Specialist 资源验证和 live CIO 上下文准备分别捕获预期导入/上下文错误，保存 FAILED_VALIDATION、实际失败阶段和明确 code；无建议且不伪造 Risk lineage | 注入 PackageNotFoundError 和上下文 hash 错误，验证 CLI 非零、无 decision/report、Risk 前 Trace 合法。沿用先前 sys.executable 修复，尚无其新版真实运行证明 |

解析器版本 `sec-sections/0.3.1`，采集版本 `live-collection/3.0.1`；仅影响未来 live 运行的实际发现版本，不重写历史版本锁或生产指针。原型目录截断/缺失指标等信息仍保留，研究是否充分由真实 Agent 和绑定的语义 Eval 判定，不用正文长度判投资能力 PASS。

最终同一实现上的 90 项受影响确定性测试 PASS，OpenSpec strict validate PASS。完整命令、日志、12 个相关文件 SHA-256、原始材料 SHA-256 与离线处理结果见 [机器可读证据](live-research-materials-fix.json)。测试包含合成角色输出，只证明契约接缝，不代表真实 LLM 研究已完成。独立 TMPDIR 位于仓库外；未运行全量 Regression、Calibration、Ablation 或 Release Gate。

## 尚未授权的派发设计调整

历史 `live-1e90843c-71d3-4fb8-9747-afd6c0420f4e` 的两位 Subagent 生命周期实际存在，但缺少两次 PreToolUse 派发记录，不能认定派发前门禁生效。官方 [Hooks 文档](https://learn.chatgpt.com/zh-Hans/docs/hooks) 明确部分专用路径不经过默认工具 Hook；SubagentStart 可添加开发者上下文，但不能阻止子 Agent 启动。

已向用户提出限定选择：使用真实 SubagentStart 注入确定性冻结输入并绑定 hash，再通过现有 MCP/输出/终态校验验证；仍保留可触发的 PreToolUse，但不再以其覆盖全部派发为完成保证。缺失绑定仍 fail-closed。该方案**待批准、未实现**，不得把它写成已有保证或视为本轮已获验收豁免。全进程隔离继续 UNVERIFIED。

## 任务与停止边界

- 本轮证据支持既有 Tasks 2.2、3.2、3.5、5.1 的受影响修复；不扩大旧完成项的证明范围。
- 2.6：仍需与新版真实研究串联的行情主备锁及报告证据。
- 5.2：待派发方案批准、实现与接缝验证后刷新现有插件，执行一次受限宿主单股运行和真实语义 Eval；本次不消耗模型做已知必失败的补跑。
- 5.3：单股通过后，最终候选锁下执行一次三股批次。
- 5.4/5.5：底层产物齐全后的独立复核与最终人工完成批准。

完成度保持 19/24；未勾选新完成项，不归档、不提交、不推送。批准派发调整不等同于批准 Change 完成，也不自动扩大模型运行预算。
