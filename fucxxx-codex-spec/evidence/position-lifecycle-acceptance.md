# MVP L1 验收记录（2026-11-28）

依据：[designs/position-lifecycle.md](../designs/position-lifecycle.md)“验收”；plan [plans/position-lifecycle-impl.md](../plans/position-lifecycle-impl.md)。

## 实现与复核
- 实现：H1 结算数学、H2 计划记录、H3 接入，由 Claude Sonnet 5.5 子 Agent 完成；证据见 `position-lifecycle-h1.md`、`-h2.md`、`-h3.md`（一开始误派给 Haiku 5.5，用户纠正后取消，Haiku 未写入任何文件）。
- 两个 Skill（`trade-plan`、`plan-review`）由主会话写。
- 代码复核：Codex `gpt-6.2-astra` 只读，12 条（5 高、5 中、2 低），全文 `.local/runs/lifecycle-design-20261128/astra-code-review.md`。按 [plans/position-lifecycle-rework1.md](../plans/position-lifecycle-rework1.md) 由两位 Sonnet 并行返工；#7（提前收市）按设计只做标记，其余均已改。返工后复查见下文“复查”。
- 主会话补改：`--seed-plans` 同时复制 `plan-reports/`（否则复核读不到原计划全文，完整性显示 missing）；Skill 按返工后的接口改写（复核第一步用 `view="thesis"`；名额满时记 wait；回放参数说明）。

## 离线测试（主会话实跑）
`.venv/bin/python -m unittest tests.test_plan_math tests.test_plan_ledger tests.test_plan_integration tests.test_decision_integration tests.test_decision_ledger tests.test_decision_scoring tests.test_decision_events tests.test_stock_data_tools` → OK（含原有测试，未破坏 P1）；`bash -n scripts/dev-research.sh` 通过。

## 固定用例（历史回放，Codex `gpt-6.1-terra`，共 4 次模型调用）

| 用例 | 运行目录 | 结果 | 判定 |
|---|---|---|---|
| A 跳空超出预算 | `*-MU-asof2026-06-26-L1-A-plan`、`*-MU-asof2026-07-01-L1-A-review` | 计划 13 股、R0 940.29、区间 1100–1132.33、失效位 1060（来自用户）。06-29 开盘 1128.70 成交；07-01 收盘 1032.28 ≤ 1060；复核：论点 **unchanged**（没有新经营事实，没有拿价格推论点），动作 **EXIT**（价格失效位触发），无偏离。07-02 开盘 1041.50 离场。照计划 −1,161.81 = **−1.236R**；持有到 cap（10-23 收盘 877.55）−3,291.03 = −3.500R；简单退出与照计划相同 | 通过 |
| B 同股重开 | `*-MU-asof2026-10-01-L1-B-reopen`；直接调用 `.local/runs/l1-acceptance-20261128/B-direct/` | 模型判断**计划不成立**（指引超预期，但说不出市场错在哪），记 `not_formed` 进入漏斗。重开链路改用回放会话直接调用工具验证：旧计划 `active=false`（`exit_review`），新计划 `51c54ef54408` 取得新 id 且 `active=true`；再开一次被 `ACTIVE_PLAN_EXISTS` 拒绝 | 通过（重开为工具直接调用，不是模型实跑） |
| C 未成交 | `*-PL-asof2026-03-20-L1-C-plan` | 区间 32.50–33.90（上限来自用户），03-23 开盘 34.50 → **unfilled**，三线无金额，进入漏斗 | 通过 |

- 三份结算：`.local/runs/l1-acceptance-20261128/score-A.md`、`score-B.md`、`score-C.md`。
- **A 手算**：买 13 × 1128.70 = 14,673.10，卖 13 × 1041.50 = 13,539.50，毛 −1,133.60；成本 14.67 + 13.54 = 28.21；净 −1,161.81；÷ 940.29 = −1.236R。持有线卖 13 × 877.55 = 11,408.15，毛 −3,264.95，成本 14.67 + 11.41 = 26.08，净 −3,291.03 = −3.500R。与脚本一致。
- 三次运行的 `model_recorded` 都是 `{"source": "run_env", "value": "gpt-6.1-terra"}`。
- 计划卡质量（主会话抽读）：A、C 的放弃事实都是将来可核对的具体事项（例如“FY2027 收入指引上限下调至低于 4.15 亿美元”“Q1 收入低于 8700 万美元”），失效位写明理由并提示“很近、容易触发”。

## 真实前瞻尝试（2026-11-28，Codex terra，2 次模型调用）
| 股票 | 运行目录 | 结果 | 主会话判断 |
|---|---|---|---|
| NVDA | `.local/runs/20261128T081818Z-codex-NVDA-L1-live-plan` | `not_formed`：财报与复职都已公开，复职后冲高回落，加州调查未解决，“无法确认市场误判” | 门槛过高，且漏查关键事实：Q3 10-Q 截至 11-28 未提交（前两季都在财报当天提交） |
| PL | `.local/runs/20261128T082713Z-codex-PL-L1-live-plan` | `wait`：两份合同未披露金额，等 12-10 财报 | 合理，但同样反映“必须证明错价”的门槛 |

随后 Opus 与 Codex astra 就 NVDA 讨论两轮（`.local/runs/nvda-dialog-20261128/summary.md`）：共同结论为 **wait**，检验点 12-03 参议院听证、12-04 10-Q 截止（NT 后 12-09）。据此修改 `trade-plan` Skill（用户 2026-11-28 同意）：加入申报惯例核对；“市场错在哪”改为可检验的分歧并标把握程度；三种结果（not_formed / wait 写明重看条件 / 冻结）；空仓等待不写失效位；卡片首行写把握程度。

## 历史走查（2026-11-28，用户不想等 NVDA；Codex terra，10 次模型调用）
选样规则（看结果前定）：PEAD v2 事件表中财报后超额 ≥ 8% 的事件，2025 与 2026-01~07 各按 sha256(信号日:代码) 升序取前 2 个，跳过已用于验收的 PL → IBM 2025-01-30、TER 2025-07-30、GS 2026-07-14、MRVL 2026-03-06。

第一批（旧成交规则）：IBM `wait`（等 02-04 投资者日，写明放弃与重做条件）；TER、GS、MRVL 都成计划但**全部 unfilled**（区间 ±1–2%，只看第一个开盘）。据此做返工 3（限价挂单，见 [plans/position-lifecycle-rework3.md](../plans/position-lifecycle-rework3.md)），348 个测试通过，旧记录结算逐字不变。

第二批（新规则，运行目录 `*-hist-plan2`、`*-hist-review`，结算 `.local/runs/l1-acceptance-20261128/hist2-*.md`）：

| 股票 | 计划 | 复核 | 照计划 | 持有到期 | 说明 |
|---|---|---|---|---|---|
| IBM | 02-04 投资者日后成计划：入场 264.46（259–270，3 日），失效 246，54 股，R0 996.84 | 下次财报前已止损，未复核 | −1.271R | +0.024R | 03-13 收盘 245.80 触发，之后反弹：一次被震出 |
| GS | 1140（1110–1170），失效 1080，16 股 | 下次财报前已止损 | −1.267R | −3.728R | 少亏 2.46R |
| TER | 107.65（103.9–111.4），失效 102，176 股 | 10-29：论点**增强**，HOLD | +10.383R | 同 | 拿到持有期上限 |
| MRVL | 89.57（86.2–93.0），失效 83，152 股 | 05-28：论点**增强**，HOLD | +28.677R | 同 | 87.93 → 276.70 |

合计：照计划 +36.5R，持有到期 +35.4R。形状是“两笔小亏、两笔大赚”。

限制与发现：
- 样本 4 个、都是 AI 行情期的财报大涨，MRVL 一笔占大头；2025 事件很可能在模型训练期内，回放不能排除记忆。**不是效果证据**。
- 两次复核都选择拿住赢家（没有过早卖出），但**都没有上移失效位保护利润**（TER 复核时价格约为入场的 1.5 倍，失效位仍是 102）。用户 2026-11-28 同意后，`plan-review` 增加“浮盈保护”判断：每次复核算浮盈 R，约 2R 以上且论点未变坏时判断是否上移失效位并写理由（判断指引，不是规则）；尚未实跑验证。
- 持有期上限（用户定 120 天内）在两笔赢家上强制离场。

## 未完成
- 用户 2026-11-28：历史走查**不能**代替真实前瞻用例，L1 仍待 NVDA（12-04 之后）。
- **真实前瞻用例改为：12-04（10-Q 截止）之后对 NVDA 用修订后的 Skill 重跑**；形成计划则在下一次公开事件后复核，L1 收口。
- **真实前瞻用例**（L1 最后一项）：需要用户选一只临近财报或有已排期事件的股票，计划后由用户复述失效条件，下一次公开事件后复核。10 个交易日内没有合适事件则报告“待验”。
- 用户复述失效条件：待用户。
- 回放仍开着联网检索，不能完全排除模型看到截止后的报道；固定用例只验证流程与算术，不作效果证据。
- 已知限制：提前收市日只标记；分红不计；拆股窗口不可结算；`list_trade_plans` 摘要里的 `report_path` 是原始绝对路径，仅作显示，读取全文按 id 定位并校验。

## 复查
Codex `gpt-6.2-astra` 复查返工 1（`.local/runs/lifecycle-design-20261128/astra-recheck.md`）：12 条中 #3、#5、#8、#9、#11 已修复；#1、#2、#4、#6、#10、#12 部分修复；#7 达到约定的人工核对要求；另有 1 条新问题（回放当天无法记录选择）。A 的三线结算独立手算复现一致。

返工 2（[plans/position-lifecycle-rework2.md](../plans/position-lifecycle-rework2.md)，Sonnet 5.5）：
- 拆股：`data_tools.get_price_history` 带 `as_of` 时只还原“截止之后、且不晚于响应获取日”的拆股（修掉“拆股前缓存被再乘一次”）；拆股比例无法解析 → 不可结算。这是共享行情工具的既有缺陷，常见情形结果不变，有回归测试。
- 回放写入遇到截止后记录 → 统一 `HISTORY_WRITE_CONFLICT`，不透露未来动作；`published_at` 只接受 `YYYY-MM-DD` 或带时区的完整时间；到期且日历内无可成交开盘即 `expired_unfilled`；选择可与引用记录同一有效时刻；`--plan`/`--review` 回放提示与 Skill 一致。
- #10 的“持有依据混入价格条件”：Skill 改为持有依据只写经营与消息事实，价格条件只写失效位（主会话）。未做字段拆分，已有计划不受影响。
- 主会话核对：319 个测试通过；A 重新结算逐分不变，C 仍 unfilled。返工 2 未再做独立复查。

遗留（不阻断 L1）：计划本身晚于截止才冻结时仍返回 `EFFECTIVE_NOT_AFTER_FROZEN`（会暴露该 id 存在）；获取当天发生的拆股按“已调整”处理，边界日可能有一天偏差；拆股还原只用 mock 与临时缓存验证，未对真实拆股股票实测；提前收市日只标记。
