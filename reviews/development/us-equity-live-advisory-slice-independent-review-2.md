# 第二次独立只读差异复核

`CHANGE_REVIEW: FAIL`

复核方式：独立 Reviewer 只读检查当前源码、Git 工作区、OpenSpec Proposal、Design、Specs、Tasks 与已有测试、证据文件；未修改文件、未运行测试、未联网，未调用产品 LLM、Regression 或 Gate。

## 阻断项

### 1. live 数据包的底层重验仍不完整

当前实现已经停止篡改 Gate 后自动重签，并要求 live Gate 同时提供 `data-preparation` 与 `source bundle`。但 `validate_common_stock_source_bundle` 尚未从逐证券 snapshot 重建并核对以下内容：

- `gate.conflicts`；
- `data-preparation.items[].data_gaps`；
- 失败项两侧一致的 `failure_code`；
- `source-bundle.items[].snapshot_id`；
- 失败项 `collection_error_ref` 与 `collection_error_hash`；
- Agent 启动前 `run_manifest.json` 的自身 hash 以及 Gate、preparation、source bundle、dispatch index 等底层绑定。

因此可修改部分字段并重新计算外层 hash 后通过，第一轮复核的第二项阻断尚未完全关闭。

### 2. 299 项与 strict validate 缺少当前快照的底层执行记录

cleanup inventory 仅保存命令和结果摘要，没有保存绑定当前源码快照的机器可读结果、原始输出和完整输入 hash。旧 `live-admission-v4-test-results.json` 只覆盖早期 175 项，且包含现已删除的 batch 测试，不能证明最新数据包校验和真实 Handoff 隔离修复。

## 第一轮三项阻断核对

| 原阻断 | 结论 |
|---|---|
| Handoff 到 v4 的三股上限 | 已关闭。当前 v4 无固定三股产品上限；历史 profile/v1/v3 只作兼容保留。 |
| live 下游完整重验 | 未完全关闭。主要 Evidence、PIT、SourceSelection 与 hash 已重验，但仍有上述字段和启动 manifest 缺口。 |
| 实际 Handoff 单证券失败隔离 | 已关闭。真实 Handoff 编排逐证券采集，单项失败后继续其余证券。 |

## 已确认边界

- 旧 host `--profile live-us-equity --portfolio ...` 在代理、Provider 与模型启动前拒绝。
- 三个旧 batch CLI 不再注册，活动源码无 `live_batch` 消费者。
- 必要共享实现、多维研究模块、历史 Schema 与锁仍保留。
- 本 Change 只证明数据和确定性接缝，不证明真实 Provider 当前可用、资料充分、Company Analyst 质量、Council/CIO/Risk、Regression、完整 Gate、`DOWNSTREAM_READY` 或 Promotion。

## 非阻断残余风险

- 历史 `live-us-equity/4.0.0` profile 仍含三股限制；当前 Handoff 数据路径不读取该限制，安全上仍依赖旧 host 入口已经退役。
- 每只证券建立一次有界采集事务，整批请求量随普通股数量线性增长，不等于固定持仓上限，也不证明无限吞吐。
- 当前工作区为多 Change 混合现场，目标文件可用完整 hash 锁定，但不能把整个工作区视为该 Change 的干净独立 diff。
- Task 5.4 尚未获得人工完成批准。

## Reviewer 重算 SHA-256

```text
e1431ba034ca52e91523944370114c783c3869e791267ef78abef16a0d3db3fd  proposal.md
3ff05e75fa6cb3e62bb7934d5a2f16a0d939239971914f3f0916c516883433cd  design.md
0cca5084c44b0d57e41aff70fe6d9e46a540343020e99a3f177cda0130cf066f  tasks.md
9ca8ac74b62363044dc825e54a6ea695d1e8d2742905fe20913cc385fd31b849  delta spec
4028e6b2b881f37a37993f91b6090385f6432e57de457a1725d4835f6a484afc  product/runtime/common_stock_data.py
bd2d039e99439157354962f9dad4f13ecc9b6e6adf9e4e9c00720a3ef7fbd1fb  product/runtime/common_stock_stage.py
31990cbaec95bc07f6033aee3698f1126caee7091e196f4d54aadedd2806c27c  product/council/common_stock_research.py
2646e232b99b8ae6255ba20e3267fdefa502dd62f39274c6d3ad7bcdf49668b3  product/mcp/live/collection.py
e53e0a746637cd2c281ccae558bc4fa5d9ab188f1873a162405eea41c932d537  scripts/run-product-smoke.sh
469ed6f5e3109986e93e71b17529d3f812f4e72fcbe7f656b4e6f3e0b2e8be45  product/runtime/cli.py
698cce75e254fe90e9459e07300a11632ee6aa501fe8ec4c267f83cb7af0e181  product/version-manifest.json
3ef5a32a91688a595ff03ddaaf7138f9f69b1454243aea63ad03ecec027cba98  live-portfolio-v2.schema.json
625152e883e07022c44bdc47969cfbc2c150ae9610104fa039f369d4449479ff  live-snapshot-v4.schema.json
a5fcecc2c492bb63b9a1b736af6f6f7a4d2c5486a9188949187d056257a39c15  live-source-access-v4.schema.json
ea10c888f417bb370a63377936646fff478539694a47f3cb3aa4182a88141c11  personal-research-approval.json
```

结论只代表第二次独立复核，不构成人工完成批准或 Promotion 判断。
