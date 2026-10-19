# 冻结版本

前瞻验证只使用冻结版本；冻结后的修改进入下一个版本，不回头按历史回放样本调整。每条决策记录的 `code_version` 写明产生它的 git commit 与是否有未提交改动。

## research-v3（2026-10-19）

- **流程**：`stock-research`（advocate 与 skeptic 并行独立初稿 → skeptic 核验正向论点一轮 → CIO 判断，无事后审查）、`bull-case`、`skeptic-review`、`investment-decision`，以及 `research-standards` 与各分析 Skill。
- **共享 references**：`product/references/` 方法卡 6 张（v1：guidance-revision、growth-acceleration、quality、implied-expectations、trend-stage、relative-strength-ma）、案例卡 12 张（按结果已知日期过滤）、角色输出格式。
- **统计证据**：信号定义 v1（tag `signals-v1`）；事件表由 `scripts/build-signal-events.py` 生成，`get_signal_stats` 用同日对照与整群置信区间。
- **决策记录**：`forecasts`（营收增速、营业利润率、126 日相对板块、可选指引）、`expected_return_pct`、`methods`、`code_version`。
- **开发集表现**（2025-01/04/07 共 27 个回放样本，Codex gpt-6-luna）：方向预测与朴素基准无可靠差异；BUY 4 个、126 日净超额中位 +33%（样本太少，不作结论）。详见 `evals/replay/ablation/27-codex-summary.md`。
- **已知限制**：股票池 82 只大盘股有幸存者偏差；回放中模型可能记得结局；单信号优势尚未证实；无历史一致预期。

历史回放样本（`evals/replay/`）此后只用于说明，不再用于调参。
