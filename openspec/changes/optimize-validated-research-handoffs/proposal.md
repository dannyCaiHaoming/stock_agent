## Why

当前 CIO 原生接缝要求经 `research_reports.read` 读取允许目录内全部完整报告，且正式装配以全部报告的读取事件为准。完整报告与可核验引用必须保留，但把每份全文都交付到模型上下文，可能增加重复输入、挤占判断空间并影响反证取舍；现有完整/紧凑投影和父线程 usage 不能证明实际全链费用或质量收益。先查清真实交付，再只优化这一处交接。

## What Changes

- 在已有冻结资料与真实执行事件上建立分阶段输入体量审计，区分磁盘产物、准备投影、实际 MCP 返回、模型输入及父/子 usage；分别披露字节、参考 token、缓存和未观测费用，不以投影大小声称节省。
- 在验证原报告、状态、身份和 hash 不变的前提下，为 CIO 的获准报告读取设计版本化的两层视图：先逐份交付可追溯的结构化索引，再按精确报告/局部标识读取必要原文。全文始终可按原绑定读取，不能让摘要成为唯一证据或由程序编造研究结论；不可证明完整覆盖时保留现有全文交接。
- 为新交付版本提供真实工具事件、读取范围与引用闭包的重验；旧包和旧全文读取协议保持原样。Skeptic 独立首轮、原 Gate/资料、报告 Schema、CIO 研究级限制及 Risk NOT_RUN 不变。
- 使用同一冻结来源、锁定模型/问题和明确预算对照原交接与候选交接；质量不退化是采用前提，实际 token、延迟与可观测费用改善才是效率结论。未经新的明确运行授权，不启动模型或候选晋升。
- 本 Change 规划与仍在执行的 `enable-single-stock-research-synthesis` 串行：先只读测量已完成的 MRVL 样本，不在 ALB 活跃运行中改共享代码/产物，待其终态稳定再验证单股兼容。`add-independent-tiger-trading-skills` 为独立入口，完全排除其代码、账户资料、账本、图表、复盘和插件副本。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `research-handoff-contracts`：明确 CIO 分层报告交付的允许范围、实际读取证明、质量/成本观测与失败回退，同时保留独立首轮隔离及历史版本读取。
- `common-stock-holding-analysis`：明确“CIO 可得到完整报告及可解析引用”在有界索引加按需全文读取下仍须成立，摘要不得成为唯一交付或屏蔽反证与限制。

## Impact

规划内目标接缝为 `product/runtime/cio_handoff.py`、`product/runtime/fixture_mcp.py`、`product/runtime/predecision_cio_stage.py` 及现有 CIO prompt/测试与运行审计；实际文件归属须在 apply 前重验，不能整体认领并行 Change 对共享文件的修改。现行 `read_cio_reports` 返回全文、`verify_cio_report_reads` 要求全目录已读，新方案需显式版本和闭合证明；不修改真实研究报告、账户权限、来源策略、产品运行入口或其它 Agent。此次只创建 OpenSpec 规划产物，不执行实现、模型调用、归档、提交或推送。
