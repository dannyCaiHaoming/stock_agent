# 第三次独立只读差异复核

`CHANGE_REVIEW: FAIL`

独立 Reviewer 只读检查当前源码、OpenSpec、已有测试证据和完整 hash；未修改文件、未运行测试、未联网，未启动产品 LLM、Regression 或 Gate。

## 阻断项

1. Gate、preparation 与 collection error 尚未完整从底层重建：`model_calls`、`provider_requests_completed_before_freeze` 等可在重签外层 hash 后通过；删除 `collection-error.json.failure_code` 后重签也未被拒绝。
2. Agent 启动前尚未使用 canonical validator/constructor 重建并比较 stage、coverage、holding request、invocation 和 dispatch index；一致修改并重签这些文件仍可能通过。

对应 Delta Spec 的“冻结研究数据包必须可被下游研究消费／数据包被篡改”场景，以及 Tasks 2.2、5.3。Task 5.3 当时不能完成。

## 已确认项

- 当前 Handoff 到 v4 不存在固定三股产品上限。
- 实际 Handoff 采集路径已实现单证券失败隔离。
- 旧 host profile 和三个 batch CLI 已退役。
- 必要共享实现、多维能力和历史读取未误删。
- 最终聚焦测试 JSON 当时声明的 34 个文件均存在且 hash 一致，但其证明范围不能覆盖上述重签路径。

## 当时关键 SHA-256

```text
da3d0411ff4041f94176566078e79956ec9b6eafb1320eb90f87909622a1c1aa  product/runtime/common_stock_data.py
fffebf79adedc90463999c933f4e10e3e4f31237b1cb89b2b35b58c047dc2e04  product/runtime/common_stock_stage.py
ad86d360cb3019d0f372634390dbdcac0f02297afe3a034e7eb25b31a4d17b55  final-focused-tests.json
af9c2020d831fa1f4259eedbe30fe94ba1ceb28474ebebe188961b898e3c258f  cleanup inventory
```

本结论记录当时快照，不构成人工完成批准或 Promotion 判断；后续修复不得改写本报告为 PASS。
