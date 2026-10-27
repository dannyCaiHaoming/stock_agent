# 前瞻纸面预测账本（baseline CIO）

目的：从现在起冻结系统“当时”的预测（含 NO_TRADE），之后的结果无法被事后重新解释。这是 baseline：用现有 CIO 流程，**不新增方法卡**（earnings-reaction 方法卡处于暂停状态）。不涉及真实交易与持仓，研究提示固定为“我目前未持有。”。

## 文件

- `reports/<日期>/<代码>-<decision_id>.md`：每条预测的完整报告冻结副本，与账本一同提交；账本中的 `report_sha256` 对应这份副本。
- `ledger.jsonl`：唯一账本，**只追加**，已有行不改写；提交到 git，以提交时间作为时间戳佐证。每行 `kind` 为：
  - `selection`：当天的选股结果与每只的入选原因，在研究开始前写入。
  - `prediction`：一次成功运行的冻结记录（动作、置信度、期限、方向预测、期望收益、论点摘要、失效条件、方法卡、`code_version`、模型、基准 ETF、纸面规则、完整报告的 `report_sha256`）。
  - `failure`：运行失败或没有保存决策，使缺失结果可见（`status`：run_failed / no_decision_saved / report_missing / run_json_missing）。每只股票失败后自动重试一次，两次尝试都留在账本里；两次都失败则当天该股票没有预测，不再补跑。错误以 `FORWARD_ERROR` 开头即时写入 `.local/data/history/forward-errors.log` 并发 macOS 通知。
- 同一 `run_id` 不能重复记录。

## 选股规则（预先固定，不得因结果调整）

美股交易日运行，每天最多 4 只，股票池 `evals/replay/universe.txt`。

1. 有“新鲜财报”的股票：财报 8-K（Item 2.02）的信号日 D0 等于最近一个已收盘交易日，D0 口径同 `evals/signals/pead-v2-definition-2026-10-26.md`（EDGAR 受理时间 09:30 前 → 当天；盘中、16:00 后或非交易日 → 下一交易日）。按 sha256("D0:代码") 排序（避免按字母序偏向某些代码），最多取 2 只。覆盖上次选择的信号日之后、到最近已收盘交易日之间的所有信号日（价格缓存滞后、节假日或漏跑时不跳过）。
2. 余下名额用确定性轮转补齐：股票池按字母序去重，起点 = `date.toordinal() * 2 mod 股票池大小`，依次取，跳过已选。

## 纸面规则

入场 = 预测时间之后的下一个交易日开盘（09:30 前做出的预测用当天开盘）；在入场后第 20、60 个交易日收盘退出；超额收益 = 个股同窗口收益减基准 ETF（`meta.json` 的行业 ETF，缺省 SPY）同窗口收益；往返成本 0.2 个百分点。NO_TRADE 也记录，用于检验“不做”是否正确。

## 脚本

- `scripts/forward-select.py [--date D] [--write]`：选股，`--write` 追加 selection 行。
- `scripts/forward-record.py <run-dir>`：把一次运行记入账本。
- `scripts/forward-run.sh`：选股 → 逐只 `dev-research.sh codex <T> --tag forward` → 记录 → 日志（`.local/data/history/forward-run.log`）。由 Codex 定时任务调用，仓库内不安装 launchd/cron。

## 评分

尚未实现。之后可扩展 `scripts/score-forecasts.py`，按上述纸面规则读取本账本评分；在评分规则写定前不做任何事后解释。
