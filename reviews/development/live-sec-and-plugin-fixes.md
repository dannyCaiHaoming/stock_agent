# 真实取数与插件加载接缝修复

Change：`us-equity-live-advisory-slice`。本记录不是 Change 完成批准，也不是 Promotion PASS。

## 实际结果与根因

1. HTTPS：复用系统信任并显式加载已锁定的 certifi CA；SEC、NASDAQ 与备用 urllib transport 保持证书/主机名校验、原域名、禁止跳转和请求预算。错误按 TLS/DNS/连接/超时分类，TLS 不盲目重试。Yahoo 实际主行情成功，SEC mapping、submissions、companyfacts 与选定披露均返回 HTTP 200。
2. SEC 申报目录：真实响应有 1,001 条记录，其中 801 条包含合法 XSL 目录。旧解析器仅接受文件名。现允许一个 `xsl…/` 展示目录，保留原路径；穿越、编码斜杠、任意子目录、绝对 URL 仍拒绝。实际下载允许的文档类型/URL 没有扩大。
3. 证券身份：MSFT 10-K 同时登记普通股及两项同符号定息债券。现排除明确的百分比 Notes/Bonds 到期标题，再要求唯一普通股 context。未知类型、ADR、优先股、多个普通股 context 仍拒绝。
4. 真实单股已冻结 345 条数据，Gate 允许 96 条（88 财务、4 派生、2 披露、2 价格），排除 249 条非近期完成时段价格。真实双专业 Agent 执行，但已安装插件缓存只有 fixture 工具，报告 `LIVE_EVIDENCE_QUERY_UNAVAILABLE`；后续因 `UNGROUNDED_CHALLENGE` 进入 `FAILED_VALIDATION`，不能算研究通过。
5. 按本地插件更新 Skill 刷新缓存后，零模型实际调用又证明批准文件定位依赖仓库外层 docs，安装包中不存在。现将同一原批准作为插件资源 `product/mcp/live/personal-research-approval.json` 打包并纳入 live 资源锁；与开发原记录逐字节一致，不产生新批准、不修改历史记录或上游状态。缺失与篡改继续拒绝。
6. 同步 live Skill 参考说明到已批准的 4.0.0 双状态契约。已安装版本 `0.3.0+codex.20260910113002` 与仓库 MCP、适配代码、批准资源 hash 一致，从安装包目录执行真实 stdio query 已返回匹配 Evidence。此为确定性工具接缝证明，不是 Agent 加载/研究成功证明。新增模型执行必须使用新宿主会话，不能复用旧会话工具集；更新流程参考 [官方插件文档](https://learn.chatgpt.com/docs/plugins) 及本机 Plugin Creator Skill。

## 验证与复用

完整命令、原始工具响应、版本与文件 hash 在 [机器可读证据](live-sec-and-plugin-fixes-evidence.json)。63 项 HTTPS/来源接缝在解析修复前通过；随后 40 项覆盖 SEC/身份与采集，22 项覆盖产品配置/profile/宿主，20 项覆盖随包批准与受影响接缝，均无 skip。不能将重叠测试数量相加当成独立案例总数。

插件/Skill validator 起初缺 PyYAML，记录为环境缺依赖而非产品断言失败；外置安装开发校验依赖后，两项 validator 实际通过，未改 live 依赖锁。OpenSpec strict validate 通过。未运行完整 Gate/Regression/Calibration/Ablation/Promotion。

## Task 映射与未完成范围

- Task 2.2：目录 XSL 路径真实响应重解析及正负测试；Task 2.1：同符号债券与普通股识别修复。
- Task 2.4、5.1：HTTPS、失败分类、保持限额/拒绝语义的接缝测试。
- Task 1.3、3.1、3.2：原批准记录随包资源及完整性、安装包实际 Gate 查询；不能替代真实 Agent 调用证明。
- Task 4.3：Skill 参考说明版本和双状态语义同步。
- Task 2.6、5.2：已存在真实 Yahoo 来源选择和冻结数据，但完整研究验收仍未通过，不勾选。
- Task 5.3、5.4、5.5：三股、独立复核、最终人工批准未完成。

失败原包 `/private/tmp/stock-agent-live-sec-identity.1l1LBQ/run` 保留。安装包零模型接缝目录是 `installed-mcp-seam`（失败）与 `installed-mcp-fixed`（成功），不得拿它们冒充真实 Council。缓存、联系信息、cookie 和会话均不提交 Git。全进程隔离仍为 UNVERIFIED。

## 获授权的修复后补跑：仍未通过研究验收

通过授权的现有宿主 launcher 执行新运行 `live-8745812b-d1ae-4b60-aae8-7a07535df396`，目录 `/private/tmp/stock-agent-live-plugin-fixed.pNoBOb/run`。使用新插件 `0.3.0+codex.20260910113002` 和新模型会话，数据缓存复用、cutoff 重新冻结；没有改写之前失败包。

- 数据采集/冻结与 PIT 通过。真实 Analyst、Skeptic 各成功执行一次 `live_evidence.query`，各取得 11 条证据，并保存研究报告；之前一次空查询和一次错误 ID 被拒绝，不隐藏这些错误。
- Analyst 初稿多出顶层 `evidence_refs`，触发已有一次格式修复。修复删去该字段，但还改写/删减 `claims[0].statement`、`claims[5].statement`、`uncertainties[2]`，改变事实原子 hash；Validator 拒绝为 `FORMAT_REPAIR_ADDED_FACT_CONTENT`。错误名不表示已证明新增外部事实；具体问题是改动超出 FORMAT_ONLY 边界。
- `terminal_state=FAILED_VALIDATION`、`failed_stage=SPECIALIST_VALIDATION`；宿主退出码 5，源码完整性为 true。CIO、Risk、decision/report/语义 Eval 未完成，不能申请人工完成批准，也不进入三股。
- launcher 另记录 `SKILL_LOAD_PROOF_MISSING`，不能盖过 `run_error.json` 与实际事件中的首个失败原因，也不能据此重新归因为网络失败。失败阶段的下游执行证明尚未齐全。
- 完整命令、当前源码/资源 hash、底层文件 hash 与实际 MCP 事件见 [补跑证据](live-plugin-fixed-smoke-result.json)。按 Task 5.2 不自动再次启动付费运行；后续仅针对纯格式修复越界处理，不放宽 Evidence/事实校验或改写此次输出。
