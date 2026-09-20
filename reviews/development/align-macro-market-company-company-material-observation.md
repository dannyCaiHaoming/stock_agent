# Company 材料覆盖观测

## 当前持仓范围

使用已归档 `capture-futu-client-research-data` 验收中确认的三只普通股：`US:COMMON_STOCK:ALB`、`US:COMMON_STOCK:MRVL`、`US:COMMON_STOCK:WOLF`。该历史验收已记录 3/3 SEC + Yahoo + Moomoo SG 冻结包与公司报告消费；本 Change 不复制当时的私人运行产物。

## 新路由

- SEC Gate 中已解析的 `earnings_release` / `management_discussion` 自动投影为 `ISSUER_MATERIAL` + `BODY_VERIFIED`，正文仍通过绑定 Evidence ID 查询，不在 dispatch 内重复整段正文。
- `sec_issuer_guidance_candidate_text` 只列为发行人指引候选，`yahoo_earnings_trend` / `yahoo_recommendation_trend` / `moomoo_analyst_consensus` 列为第三方预期，两者不互换。
- OpenAlex 独立研究只在取得 `BODY_VERIFIED` 正文时进入 `INDEPENDENT_RESEARCH`；搜索结果始终为 `LEAD_ONLY`。

## 2026-09-20 真实尝试

截止时点 `2026-09-19T15:53:41Z`，使用固定 adapter `openalex-public-research/1.0.0` 各执行一次有界检索：

| 证券 | 候选 | 搜索 raw hash | 正文尝试 |
| --- | ---: | --- | --- |
| ALB | 10 | `d7ae1471950dd7910fc3c25bc636616c065ea2606219eafa07f12b129abbe271` | `PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED` |
| MRVL | 10 | `d712330ef2c1c35f76b5237d6c3c5026e19ad466300d4f61e4935929fc9b667d` | `PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED` |
| WOLF | 10 | `7bdfa1868ac4ce2c2c3096750e46dbe8e64ebcb0b0be1d3e19c303c31abb73f0` | `PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED` |

三次检索均 HTTP 200；因当前未配置 `OPENALEX_API_KEY`，正文获取在请求前被本地契约拒绝。因此独立研究增强当前是 `BLOCKED_CONFIGURATION`，不计作已读正文；这是任务允许的受限研报结果，其影响是 Company 报告只能使用已冻结的 SEC 发行人材料和三源预期，不能声称完成多份独立研报正文对照。
