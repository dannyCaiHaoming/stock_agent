# 流程对照实验（不属于正式流程）

由 `scripts/replay-ablation.sh <起始日> <宿主> <a|b|c>` 通过任务提示指定。每个变体只改一处，其余（数据、模型、输出格式、`forecasts` 方向预测）都相同：

- `variant-a.md`：单人版（现有正式流程去掉子 Agent 与论证审查）。
- `variant-b.md`：A + 把 CIO 的核心问题换成“基本面与公司指引的变化方向”，估值只衡量空间。
- `variant-c.md`：B + 正反双方观点备忘录，并在 CIO 判断之前交锋一次。

评分：`scripts/score-forecasts.py`。
