## MODIFIED Requirements

### Requirement: 正反交接包必须通过显式独立阶段进入研究级 CIO
系统 SHALL 提供 PREDECISION_CIO_SYNTHESIS 阶段，从经过重新验证的 PreDecisionResearchPackage、对应输入类型的来源绑定和显式研究请求启动：持仓分支绑定来源 Handoff，非持仓分支绑定 SINGLE_STOCK_RESEARCH 请求。新运行 SHALL 接受已在该来源包完成正反研究的目标美股普通股，不再只按 MRVL 样例限制准入；证券身份和目标研究范围仍须模型前严格验证。系统只发布 RESEARCH_SYNTHESIS，MUST 拒绝 PORTFOLIO_ADVICE，不自动降级后假称已完成建议。阶段 MUST 使用新 run_id 和仓库外独立输出目录，保留 source_run_id、package_hash、源请求及新请求身份。原独立反证阶段停止点、complete_portfolio_decision=false 和源产物 MUST 保持不变。CIO SHALL 由现有宿主入口下的 Codex 主线程执行，不新增 CIO 子 Agent 或第二套编排器。

#### Scenario: 用户研究已清仓的 MRVL
- **WHEN** 用户指定历史合格 MRVL 交接包并明确请求 CIO 研究综合
- **THEN** 新阶段在独立运行中综合原截止点的正反研究，标注当前持仓适配未评估，不要求用户提供新的账户截图或把 MRVL 伪装为现持仓

#### Scenario: 请求本阶段未发布的持仓建议
- **WHEN** 调用方选择 PORTFOLIO_ADVICE
- **THEN** 宿主在模型前明确拒绝该级别，不产生持仓动作、Risk 通过或建议文件

#### Scenario: 只运行研究阶段
- **WHEN** 用户仅请求多维研究或独立反证
- **THEN** 原阶段仍停止于研究产物，不自动调用 CIO 或 Risk，也不因缺少决策报告而失败

#### Scenario: 新 ALB 正反研究进入 CIO
- **WHEN** 同源单股 ALB 交接包通过全部原有研究门禁且显式请求综合
- **THEN** CIO 实际加载 ALB 目标约束与完整正反报告，输出同源综合，不注入 MRVL 已清仓或半导体样例上下文

#### Scenario: 综合面对上游已保存但局部内容有误的报告
- **WHEN** 原报告的缺口理由、正文引用或计算关联有具体疑点
- **THEN** CIO完整读取同源报告，对最终实际采用的相关主张核验本批合法依据并明确判断影响；本期有限版不要求逐项修复全部未采用的上游错误，但交付限制须保留这些疑点，不能把未查询说成来源不存在。不给上游改状态或自动补写引用；最终采用内容的正确性、重要反证准确性及核心判断支持仍受独立内容复核和原Evidence门禁约束

### Requirement: CIO 准备必须验证来源闭包与时点
系统 MUST 验证源交接包及其 forward bundle、逐股反证、执行证明、完整 coverage、原始报告引用和内容哈希，要求 consumability=DOWNSTREAM_READY。CIO 输入 MUST 绑定相同来源输入类型、对应请求身份、目标、decision_cutoff 与 Gate；持仓分支仍校验原 Handoff 与 portfolio hash，非持仓分支须校验真实单股请求 hash，不用空值或伪 Handoff 绕过。源研究 run_id 与新 CIO run_id MUST 分别保留，不改写源报告身份。CIO MUST 只能查询该冻结 Gate 允许的 Evidence，不得获得原始缓存、其他运行或未来事实。承载事实的输入 MUST 保留 source_id、as_of、retrieved_at。旧研究包在新运行中的使用 MUST 明确为原研究截止点的综合，不能标记为当前行情或当前持仓判断。

#### Scenario: 资料篡改或报告来自另一批研究
- **WHEN** 任一报告 hash、证券身份、Gate、cutoff、执行证明或对应输入绑定不匹配
- **THEN** 系统在 CIO 前报告 FAILED_VALIDATION，保留具体错误，不启动模型且不生成建议性 NO_TRADE

#### Scenario: 历史报告不冒充当前研究
- **WHEN** MRVL 的来源 cutoff 早于实际生成时间
- **THEN** 报告分别展示两个时间，说明判断适用于来源 cutoff，不把新价格与旧结论拼接

#### Scenario: 目标未在来源中研究
- **WHEN** 请求 ALB 综合但源包只有 MRVL，或两分支输入类型不同
- **THEN** 模型前拒绝，而不是只替换请求的 ticker、Schema const 或报告标题
