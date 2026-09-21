## Why

Company、Macro、Market 三域的数据准备能力已扩展到 SEC、Yahoo、官方宏观来源与 Moomoo SG 补充层，但现有本机网页仍主要呈现早期快照和报告：它不会读取 `provider-coverage.json`，也没有展示 Dot Plot、经济日历、FedWatch、期权市场统计及 `OPTIONS_FLOW` 的交付状态。第一轮实现补齐了覆盖审计，却只让用户看到 dataset 名称与计数；真实冻结值仍埋在 Gate Evidence 中，Macro/Market 页面因缺少旧式快照继续显示“尚无快照”，无法回答“拿到了什么数据、当前值和时间是什么”。因此本 Change 还需同时解决研究内容可读性，而不是停在技术覆盖率页面。

## What Changes

- 扩展本机只读运行产物 registry，识别并校验当前 `provider-coverage` 审计产物；不递归扩大目录扫描范围，不读取未知私人文件。
- 在 Macro、Market、Company 页面分别展示与该域相关的数据集覆盖、来源层、Capture / Gate / Delivered 数量、状态、限制和失败码，并保持数据集到研究能力的路由可查。
- Macro 增加 Dot Plot、经济日历和宏观历史等已保存数据集的覆盖展示；官方宏观事实与 Moomoo 供应商补充保持分层，不把预测、共识或市场隐含概率冒充官方事实。
- Market 增加 FedWatch、期权市场统计及安全绑定的 `OPTIONS_FLOW` 报告入口；证券级期权快照、标的上下文和供应商资金流不得冒充共享市场状态或确定资金方向。
- 从与 coverage 同一 source/run/cutoff 绑定且 hash 有效的 `evidence/gate.json` 中，仅按 coverage 已声明的 Evidence ID 和语义允许列表生成只读内容 projection：Macro 展示指标最新值、趋势、Dot Plot 与经济日历，Market 展示 FedWatch、全市场 Put/Call 统计以及证券级波动率、合约和供应商资金流。
- 将用户可理解的冻结值、日期、单位、来源口径和合法限制放在域页主内容区；Capture/Gate/Delivered 等技术审计明细移到页面底部并默认折叠，不再用交付计数替代实际内容。
- 将美国宏观、FedWatch 和全市场期权统计标为共享环境数据；运行以 MRVL 为研究对象不等于这些共享数据“适用证券是 MRVL”。只有期权链、标的波动率与供应商资金流显示证券范围。
- Company 在既有事实、Company Agent 报告和四类补充研究之外，增加公司数据集交付概览，使 analyst expectations、financial history、management/governance、ownership 等覆盖与缺口可见；不把已交付资料自动表述为 Agent 已采用。
- 在首页和三域页面明确区分 Capture、Gate eligible、Delivered、Actual research use 和研究报告状态。`NOT_EVALUATED_AT_PREPARATION`、`NO_GATE_EVIDENCE`、`SOURCE_LIMITED` 等状态保持原义，不合并为单一成功/失败。
- 将页面内“刷新”文案统一为重新读取已配置本地 Memory 和冻结运行目录；刷新仍不得调用 Provider、OpenD、模型或研究调度，也不得修改任何运行产物。
- 补充真实新版冻结产物与确定性样本验收，包括旧运行兼容、错绑定隔离、未知/损坏 coverage 降级、窄屏阅读、隐私与只读性。
- 保持现有 Python 标准库服务和页面结构，不新增前端框架、JavaScript 数据层、数据源 Agent、第二套路由服务或浏览器专用持久化模型。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `local-research-browser`: 增加三域新版数据覆盖、来源层、路由与实际研究使用状态的只读展示；同时把同运行 Gate 中的 Macro、Market 和 Options 冻结 Evidence 转换为可理解的指标、趋势与明细，并补充共享范围、`OPTIONS_FLOW`、本地刷新语义和新版产物兼容验收。

## Impact

- 主要影响 `product/web/read_only.py`、`product/web/rendering.py`、必要时的最小路由装配，以及 `tests/test_local_research_browser.py` 和浏览说明。
- 读取 `run/audit/provider-coverage.json`、与其绑定的 `run/evidence/gate.json` 及现有 `research-dimension-report/2.0.0`；不修改其生产 schema、数据准备、Gate、研究调度或 Agent 输出。
- 保持 `127.0.0.1`、显式准入目录、符号链接/路径穿越防护、内容校验、私人上下文清理和无外部资源加载等边界。
- 旧运行没有 coverage 产物时继续显示原页面并给出可理解空状态；网页未升级或不可用不影响采集、研究和 Runtime。
