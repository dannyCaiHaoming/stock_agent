# 受限实验结案记录（2026-09-26）

## 结论与授权

- 结案：`EXPERIMENT_CONCLUDED_WITH_ROLLBACK`，仅为记录标签，不新增 Runtime 状态。
- 原消减质量目标：`NOT_ACCEPTED`；不得称为精简成功、研究质量提升或生产晋升。
- 回退后完整真实 Smoke：`NOT_RUN`。用户在已说明此限制后明确批准“记录下问题，然后归档”，本次按有界实验结案处理，不声称满足通常上线的真实 Smoke 验收；不追加第六次模型调用。
- 独立只读复核：`/root/company_closure_review`，`PASS_WITH_DECLARED_LIMITATIONS`。复核实际配置选择、字段查询授权与交付引用、第五次原始失败及 hash，未发现阻断受限结案的问题；未额外运行模型或测试。人工批准不由 Reviewer 代替。

## 保留与回退

普通股恢复完整 `runtime_company_analyst.toml`（3.0.20）及原研究说明，精简实验文件仅保留追溯，不被默认入口加载。保留精确字段查询、全期间原事实、授权交集与超限整次拒绝、按真实附件权限显示工具的局部修复。其他 Company 模式、Evidence/Gate/Schema/PIT 和投资判断职责不变。

主规格只同步以上实际保留行为，不同步精简成功承诺。第五次报告仍为 `FAILED / COMMON_STOCK_REPORT_SET_INCOMPLETE`；零退出码和工具成功均不是研究成功。

## 待解决问题（不混入本次实现）

1. **提交纠错缺少闭环**：Company 报告的结构/引用错误被正确拒收，但当前缺少有界反馈修正路径。后续可单独设计一次受预算约束的反馈纠错；不能用 Python 补写投资判断、虚构支撑或把“无证据”当作可机械修复的格式问题。是否重试必须先明确授权和终态，保留原失败。
2. **资料可用不等于模型取用**：第五次已使用字段查询，但没有查询完整 FY2026 EPS，且提交无支撑 Claim。后续先区分未查询、已交付未采用、不可比和真实缺失；不要硬编码 MRVL/EPS 必查表，也不据此断言精简配置必然造成退化。
3. **目录是主要输入负担**：约 199402 字节目录占旧 packet 约 90%；指令缩短约 62% 仅让整体 packet 缩短约 2%。后续若继续优化，应单独评估目录表达与按需取用，并保留授权范围、全期间语义及引用链，不新增通用框架。
4. **质量收益仍未证明**：现有对照受设置和环境差异限制，不能证明因果；完整配置回退也不保证消除遗漏或格式错误。未来重新启用精简 Profile 需新授权和明确验证，不沿用已耗尽的研究额度。
5. **独立研报引用缺陷**：`RESEARCH_REPORT → DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING` 继续单独保留，不作为本次已修复项。

## 检查与发布范围

已有四模块聚焦测试 203/203 通过；最后技能集合兼容修正后普通股测试 97/97 通过。这里均为确定性检查，不是回退后的真实研究。详细版本、原始证据路径和 hash 见基准记录；临时运行目录不随 Git 发布，不能假定仓库副本含完整原始运行证据。

归档发布前再次执行 `python3 -m unittest tests.test_native_evidence_gate tests.test_common_stock_research_contracts tests.test_multidimensional_stage tests.test_independent_skeptic_stage`，203/203 通过（5.065 秒）；主规格 strict、全部 20 项主规格验证和差异空白检查通过。暂存文件的私钥/常见令牌模式扫描无命中；未纳入原始会话数据库或运行产物。

仅归档本 Change、同步 common-stock-holding-analysis 规格，提交两个 Runtime 文件、相关测试、本实验配置和复盘记录。排除 Tiger、Luna 模型设置及其共享文件修改；保留其工作区现场。本结案不创建或实施后续 Change。
