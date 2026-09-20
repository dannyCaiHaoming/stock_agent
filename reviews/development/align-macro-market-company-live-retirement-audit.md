# 旧 `live-us-equity` 定向退役审计

审计日期：2026-09-20
审计范围：`prepare-live`、旧 full live Council 创建/派发路径、当前 Handoff 采集复用、历史 Replay/只读读取、对应测试与文档。
恢复基点：实施前基线 commit `2dd25a8b43e5c06b884b70c81016d1c78b485698`；本次没有删除文件或历史产物。

## 结论

旧 `live-us-equity/4.0.0` 不再具有新运行创建入口。公开 CLI `prepare-live` 在读取 portfolio、snapshot、calendar、cache 之前返回 `LIVE_COUNCIL_ENTRY_RETIRED`，并声明 `data_reads=0`、`network_calls=0`、`llm_calls=0`。当前权威入口为已确认 `PortfolioHandoff v3` 驱动的 `common-stock-research` / 多维研究链路。

不能按 `live_*` 名称批量删除。当前 Handoff 链路仍复用旧 live 层中已验证的只读采集、来源标准化、PIT Gate 和冻结记录校验；历史 Replay/trace/eval 读取也仍需校验旧包。此次只退役已证明没有当前生产消费者的 CLI 创建分支，保留共享能力与历史读取。

## 逐项处置

| 符号或文件 | 审计分类 | 当前消费者/证据 | 处置 | 恢复方式 |
|---|---|---|---|---|
| `product.runtime.cli: prepare-live` 分支 | 零当前消费者的旧创建入口 | 宿主入口已拒绝 `--profile live-us-equity`；当前 Handoff 使用 `collect-common-stock-data` / `prepare-common-stock-research` | 改为前置显式拒绝，保留参数解析以给旧脚本稳定错误码 | 恢复基点中的原分支 |
| `product.runtime.run_package.prepare_live_run` | 历史兼容测试构造器 | 仅旧契约/eval 测试直接调用；当前 CLI 已不导入、不调用 | 保留实现并把 docstring 限定为历史包兼容测试；不作为当前入口发现 | 无需恢复 |
| `product.mcp.live.collection.collect_live_snapshot` | 当前生产复用 | `product.runtime.common_stock_data.collect_common_stock_data_from_handoff` | 保留 | 不适用 |
| `product.runtime.live_input.load_live_portfolio`、`freeze_snapshot` | 当前采集复用 | `product.mcp.live.collection` | 保留 | 不适用 |
| `product.runtime.evidence_gate.run_live_evidence_gate` | 当前生产复用 | common-stock 数据装配、研究材料 stage、live MCP 以及若干来源路由 | 保留 | 不适用 |
| `product.runtime.live_context.validate_raw_records` | 当前生产复用 | common-stock 冻结来源校验与 live collection 测试 | 保留 | 不适用 |
| `product.runtime.live_context.load_live_run_context` | 历史只读/Replay | `replay.py`、`trace_validation.py`、`smoke_prompt.py`、`native_eval.py`、`invocation.py` | 保留；不得用于创建新 live run | 不适用 |
| `product.runtime.live_context.source_topology_lock`、`live_resource_hashes`、`live_artifact_hashes` | 历史包完整性 | 历史 context 校验及兼容构造器 | 保留 | 不适用 |
| `product.runtime.live_input.build_live_specialist_inputs` | 历史 Replay/eval 与兼容测试 | `native_eval.py` 和旧包契约测试 | 保留 | 不适用 |
| `product.runtime.live_mcp` | 历史包冻结 MCP | 已存在 run 的只读证据访问 | 保留；当前三域正式入口使用新的多维 stage/fixture MCP 权限集合 | 不适用 |
| `product/profiles/live-us-equity.json` | 冻结历史配置 | 历史 manifest/hash、当前拓扑中的 retired 引用 | 内容不改；状态由新拓扑标记 `RETIRED/COMPATIBILITY_ONLY` | 不适用 |
| `product/skills/portfolio-council/references/live-us-equity.md` | 历史运行上下文说明 | 仅 manifest 明确为旧 live profile 时读取 | 保留 | 不适用 |
| `tests/test_live_cli.py` | 退役入口保护 | 验证输入/网络/模型前拒绝与稳定错误码 | 收缩为拒绝测试；保留 synthetic schema 与 self-check 边界测试 | 恢复基点 |
| `tests/test_live_contracts_gate.py`、`test_live_collection.py`、`test_live_source_routing.py` 等 | 共享校验/历史兼容 | 覆盖当前仍复用的 Gate、采集与历史读取 | 保留，禁止按文件名前缀删除 | 不适用 |
| `docs/data/live-*.sha256`、历史 progress 文档 | 有效历史验收证据 | 记录旧版本的当时状态与 hash | 保留，不改写为当前事实 | 不适用 |
| 未跟踪的真实运行包、私人账户/cookie/原始数据 | 审计排除 | 不属于仓库受控实现；本次未发现并未读取 | 不处理 | 由外部数据所有者管理 |

## 文档与测试收缩

- `docs/product/us-equity-live-advisory.md` 不再声称 `prepare-live` 是可用内部准备工具，明确它在任何数据读取、网络或模型调用前拒绝。
- 保留 `collect-live` 共享确定性采集能力，因为当前 Handoff 数据准备仍复用它；“live”命名本身不是删除依据。
- 保留旧 profile、schema、rubric、Skill 引用和历史测试，以免破坏已存在 run 的 Replay、trace integrity、只读浏览和 eval 读取。

## 产物处置

引用复查没有发现可以同时满足“已跟踪、重复、零引用、非验收证据、可安全恢复”的日志或中间产物，因此本次结论为 **零删除**。不为完成清理任务而制造删除；如果以后发现候选，必须逐路径记录引用查询和恢复 commit 后另行处理。

## 聚焦验证

- `tests.test_live_cli`
- `tests.test_live_contracts_gate`
- `tests.test_live_eval_contract`
- `tests.test_live_host_entry`
- `tests.test_research_input_topology`

上述集合在退役修改后通过；旧 `prepare-live` 的拒绝测试证明没有输入文件读取、网络调用或模型调用。
