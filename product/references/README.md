# 共享 references（三个角色共用）

知识与流程增强，不是更新模型参数。版本随 git 管理；决策记录写明引用了哪些方法卡及其版本。

- `methods/`：方法卡——适用情境、数据要求（工具与字段）、分析步骤、输出口径、对应统计信号、常见误用。
- `cases/`：历史案例卡——当时信息、原始判断、后续结果、成败原因、与当前的差异。只用于说明机制，不混入胜率统计。读取用 `get_reference_cases(method, as_of)`，只返回结果在 as_of 之前已知的案例。
- 统计证据：不手写。由 `scripts/build-signal-events.py` 生成事件表，`get_signal_stats(signal, horizon_days, as_of)` 只统计结果在 as_of 之前已知的样本；样本不足标“需要验证”。对照口径为同日全股票池横截面百分位（`mean_percentile_minus_50`），两个整群置信区间都不含 0 才算可靠；另含财报后漂移（pead_*）、内部人（insider_*）、议员（congress_*）事件，详见 `evals/signals/method-and-results-2026-10-20.md`。只有触发条件明确的信号才有统计，方法卡不强行配胜率。
- `templates/`：卡片模板与三个角色的输出格式。

统计主窗口 60 个交易日，20／126 日辅助（方法卡可另定，如 `earnings-reaction` 以 20 日为主）；这不规定实际持仓期限。
