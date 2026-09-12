# establish-portfolio-intake 限定验证记录

## 结论

当前实现已完成 Change 中除最终人工批准、归档、提交和推送之外的产品切片。验证结果为 `PASS`，但只覆盖 Portfolio Intake，不代表 Portfolio Council 研究链路或候选版本晋升通过。

## 能力映射

| 能力 | 实现与证据 | 结果 |
|---|---|---|
| Draft / Handoff 契约 | v2 Schema、可辨别多资产结构、确定性校验与稳定 hash | PASS |
| 截图输入 | Codex 按 `portfolio-intake` Skill 直接读取合成 PNG；未知现金保持 `MISSING` | PASS |
| 手工输入与修订 | 简洁手工入口、修订来源追加、Draft hash 变化和旧 Handoff 失效 | PASS |
| 组合完整性 | 区分 `BROKER_ACCOUNT` 与 `USER_DEFINED_PORTFOLIO` | PASS |
| 无持仓数量上限 | Schema 无 `maxItems`；十只样例完整保留 | PASS |
| 全量研究范围 | 固定 `ALL_INPUT_POSITIONS`，研究计划与 Portfolio 集合严格相等 | PASS |
| ETF / 期权输入 | 区分 `COMMON_STOCK/ETF/OPTION`；保留 Long/Short 数量和期权身份 | PASS |
| 能力缺口 | ETF/期权进入全量计划，但缺少专业 Skill 时输出 `CAPABILITY_GAP` | PASS |
| Council 输入接缝 | 生成多资产 `portfolio-council-input/2.0.0`，不获取 Evidence、不启动研究 | PASS |
| Risk 前置绑定 | 完整 Portfolio、现金及 hash 原样绑定；多资产明确要求对应 Risk Policy | PASS |
| 私人数据边界 | 真实来源与产物禁止写入仓库，账户号必须脱敏 | PASS |
| 既有 DEMO_SCAFFOLD | 27 项既有 Demo 测试通过；未修改暂停 live 路径 | PASS |

## 实际验证

- 聚焦及相邻回归：63 项通过；
- OpenSpec strict validate：通过；
- 合成 Handoff 独立校验：通过；
- 合成图片切片产物：见 `reviews/development/portfolio-intake-synthetic-example/`；
- 同一张真实截图重测：仓库外证据包 `stock-agent-portfolio-intake-v2.8oAagv`。五项持仓均被结构化；确认仅因账户完整性、业务截止时间和不可见的期权执行价/乘数被预期阻止，不再因 ETF/期权类型被拒绝；
- 完整命令、源码 hash 与结果：见 `portfolio-intake-focused-test-results.json`。

## 明确未做

- 未调用 Company Analyst、Independent Skeptic 或 CIO；
- 未运行市场数据、真实券商 API、Replay、Regression、Calibration、Ablation 或 Promotion Gate；
- 未恢复或改写 `us-equity-live-advisory-slice`；
- 未归档、提交或推送。

## 剩余门禁

ETF 与期权扩展任务 5.1–5.5 已完成。最终任务 4.4 中的使用说明、strict validate、Skill 发现和限定验证已经完成；仍需用户人工批准 Change 完成。取得批准前，任务 4.4 保持未完成。
