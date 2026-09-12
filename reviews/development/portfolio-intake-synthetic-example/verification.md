# Portfolio Intake 合成截图限定验证

## 范围

当前 Codex 读取 `portfolio-intake` Skill 及其契约说明，并直接检查合成截图。验证只覆盖：图片可见事实提取、缺失字段保留、用户补充、一次确认、Handoff、全持仓研究计划、多资产 Council 输入转换及 Risk 前置绑定。

本验证没有调用 Company Analyst、Independent Skeptic 或 CIO，没有获取市场 Evidence，没有生成 Thesis、买卖动作、置信度或投资报告，也没有启动 `portfolio-council`。

## 输入与处理结果

- 合成截图：`evals/fixtures/portfolio-intake/synthetic-account-page.png`
- 截图 SHA-256：`6b7ae242ac6b778ca90f763caf4018918a638edca006e4fda0261421ef225626`
- Skill SHA-256：`e92ff17a0f64756949a500072e6e4a61b91f8524ff074901c22ad220906371f8`
- 初始 Draft hash：`39e6dfa9fcf6e616d7b13b55e3083126768d3b009739bb2a980d89782331d3e8`
- 补充后 Draft hash：`51a6c3ea4f7188162b6521dc7cf625a02615fd80e3af35f89b2bff9e48f58fec`
- Handoff hash：`2548523b51c1109600a137e3834d0209d98e33d07ab4b5dbf22066e3d30b5128`
- Portfolio hash：`8206efa60c564d538bdadc87a5d76cb040b342a8c76aaf19dcb298ad46cd0ebc`
- 组合持仓数：5
- 研究计划项数：5
- 研究范围：`ALL_INPUT_POSITIONS`

初始 Draft 将现金保留为 `MISSING`。合成用户补充现金后 Draft hash 改变；只有显式确认当前新 hash 后才生成 Handoff。Handoff 中五只持仓与五个研究计划项一一对应，分批大小为 3，但没有截断第二批持仓。

## 产物

- `portfolio-draft-initial.json`：图片可见事实及未知现金；
- `portfolio-draft-confirmable.json`：追加用户补充来源后的可确认 Draft；
- `portfolio-handoff.json`：绑定确认和全量组合；
- `council-portfolio-input.json`：`portfolio-council-input/2.0.0` 契约转换结果；
- `risk-input.json`：绑定同一完整 Portfolio hash 的 Risk 前置输入；
- `draft-summary.md`：中文集中确认摘要。

结果：`PASS`。该结果只证明 Intake 纵向切片，不证明 Council 研究质量、真实券商截图兼容性或版本晋升。
