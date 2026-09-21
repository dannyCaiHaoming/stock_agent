## 1. Coverage 只读适配

- [x] 1.1 在现有固定候选目录与版本 registry 中接入 `audit/provider-coverage.json`，校验 schema、canonical hash、必要结构及 source/run/cutoff 上下文；用聚焦测试证明有效产物被接纳、未知版本/损坏 hash/符号链接和越界文件被隔离
- [x] 1.2 构造 Macro、Market、Company 的字段允许列表 projection，保留 dataset、capability、provider/source layer、security、Capture/Gate/Delivered、实际使用状态、时间、限制和失败码；用测试证明其他证券、其他域及私人/路径字段不会进入页面 model
- [x] 1.3 实现 coverage 版本选择与空状态，确保历史快照/View 只匹配同 source/run/cutoff 的 coverage，旧运行无 coverage 时不退化为零覆盖；用多运行、同 cutoff、错绑定和旧运行样本验证

## 2. 三域页面与 Options 专项

- [x] 2.1 在总览页加入按运行绑定的 Macro、Market、Company 覆盖摘要，不跨运行累加，并将操作文案改为“重新读取本地资料”；用 HTTP 页面测试确认 POST 仍仅触发本地 rescan
- [x] 2.2 在 Macro 页面增加 `MACRO_CONTEXT` 数据集覆盖、来源层和缺口展示，保持官方快照/报告与 Dot Plot、economic calendar、macro history 补充状态分层；用完整和受限样本证明 coverage 不会被渲染成宏观数值或趋势
- [x] 2.3 在 Market 页面分区展示 `MARKET_STATE` 与证券级 `OPTIONS_FLOW` 的数据集及报告，校验 security/run/cutoff/Evidence 绑定；用有报告、已交付未研究、无 Gate Evidence 和证券错配样本证明不产生资金方向推断
- [x] 2.4 在 Company 数据来源区加入与所选 View 精确绑定的数据集交付概览，并保持 Company Agent 报告、四类补充研究和 Options 关联身份互不改写；用切换 View 和他股混合运行样本验证

## 3. 状态语义与可读性

- [x] 3.1 增加复用现有 card/badge/details/table 的 coverage 渲染组件，分别显示 Capture、Gate eligible、Delivered、Actual research use 和报告状态；用快照断言证明 `NOT_EVALUATED_AT_PREPARATION`、`NO_GATE_EVIDENCE`、`SOURCE_LIMITED`、`NOT_ATTEMPTED` 保持可理解且不被合并
- [x] 3.2 控制默认信息密度：域摘要和重要缺口可见，provider/dataset 长表及限制默认折叠，不展示 Evidence ID 长列表；实际查看桌面与窄屏页面，确认导航、长文本、表格滚动和空状态可读
- [x] 3.3 更新本机浏览说明，记录新版支持格式、三域映射、Options 归属、状态边界及“重新读取不联网”；通过文档与页面文案对照检查确认无 OpenD/Provider/模型刷新暗示

## 4. 回归、真实产物与只读验收

- [x] 4.1 扩充 `tests/test_local_research_browser.py` 的合法结构 fixture 与聚焦用例，覆盖三域路由、真实使用状态、旧运行兼容、binding mismatch、未知/损坏 coverage、HTML 转义、私人字段清理和无写入刷新，并运行完整本机浏览器测试集
- [x] 4.2 使用当前 `research-provider-coverage/1.0.0` 冻结运行或其保留的完整结构副本核对页面 dataset/计数/状态：至少验证 Macro 的 dot plot/economic calendar/macro history、Market 的 FedWatch/option statistics、Options 的 snapshot/underlying/vendor flow，以及 Company/ownership/研报数据集；记录输入完整 hash，并明确 preparation 证据不代表实际研究使用或产品 Smoke
- [x] 4.3 对浏览前后的 Memory 与准入运行产物执行完整 hash 对比，并访问总览、三域页面、历史版本和重新读取；确认没有 Provider、OpenD、模型、checkpoint、报告、coverage 或数据库写入
- [x] 4.4 运行 OpenSpec 严格校验和受影响的确定性测试，完成只读独立复核；若复核发现阻断级错绑、状态误报、安全暴露或旧功能回归则修复并重验，不启动 Runtime Eval、Execution Replay 或候选晋升

实施证据（2026-09-21）：本机浏览器确定性测试 32 项通过，OpenSpec strict validation、Python 编译检查与 `git diff --check` 通过。真实 v4 运行的完整文件集合 hash 在浏览、展开、版本导航和页面“重新读取本地资料”前后均为 `8c4bc473f4fe863d3bf8a14cde138c3f5756fcfce0bdaa05bb936e926a14ecf4`；其 coverage 原文件 SHA-256 为 `93d209bf4e1231ccd2b41f7f885a35c9053af4a2166ce01a5ff23b283e008526`，契约内 canonical `coverage_hash` 为 `115028e8fe55767327d055a1eff42fb481b3429ae745f2c2c584b10a05c02e63`。页面实际显示 Macro 3/3 delivered，Market/Options 5/6 delivered（market breadth 为 `NO_GATE_EVIDENCE`），Company 11/12 delivered，并把 v4 `OPTIONS_FLOW` 报告保持为 `SOURCE_LIMITED`；所有 dataset 仍显示 `NOT_EVALUATED_AT_PREPARATION`，仅另列报告 Evidence 引用证明，不将其改写成 preparation 已评估实际使用。v2 运行另验证 Company 四类、Macro、Market、Options 报告可按原身份读取。

只读性补充：真实运行目录完整 hash 未变化；确定性 Memory 测试对持久化 SQLite 主库及对象树、运行目录分别做浏览前后 hash 对比并保持一致。SQLite 只读 WAL 打开可能创建空 `-wal/-shm` 协调文件，因此它们不作为持久化内容 hash；测试同时确认没有 DML、checkpoint、报告、coverage 或对象写入。桌面断点和窄屏断点均实际查看，body 无横向溢出，长表仅在自身容器滚动，详情默认折叠；Codex 内置浏览器的 opaque `Origin: null` 仅在 `Sec-Fetch-Site: same-origin` 时允许本地 rescan，`cross-site` 仍返回 403。

独立复核（2026-09-21）：Reviewer PASS。复核确认完全相同 coverage bytes 在不同运行中仍按唯一 source/run 绑定各自报告；Options Evidence 按 security 闭合，纯他股及本股+他股混合引用均 fail closed；总览排除 manifest cutoff 不一致的 coverage；未发现新的阻断级错绑、状态误报、安全暴露、旧功能回归或持久化写入。该结论不代表人工归档批准或 Promotion PASS。

## 5. Macro / Market 实际冻结内容可读性修正

- [x] 5.1 在固定 `evidence/gate.json` 位置接入 `common-stock-research-evidence-gate/1.0.0`，验证 canonical hash、manifest cutoff 或 coverage/Gate 双 hash 绑定、run/cutoff、allowlist 和必要来源时间字段；仅按同运行 coverage dataset 声明的 Evidence ID 与语义白名单构造安全标量 projection，并用错 run、错 cutoff、显式 hash 冲突、缺失 manifest 绑定、坏 hash、未声明 Evidence、嵌套私人字段、绝对路径和符号链接样本验证 fail closed
- [x] 5.2 为 Macro 构造并渲染内容优先视图：最新指标、24 期宏观历史、Dot Plot 分布和有界经济日历须显示值、单位/口径、观察期和来源；官方快照缺失只作为局部限制，coverage 技术表默认折叠，并用真实 v4 等价 fixture 核对 12/100/192 条输入不会退化为计数占位
- [x] 5.3 为 Market 构造并渲染共享 FedWatch、全市场 Call/Put volume/OI 趋势和市场宽度缺口，以及证券级 Options underlying、48 条有界合约和 9 条供应商资金流；共享数据不得误标 MRVL，证券数据须保持 security/run/cutoff 绑定、来源限制和非方向性边界
- [x] 5.4 更新本机浏览说明和页面信息层级，确保用户内容位于主区、报告随后、技术审计在底部折叠；实际查看桌面和窄屏 Macro/Market，确认数值、长表、标签、缺口与无脚本图形可读，并重验重新读取不会联网或写入
- [x] 5.5 运行完整本机浏览器确定性测试、Python 编译、OpenSpec strict validation 与 `git diff --check`；用真实 v4 冻结运行逐项核对页面实际值并完成新一轮独立只读复核，出现阻断级错绑、误导标签、原始 Gate 泄露或旧功能回归则修复后再验

Section 5 实施证据（2026-09-21）：本机浏览器确定性测试 34 项、Python 编译、OpenSpec strict validation 与 `git diff --check` 均通过。真实 v4 的 Gate projection 为 Macro `dot_plot=12`、`economic_calendar=100`、`macro_history=192`，Market `fedwatch=3`、`market_breadth=0`、`option_market_statistics=37`、`options_snapshot=48`、`options_underlying=1`、`vendor_money_flow=9`；页面已实际显示 8 个最新宏观指标、8×24 趋势、点阵、经济日历、FedWatch、全市场 Put/Call、MRVL IV/HV、合约及资金流，coverage 审计位于底部折叠。桌面与 371px CSS 窄屏均实看，body `scrollWidth == clientWidth`，长表只在自身容器滚动。

只读复验：真实 v4 运行完整 hash 与 rescan 前后均为 `8c4bc473f4fe863d3bf8a14cde138c3f5756fcfce0bdaa05bb936e926a14ecf4`，Memory 持久化内容 hash 均为 `e4f91b63a3f306c7ad8b1ce59bb72198a896479623301cfb8b5ba4471d14592d`，本地 rescan 返回 303 且未访问 Provider/OpenD/模型。开发控制面全局 `self-check` 在当前 Codex 环境返回 `SELF_CHECK_COMMAND_NOT_ALLOWED`、`llm_calls=0`，未伪造成 PASS；它不是本 Section 规定的验收项。

新一轮独立复核先发现并促成修复 manifest 同步错位、嵌套私人值/绝对路径及 selected snapshot 分支不一致三类 blocker；最终 Reviewer PASS 确认 manifest cutoff 或双 hash 绑定、selected/无 selected 共用校验、显式 hash 冲突 fail closed、安全标量 projection、真实 v4 兼容与旧功能回归均闭合。该结论不代表人工归档批准或 Promotion PASS。
