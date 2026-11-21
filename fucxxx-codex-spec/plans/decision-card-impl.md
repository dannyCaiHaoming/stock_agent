# MVP P1：日用决策卡 实施 plan

类型：实现
依据：[designs/decision-card.md](../designs/decision-card.md)（全文已定）；[协议 v1](../../evals/forward/decision-protocol-v1.md) §2–§8；总设计 §3。
依据版本：`main` d4fa875；本 plan 与子设计为本轮新增，未提交（在共享工作区中直接可读）。
执行者／工作区：T1–T4 由 Sonnet 子 session 并行执行；T5、T6 与整合由主会话（Opus）执行。所有人共用 `/Users/caihaoming/Documents/stock_agent`（`main`，不开分支）。
状态：执行中
plan 维护者：主会话。执行者不改本文件，结果写到自己的证据文件（见 §0）。

## 0. 当前交接
- **当前 MVP 核心目标**：用户问持有／未持有该怎么办，得到口径一致的决策卡，并生成一条可按协议成交、评分的 `decision/v2` 记录。
- **本 plan 只完成**：子设计 T1–T6。
- **为何直接影响当前目标**：
  - T1 让分布与成交口径一致；
  - T2 让记录可评分，且机械字段不由模型填写；
  - T3 让主窗口由事件决定，而不是由模型选；
  - T4 让行动增益可复算；
  - T5、T6 是用户入口与验收。
- **必须保留的接口／验收**：
  - 旧 `save_decision` / `decisions.jsonl` / 旧账本 / `score-forecasts.py` 行为不变；
  - `key-moments.jsonl` 原 `outcome` 字段逐行不变；
  - 测试一律在临时目录里运行（`STOCK_AGENT_DATA_DIR` 指向 tempdir），不得写入 `.local/data/`。
- **本次不做**：每日扫描、名单与映射快照、推送、完整研究改造。
- **授权与停止点**：
  - 执行者可以运行测试与只读数据请求（含 Yahoo / SEC 缓存），可以重建关键时刻表（T1）；
  - 不 commit、不 push、不调用模型实跑、不改分派给自己以外的文件；
  - 设计契约需要改变时停下，写进证据文件并返回。
- **写入归属**（互不重叠）：

| 任务 | 只可写这些文件 |
|---|---|
| T1 | `product/deterministic/key_moments.py`、`scripts/build-key-moments.py`、`product/mcp/reference_tools.py`（只改 `get_key_moments` 与 `_key_moment_events`）、`evals/key-moments/distribution-latest.md`、`evals/key-moments/distribution-close-entry-2026-11-11.md`（新）、`tests/test_key_moments_open.py`（新）、`.local/cache/derived/signals/key-moments*`（重建产物）、`fucxxx-codex-spec/evidence/decision-card-t1.md` |
| T2 | `product/mcp/decision_ledger.py`（新）、`product/mcp/server.py`（只新增 `save_trade_decision` 的注册）、`scripts/decision-record.py`（新）、`tests/test_decision_ledger.py`（新）、`fucxxx-codex-spec/evidence/decision-card-t2.md` |
| T3 | `product/deterministic/decision_events.py`（新）、`product/mcp/decision_tools.py`（新）、`scripts/sample-idiosyncratic-moments.py`（只把 `deviation` 改为调用新函数，行为不变）、`tests/test_decision_events.py`（新）、`fucxxx-codex-spec/evidence/decision-card-t3.md` |
| T4 | `product/deterministic/decision_scoring.py`（新）、`scripts/score-decisions.py`（新）、`tests/test_decision_scoring.py`（新）、`fucxxx-codex-spec/evidence/decision-card-t4.md` |
| 主会话 | `product/skills/decision-card/`（新）、`product/skills/stock-research/SKILL.md`、`scripts/dev-research.sh`、`server.py` 中 T3 工具的注册、本 plan、子设计、handoff |

- **必读输入**：
  - `AGENTS.md`；
  - 子设计对应的 T 节、协议 v1 全文；
  - 本 plan §1、§2 中自己的行。

  fucxxx-codex-spec 执行参考：Claude Code 在 `~/.claude/skills/fucxxx-codex-spec/references/execution.md`，Codex 在 `~/.codex/skills/…`。
- **交付**：
  - 在自己的证据文件里写清：实际修改的文件、新增接口签名、实际运行的测试命令与输出摘要、未运行或失败的项、对设计的回写建议；
  - 最后一条消息给出简短结论。

## 1. 工作安排
| 必要步骤 | 为什么需要／前置依赖 | 预计涉及位置 | 行为判据 |
| --- | --- | --- | --- |
| T1 开盘口径 | 无依赖 | 见 §0 | 见下方 T1 判据 |
| T2 v2 记录 | 无依赖（`CAUSES` 从 `decision_log` 导入） | 见 §0 | 见下方 T2 判据 |
| T3 事件分组 | 无依赖（读 `meta.json` 板块映射） | 见 §0 | 见下方 T3 判据 |
| T4 评分 | 只依赖子设计中已定的记录字段，用构造的测试记录开发 | 见 §0 | 见下方 T4 判据 |
| 整合 | T1–T4 返回后 | `server.py` 注册 T3；`save_trade_decision` 调 T3 核对 group 与 horizon | 全部测试通过；MCP 工具列表含两个新工具 |
| T5 Skill | 依赖 T2、T3 的接口（已在子设计中定好，可先写） | 主会话文件 | 下方 T5 判据 |
| T6 验收 | 依赖全部 | `.local/runs/`、`evidence/decision-card-acceptance.md` | 子设计“验收” |

**T1 判据**：
- `outcome_open` 的入场为 `dates[i+1]` 复权开盘，退出为 `dates[i+h]` 收盘；
- 单元测试用手造价格序列核对 ret / excess / worst / 缺价返回 None；
- 重建表后行数与旧表相同，原 `outcome` 逐行相等（抽查全表比对并写进证据）；
- `get_key_moments` 输出读 `outcome_open`，provenance 写明“next session open”；
- 新的 `distribution-latest.md` 头部注明口径，旧文件留副本。

**T2 判据**：
- 工具生成字段不接受模型传入（传了就拒收）；
- w0/w1/horizon 按协议 §4 与 group 计算；
- held/not_held 与动作的组合校验；
- HOLD/WAIT 必须有 `hold_type`；
- `review_triggers` 至少两条，其中至少一条含数字；
- E1/E2 的归因必填且使用 `CAUSES`；
- `replay_as_of`：`decided_at_effective` = 该日 16:00 America/New_York 之后，`replay = true`；
- `decision-record.py` 只追加、同一 id 不重复；
- 测试覆盖以上每条，并在临时目录里运行。

**T3 判据**：
- 迁移后的 `deviation_z` 与原脚本 `deviation` 在 20 个以上真实（缓存）事件上逐个相等；
- `pead_d0` 覆盖 09:30 前、盘中、16:00 后、非交易日四种情形；
- `classify` 覆盖 E2 下偏 / E2 上偏 / E1 / 重叠归 E2 / E0 / 无映射不进 E2；
- E1 不用 D0 收盘之后的数据；
- `b1_action` 按协议 §5；
- `classify_decision_event` 至少对 2 只真实股票的历史 as_of 实跑一次，结果写进证据。

**T4 判据**：
- 协议 §8 三行被单元测试复算；
- `fill` 覆盖 09:30 前 / 后、周末、缺开盘 → `not_fillable`；
- 个股结算缺价 → 全口径 `unscorable`；只有 ETF 缺价 → 现金口径照算；
- 迟到超过 3 个交易日 → `late`；
- 自助法：固定种子可复算；W < 3L 返回 None；
- 判定按协议 §6 的顺序互斥；
- 漏斗与缺失率按协议 §6 的分母计算；
- 脚本对一个构造的小账本跑通并输出 Markdown。

**T5 判据**：
- 卡片首屏符合总设计 §3.5；
- 两栏不相乘；
- 窗口来自 `classify_decision_event`；
- E1/E2 做归因；
- 读上一卡；
- 调用 `save_trade_decision`；
- `dev-research.sh --decision` 能启动。

## 2. 验证方式
- **单元**：`.venv/bin/python -m unittest tests.test_key_moments_open tests.test_decision_ledger tests.test_decision_events tests.test_decision_scoring tests.test_stock_data_tools`（pytest 未安装）。
- **T1 真实依赖**：重建表，并与旧表逐行比对 `outcome`。
- **T3 真实依赖**：两只股票的历史 as_of 实跑。
- **集成**：主会话整合后跑全部上述测试；在 MCP server 进程里列出工具。
- **端到端**：T6 的 12 个案例（Codex terra 实跑），用 `score-decisions.py` 对回放记录评分。
- **判定**：
  - 通过：所有判据满足，并且 T6 达到子设计验收；
  - 部分通过：单元与集成通过，T6 未完成；
  - 失败：任何“必须保留”被破坏。

## 3. 临时执行结果
- **T1–T4**：已交付，并按两轮 Codex Astra 复核返工（记录在 `.local/runs/p1-review-20261122/answer.md`、`answer2.md`）。执行者证据见 `evidence/decision-card-t1.md` … `t4.md` 的正文与“返工”节。
- **整合（主会话）**：
  - `server.py` 注册 `classify_decision_event`、`get_prior_trade_decision`；
  - `save_trade_decision` 在服务端重判 group / event_date / benchmark，并用重判结果组装 event（调用方传的事件详情不入账）；
  - 回放有效时间为当日 23:59:59 NY，与工具的裸日期截止一致，回放日必须已经结束；
  - no_sector 时相对概率为 null；
  - 上一卡须同 ticker、更早、同为实时或同为回放；
  - 新增 `tests/test_decision_integration.py`。
- **计划纠错**：
  - T3 的 MCP 函数放在 `decision_tools.py`（避免与 T1 同改 `reference_tools.py`）；
  - E1/E2 只有同日才算重叠，否则取最近事件日（复核第 2 条）；
  - 决策卡的 7 个必需标题由 T5 定下，T2 照此校验。
- **验证**：160 个单元与集成测试通过（2026-11-22）；Astra 复核第 1–7、9、10 条已解决，第 8 条（中期快照按整周取）T4 返工中。
- **T6**：12 个案例实跑中，`.local/runs/p1-t6-20261122/`。
- **延后到 P2**：`selection` / `failure` 行的字段与 `tier`；扫描报告是否冻结副本进仓库。

## 4. 主会话复核与收口
- （待填）
