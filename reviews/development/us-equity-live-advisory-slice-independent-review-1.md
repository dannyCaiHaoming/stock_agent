# `us-equity-live-advisory-slice` 第一次独立差异复核

日期：2026-09-16
Reviewer：独立 `dev-reviewer`（未参与被复核实现）
方式：只读检查源码差异、OpenSpec 文档和已有测试证据；未运行网络、产品 LLM、Regression 或完整 Gate。

## 结论

`REVIEW: FAIL`

本记录保留第一次复核发现，不因后续修复而改写为 PASS。

## 阻断项

1. 当前 `live-snapshot-v4` 的 `source_selections` 仍有 `maxItems: 3`，`live-source-access-v4` 与操作者批准记录也仍包含 `max_positions: 3`；已有超过三只测试只覆盖 Handoff 到采集请求，没有覆盖当前 v4 快照冻结。
2. 普通股阶段会删除并重算外部 Gate 的 `bundle_hash`；data-preparation 的 `preparation_hash`、Gate/Evidence/来源选择的底层绑定也未完整重验，显式 `--gate` 可省略数据准备清单。
3. `collect_common_stock_data_from_handoff` 一次性调用整批 `collect_live_snapshot`；任一证券身份、行情或 SEC 失败会使整批失败。已有隔离测试只覆盖回调组装器，不是实际 Handoff 采集入口。

## 当时源码/规格标识

- Proposal：`e1431ba…3fd`
- Design：`3ff05e75…33cd`
- Tasks：`19477f57…297`
- Delta Spec：`9ca8ac74…849`
- host launcher：`7ccf33f19375473c5d5f572d088ee05bfa50e09fb13833b35e4b71d7431759e0`
- runtime CLI：`6866e71502d492b12afccb9ca30febadd2d2159d4b1c721cf09f6c7fc07b8f2d`
- `common_stock_data.py`：`1855af26…c99`
- `common_stock_stage.py`：`1f1b30a4…ec7c`
- `common_stock_research.py`：`cde847fc…3f1c`
- `live_input.py`：`e944711b…625d`
- `collection.py`：`1b1f9df3…14c5`
- `live-snapshot-v4.schema.json`：`a6a9ac36…425b`
- `live-source-access-v4.schema.json`：`997e2eda…cc33`

## 证据适用边界

复核确认旧 host profile 与 batch 命令退役、历史消费者保留方向正确；但当时的 292 项聚焦测试不足以关闭上述三项，因此相关 Tasks 已重新打开。后续修复和第二次独立复核应引用新的完整源码 hash，不得覆盖本记录。
