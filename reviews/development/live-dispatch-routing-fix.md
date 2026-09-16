# Live 派发匹配与输出类型接缝修复

Change：`us-equity-live-advisory-slice`。2026-09-10 用户授权继续打通流程；本轮只修派发、契约提示及错误传播，不改数据源、代理、原生权限或业务判断。

## 修复与限定证据

| 观察到的问题 | 本次修改 | 证明边界 |
| --- | --- | --- |
| 历史运行有 SubagentStart/Stop，却没有 PreToolUse 派发记录；启动配置仅匹配 `^collaborationspawn_agent$` | 省略 PreToolUse matcher，让既有记录器分类调用；普通工具不保留参数，缺失固定角色的已知派发调用明确拒绝 | 启动 TOML 解析与工具别名正负测试通过；真实派发覆盖仍须看本次事件 |
| 两份历史报告把 confidence 写成字符串 LOW | 从本次 output_schema 提取 required 字段和 confidence 类型/上下界，作为消息中的 contract_checks；明确禁止标签、带引号数值和事后推断数值 | 不设置投资置信度；原 Schema、Validator、格式修复边界未放宽；各角色数值正例与字符串/null/bool/越界负例通过 |
| 大批读取文件造成 Schema 上下文截断 | 父线程指令明确逐文件完整读取，不以 `/dev/null` 读取作为上下文证明 | 指令不等于生成时结构化约束；本次未发现可靠依据可给原生 Subagent 添加 `output_schema` 参数，因此未虚构该接口 |
| SPECIALIST_VALIDATION 失败被下游 Skill proof 缺失掩盖 | 对 FAILED_VALIDATION 优先读取与 Trace 的 run/stage/state 一致的 run_error，保留原始 code/message | 只改诊断优先级，仍非零失败；错 run 错误记录不能冒充当前原因 |

Hook 匹配依据：[官方 Hooks 文档](https://learn.chatgpt.com/zh-Hans/docs/hooks)。官方说明省略 matcher 匹配全部受支持事件，spawn_agent 也匹配 Agent；部分专用路径不经过默认 Hook。因此不把这次改动当作全进程强制隔离，ISOLATION 仍 UNVERIFIED。

实际命令、61 项完整测试日志、被测文件 SHA-256、OpenSpec strict validate 和插件校验结果见 `live-dispatch-routing-tests.json`。其中 test_runtime_ablation 是离线 unittest，不是重新执行产品 Ablation。适用于 Tasks 3.2、3.5、5.1 的派发与输出契约接缝，不能替代 5.2/5.3 的真实研究。

测试后只刷新插件 cachebuster 与对应 manifest hash；运行代码不再修改。安装版本 `0.3.0+codex.20260910125707`，四个运行接缝文件在安装缓存与工作树的 hash 逐一一致。使用新宿主会话接收更新资源，不要求当前开发会话充当产品 CIO。

## 单次真实运行

本轮仅一次，外置目录 `/private/tmp/stock-agent-routing-smoke.0M4BLk`；使用已批准个人研究访问配置、合成数量/现金、现有外置缓存及宿主 launcher。保留缓存首次 retrieved_at，不改历史运行。

- run_id：`live-1e90843c-71d3-4fb8-9747-afd6c0420f4e`。
- 模型：`gpt-5.6-terra`。
- 启动前受保护运行源码快照：`77f49db1e8b874134b172dda9c0a75c8626f4db45ae076972990d78dbe126561`。该 hash 的精确文件集合在实际 environment/process manifest，不声称覆盖所有仓库文件。
- 实际运行 560.33 秒，内层退出 0，宿主退出 5；launcher=FAILED，Trace 没有合法终态。没有 CIO、Risk、decision/report/native Eval，也没有 run_error.json。内层最终文字声称 FAILED_VALIDATION 不能代替持久化终态。
- 两位 Specialist 均有独立 Start/Stop、成功 MCP query；Analyst 额外完成 calculate。两个身份正确、置信度分别为 0.34/0.24；只读调用原有两份报告 Validator 均通过，每份 7 个引用且无悬空。未执行语义 Eval，不把报告状态 INSUFFICIENT_EVIDENCE 当作研究验收通过。
- FIRST_DIVERGENCE（输入检查）：19 条 PreToolUse 均为非派发调用，工具集合含 Bash、apply_patch、collaborationwait_agent 和 live MCP，但不含两次 spawn。生命周期 Start 真实存在。因此省略 matcher 仅解决了普通工具观察，**没有关闭派发前校验**；是当前真实工具路径与默认 Hook 覆盖不一致，不能再通过猜别名重试。
- FIRST_FAILED_COMMAND：主线程的 `python3 -m product.runtime.cli prepare-cio ...` 退出 1，原始 traceback 为 `PackageNotFoundError: exchange-calendars`。宿主已使用包含依赖的虚拟环境，但登录 shell 的裸 python3 落到系统解释器。运行不是停在网络，也不是本次 confidence 非法。
- launcher 的 SKILL_LOAD_PROOF_MISSING 是尚未完成执行证明的下游缺失，不是这次第一个失败原因。本轮增加的 run_error 优先级只适用于实际存在且与 Trace 一致的错误记录，不能覆盖这次 CLI 未捕获依赖异常、没有 run_error 的分支。
- 两份报告还明确标记 FINANCIAL_SELECTION_TRUNCATED、DISCLOSURE_HISTORY_OR_EVENTS_TRUNCATED 等缺口；未证明已取得 Design 7 要求的完整研究基础，不能承诺运行到终态就足以关闭研究验收。

完整命令、输入 hash、候选版本、受保护源码前后快照、事件及 23 个实际产物 hash 见 `live-dispatch-routing-smoke-result.json`。候选版本对象 hash：`10827260ff4a76bce145aaa90b5e718192be2af16d40075f47a8dd4e553ef2f7`。源完整性在这次运行中未变；这仍不是全进程隔离证明。

## 运行后的确定性修复（不改写本次失败）

将生成指令中的确定性内部 CLI 从裸 python3 改为启动器的 `sys.executable`，正确 shell 引号处理，不 resolve 虚拟环境符号链接到基础解释器、不修改 PATH 或代理。33 项受影响离线测试及 strict validate 通过，完整日志和新增文件 hash 见 `live-runtime-python-seam-tests.json`；包括路径含空格、普通与 defer-finalize 两种指令分支。没有重新调用模型，也没有在历史 run 上继续 prepare/finalize。

这项修复尚无真实补跑证明；当前已安装插件是上次 Smoke 的版本，下次运行前需刷新现有插件缓存。旧运行不能证明这项新修改。剩余核心工作是解决已证实的派发 Hook 覆盖缺口及相应真实执行证明，而不是再次修改代理或重复猜测工具名。

任务 2.6、5.2–5.5 保持未完成；未归档、提交、推送或修改生产版本指针。
