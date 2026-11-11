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

**v2 变更（2026-11-08，因 token 成本）**：改为**每周一次**（周五收盘后），最多 4 只；财报股优先，覆盖最近 5 个已收盘交易日内的财报信号日，最多 4 只；不足再按轮转补齐。账本 `selection` 行的 `ledger_version` = 2。v1 期间（2026-10-26 起）只运行过一次，10-27 至 11-07 无记录，这段缺口如实保留。

1. 有“新鲜财报”的股票：财报 8-K（Item 2.02）的信号日 D0 等于最近一个已收盘交易日，D0 口径同 `evals/signals/pead-v2-definition-2026-10-26.md`（EDGAR 受理时间 09:30 前 → 当天；盘中、16:00 后或非交易日 → 下一交易日）。按 sha256("D0:代码") 排序（避免按字母序偏向某些代码），最多取 2 只（v2：最多 4 只）。覆盖上次选择的信号日之后、到最近已收盘交易日之间的所有信号日（价格缓存滞后、节假日或漏跑时不跳过）。
2. 余下名额用确定性轮转补齐：股票池按字母序去重，起点 = `date.toordinal() * 2 mod 股票池大小`，依次取，跳过已选。

## 纸面规则

入场 = 预测时间之后的下一个交易日开盘（09:30 前做出的预测用当天开盘）；在入场后第 20、60 个交易日收盘退出；超额收益 = 个股同窗口收益减基准 ETF（`meta.json` 的行业 ETF，缺省 SPY）同窗口收益；往返成本 0.2 个百分点。NO_TRADE 也记录，用于检验“不做”是否正确。

## 脚本

- `scripts/forward-select.py [--date D] [--write]`：选股，`--write` 追加 selection 行。
- `scripts/forward-record.py <run-dir>`：把一次运行记入账本。
- `scripts/forward-run.sh`：选股 → 逐只 `dev-research.sh codex <T> --tag forward` → 记录 → 日志（`.local/data/history/forward-run.log`）。由 Codex 定时任务调用，仓库内不安装 launchd/cron。

## 评分

尚未实现。之后可扩展 `scripts/score-forecasts.py`，按上述纸面规则读取本账本评分；在评分规则写定前不做任何事后解释。

## 组内方向预测账本（轻量，2026-11-11 新增）

目的：用很低的单次成本积累大量前瞻判断。完整研究每周最多 4 只，要分辨 55% 与 50% 的命中率需要约 400 个独立判断；轻量模式每周覆盖整个股票池。

- `scripts/forward-groups.sh`：对 `evals/replay/universe.txt` 的 14 个组各跑一次 `direction-forecast` Skill（Codex，默认 `gpt-6-luna`），每只股票给出“之后 60 个交易日收益高于本组中位数”的概率和一句依据。不写研究报告，不启动子 Agent。
- `group-ledger.jsonl`：只追加，与 `ledger.jsonl` 分开。每行 `kind` 为 `group_forecast`（一组的全部预测、`data_as_of`、`code_version`、模型）或 `failure`（没有保存，或股票与名单不一致）。每组失败后重试一次。
- 建议每周五收盘后运行一次，与 `forward-run.sh` 一样由定时任务调用，仓库内不安装 launchd/cron。
- 评分：`scripts/score-group-forecasts.py <运行目录通配符>`。结果从 `data_as_of` 当日收盘算起，与同组中位数比较；这是排序能力的检验，不是可成交的纸面收益（收盘后做出的预测无法按当日收盘价成交）。对照为之前 60 日、126 日涨幅。
- 同一只股票可能出现在两个组里（例如 NEE、AMD），各组分别评分。
