## 1. Draft 与 Handoff 契约

- [x] 1.1 增加版本化 `PortfolioDraft` 与 `PortfolioHandoff` Schema；验证 Draft 可表示缺失/冲突，Handoff 必须绑定当前 Draft hash、一次确认、来源时间和 `research_scope: ALL_INPUT_POSITIONS`。
- [x] 1.2 实现 Draft 创建、手工输入合并、用户修订和稳定 hash；验证修订保留原来源并使旧 Handoff 失效。
- [x] 1.3 实现 `BROKER_ACCOUNT` 与 `USER_DEFINED_PORTFOLIO` 完整性校验；验证缺页账户不能确认，自定义组合可按声明集合确认。
- [x] 1.4 实现最小确定性校验，覆盖数量、现金、币种、重复证券、支持资产、来源闭合和私人路径；验证未知现金不等于零、成本缺失不单独阻断。
- [x] 1.5 移除 Intake 中所有持仓数量上限和焦点子集概念；用超过三只的样例验证 Handoff 无截断且研究集合等于全部 positions。

## 2. portfolio-intake Skill

- [x] 2.1 创建并注册 `portfolio-intake` Skill，定义截图、手工输入、集中澄清、一次确认和 Handoff 输出；验证不会研究股票、生成动作或自动启动 Council。
- [x] 2.2 定义截图结构化提取格式和不确定状态；验证 Codex 原生图片理解只写可见事实，不依赖 Python OCR 或静默猜测。
- [x] 2.3 实现中文 Draft 摘要和集中澄清接缝；验证普通“继续”不算确认，确认后修改任一事实会回到新 Draft。
- [x] 2.4 复用仓库外产物路径并脱敏账户引用；验证真实附件、完整账户号和私人持仓不会写入 Git 工作区。

## 3. Council 与 Risk 接缝

- [x] 3.1 实现 Handoff 构建和独立校验，将全部确认持仓转换为版本化多资产 Council 输入，不包含市场 Evidence、Thesis 或动作。
- [x] 3.2 生成全持仓 Council 前置研究计划；验证每个 position 恰好对应一个待研究对象，任意未覆盖、重复或额外证券均失败。
- [x] 3.3 为未来大组合保存总数、完成、待处理和失败状态，并验证分批参数不改变研究集合；本 Change 不执行真实研究批次。
- [x] 3.4 确保 Risk 前置输入绑定完整 Handoff Portfolio hash 与全部持仓/现金；使用十只持仓样例验证后序持仓不被忽略。
- [x] 3.5 核对 fixture、DEMO_SCAFFOLD 和暂停 live 路径保持原行为；共享文件不能安全分离时停止，不覆盖暂停修改。

## 4. 限定验证与收尾

- [x] 4.1 增加合成手工输入、清晰截图、缺现金、账户缺页、用户定义组合、多图冲突、十只持仓、重复证券和不支持资产样例，确认不含真实账户信息。
- [x] 4.2 运行聚焦确定性测试，覆盖 Schema、来源、Draft 修订、一次确认、声明范围、无持仓上限、全量研究计划、Handoff、Risk 输入、隐私和失败传播；不启动研究 LLM 或高级 Gate。
- [x] 4.3 使用一张合成截图直接执行一次 `portfolio-intake` Skill，保存 Draft → 用户补全/确认 → Handoff → 全持仓前置计划产物；确认没有 Specialist、CIO、市场 Evidence 或投资报告。
- [x] 4.4 更新中文使用说明并执行 OpenSpec strict validate、Skill 发现和限定差异复核；取得用户人工完成批准前不归档、不提交、不推送。

## 5. ETF 与期权输入扩展

- [x] 5.1 将 Draft/Handoff 升级为可辨别的 `COMMON_STOCK`、`ETF`、`OPTION` 契约；支持非零带符号数量，并为期权增加标的、CALL/PUT、到期日、执行价、合约乘数和合约标识字段。
- [x] 5.2 更新确定性校验、手工输入、修订、摘要、hash 与重复身份规则；验证 ETF 不伪装为股票，空头期权数量被保留，零数量和不完整期权身份 fail closed。
- [x] 5.3 更新 Handoff、Council 前置计划及 Risk 输入，确保全部多资产持仓一一保留并声明所需研究能力；缺少 ETF/Options 研究能力时明确停止，不扩大现有交易或 Risk 权限。
- [x] 5.4 增加 ETF、Long/Short Option、重复合约、截断合约和股票+ETF+期权组合样例及聚焦测试；不启动研究 LLM 或完整 Gate。
- [x] 5.5 使用同一张真实持仓截图在仓库外重新执行 Intake，保存 Draft、集中澄清及确认尝试；核对所有五项持仓均被结构化保留，任何不可见期权字段不得猜测。
