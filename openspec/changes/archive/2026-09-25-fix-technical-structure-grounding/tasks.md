## 1. 冻结可比输入与失败归因

- [x] 1.1 锁定缺 SPY 的 MRVL Gate/Technical packet、原始失败草稿，以及基准完整且已通过 calculation/artifact closure 的 MRVL 样本；交付两种输入的行数、calculation/chart 状态、Claim 引用和报告状态对照，确认不是 Macro/Market 输入消减回归，也不跨 run 混用事实。

## 2. 三种技术输入的最小修复

- [x] 2.1 仅在 `TECHNICAL_STRUCTURE` 无 calculation 时，使任务说明及现有任务级输出约束要求 `status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`、`claims=[]` 和具体来源 gap；用 MRVL 有日线/SPY 缺失的聚焦测试验证草稿与正式报告可 `SAVED`、无虚构计算/引用，研究包 `coverage.status=INSUFFICIENT_EVIDENCE` 而非 `COMPLETE`，且通用无依据 Claim 校验仍拒绝违规输出。
- [x] 2.2 保持个股与基准完整时的技术计算、计算引用及 artifact closure；用聚焦样本验证正常 Technical Claims 有真实 `calculation_refs`，报告及图表引用可消费，未改计算公式、Gate 或非 Technical 任务。
- [x] 2.3 将 Technical 任务说明/Skill 的图表要求条件化，覆盖可预期的 chart 渲染失败：聚焦测试确认 calculation 文件及 hash、唯一获准的计算 artifact ref、有效 Claims 与 `calculation_refs` 均保留，只记录 chart gap，不引用不存在的图、不把状态误降为缺全部计算资料；若报告用 `sufficiency=PARTIAL` 表达图表限制，不得写成 `coverage.status=PARTIAL`；未知文件/权限错误不得被吞成来源受限。

## 3. 真实运行与收尾

- [x] 3.1 通过既有宿主 launcher 用缺基准的冻结 MRVL 输入运行受影响路径，验证 Technical 任务 `SAVED`，但报告仍为 `status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`、`claims=[]`，研究包 `coverage.status=INSUFFICIENT_EVIDENCE` 且网页/下游不展示 `TECHNICAL_STRUCTURE COMPLETE`；复核基准完整真实样本及 chart-failure 聚焦证据，分别记录保存数与实质研究状态，不宣称旧 Gate 的技术研究已完成。
- [x] 3.2 对最终差异、三种规格场景、聚焦测试及真实产物做独立只读复核，记录 `CHANGE_REVIEW` 结论与剩余限制；`openspec validate fix-technical-structure-grounding --strict`、受影响测试和差异检查均通过后，等待用户明确完成批准再同步归档，不启动无关 CIO/Eval/Regression。
