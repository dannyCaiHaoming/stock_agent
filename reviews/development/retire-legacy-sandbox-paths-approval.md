# retire-legacy-sandbox-paths 人工批准记录

批准日期：2026-09-09。

## 批准依据与范围

在收到“你是否批准 `retire-legacy-sandbox-paths` 实现完成及 Task 4.2？”的确认请求后，用户明确回复“是”。据此记录本 Change 实现完成及 Task 4.2 的人工批准。

- `CHANGE_REVIEW: PASS`
- `CANDIDATE_PROMOTION: NOT_PROMOTABLE`
- `ISOLATION: UNVERIFIED`

本批准不代表 Promotion PASS，不授权修改生产版本指针，不将原生 `workspace-write` 或源码前后 hash 一致解释为全进程源码强制只读。本轮仅保存批准记录和更新任务状态，不重跑测试、模型、Regression 或 Gate，不修改产品实现，不执行归档、提交或推送。

## 绑定的源码与独立复核

- Git 基线：`ed45255626df4e6a8614f2c54254c50a6cc64e40`。批准对象包含其上的已审阅工作区差异，不仅是该历史 commit。
- 源码/配置清单：[source-sha256.txt](retire-legacy-sandbox-paths/source-sha256.txt)，覆盖 177 个文件；清单文件 SHA-256：`dd57caa2eb1eb162d7004640f745aab554bc8626080d416d9437ccdfcf2b8d3d`。
- 清单范围为根 `AGENTS.md`、`.codex`、`.agents`、`product`、`scripts`、`tests`、`evals/fixtures`、`docs/development`、`pyproject.toml` 下纳入清单的源码/配置；不代表整个仓库、临时运行目录或生产版本锁。
- 独立 Reviewer：Kierkegaard，session/Agent ID `01a086a3-7040-7c31-aa74-e66faa2ffad8`。
- 独立复核报告：[retire-legacy-sandbox-paths-independent-review.md](retire-legacy-sandbox-paths-independent-review.md)。文件 SHA-256：`3014ed6127d8e8b48e04e427c9af1814206d9177e2b97df4016f8e2c4b4f3c90`。

## 绑定的验收证据

| 证据 | 标识与完整 SHA-256 | 适用范围 |
| --- | --- | --- |
| [限定接缝验收记录](retire-legacy-sandbox-paths-verification.md) | `e7a63c635e2ec09c21670e625c172116a2f621536a30995ae6059f439c0f89cf` | 已执行的 28 项确定性接缝测试及 OpenSpec strict validate；不代替模型加载或强隔离证明 |
| [宿主 normal Smoke 记录](retire-legacy-sandbox-paths-normal-smoke.md) | `53427c1dea8b5e4bc8c2611cb398589bb0865f16fc78f448bae34932f1a64d5e` | 一次修复后实际宿主运行的参数、加载、执行与终态证据，不是全量 Regression 或晋升证据 |

Smoke run_id：`host-normal-5f21e995-d4cb-426f-b3d3-488b161c455b`。

原始运行目录：`/private/tmp/stock-agent-retire-normal.lar8XL/run`。终态为 `SAFE_NO_TRADE`，运行及既有 Eval 检查通过。产品源码快照（83 个文件）hash 为 `f836d67fe2a75a9b6e2e0fa23a969c6c052f19839f19be15b69583137fdcefcd`；该产品快照与上面的 177 文件清单范围不同，不互相替代。

本次直接复用已独立复核的原始证据，不补写或改写历史运行产物。私密运行状态仍留在原授权本地目录，不随本记录复制进仓库。

## 任务收尾

Task 4.2 已获得明确人工批准，可以标记完成；连同已完成的 Task 1.1–4.1，本 Change 为 8/8。归档与主规格同步仍是后续独立操作，本记录不声称已经完成归档或 Git 发布。
