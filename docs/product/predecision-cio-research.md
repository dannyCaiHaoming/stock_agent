# 正反研究之后的 CIO 综合

`PREDECISION_CIO_SYNTHESIS` 是显式后续阶段，不会在普通股、多维研究或独立反证完成后自动启动。它重验同一次来源运行的 `PreDecisionResearchPackage`、正向报告、逐股反证、来源 Handoff、Gate、执行证明和哈希，在仓库外的新目录冻结输入。来源目录保持研究停止点，不写入 CIO/Risk 产物。

## 当前唯一交付级别

本阶段只交付 `RESEARCH_SYNTHESIS`：主线程 CIO 综合 Company、Macro、Market 与 Independent Skeptic，解释 MRVL 在**来源研究截止点**的判断、分析期限、关键事实推导、反证取舍、市场传导、推翻条件及观察事项。报告另列实际生成时间，区分业务前景、原时点价格吸引力与未评估的当前账户适配。估值资料不足时明确未知；分析期限不是用户持有期限。

用户在需求讨论中表示曾清仓 MRVL，系统未独立核验当前账户。来源 Handoff 只证明研究血缘，不能冒充当前持仓；无需补当前现金、SOXL 期权、Mandate 或完整组合资料。研究综合不输出 HOLD/TRIM/EXIT/NO_TRADE、BUY/ADD、目标仓位、现金安排、金额、交易数量、`risk.json` 或 `decision.json`，Trace 标记 `Risk=NOT_RUN`。积极研究判断也不等于买回建议。本阶段未开放 `PORTFOLIO_ADVICE`：宿主和直接准备入口会在模型前拒绝，不能降级后声称已完成建议。原有 fixture Council/Risk 能力保持不变。

来源身份、报告哈希、执行证明或必要正反研究未就绪时直接停止，不能以资料不足为由发布伪成功报告；合法的辅助维度缺口由 CIO 解释。CIO 只能查询冻结 Gate 内证据，不重新派发 Specialist，不自动刷新当前行情。需要当前时点判断时先重新完成上游研究，不能用今日数据回填历史 cutoff。

## 宿主运行与产物

在 macOS 宿主 Terminal 使用已有入口；来源目录和新产物目录都在仓库外：

```text
bash scripts/run-product-smoke.sh --stage predecision-cio-synthesis \
  --source-run <完成正反研究的 run 目录> \
  --target-security-id US:COMMON_STOCK:MRVL \
  --requested-level RESEARCH_SYNTHESIS \
  --model gpt-6-luna \
  <新的仓库外产物目录>
```

默认开发测试模型为 `gpt-6-luna`；若本机 CLI/账号不支持，运行保留失败证据，不静默换模型。对已冻结 MRVL 包使用此前获批的 `gpt-5.6-terra` 需显式指定并记录实际模型。本阶段仅允许 `SOURCE_CUTOFF`；请求 `CURRENT` 会在模型前拒绝，当前行情研究须先准备新的上游包。

运行后用 `check-predecision-cio` 只读核验。合格研究级运行保存 `cio-research-synthesis.json`、同源 `report.md` 与 `decision_trace.json`；每次新运行有新 `run_id`，来源报告身份不变。旧 advice 实验产物保留原文件供人工只读审计，不作为当前可用能力，也不迁移成研究报告；当前 checker 只接受研究级，不能重新认证旧 advice 为 PASS。本阶段不包含回测、自动监控、Runtime Eval 或候选晋升。结果仅供研究参考，不构成投资或交易指令。

成功检查还核对同一运行的宿主进程结果：退出码、超时、失败原因、终态与受保护产品文件前后完整性；任一项缺失或不一致均不返回 PASS。模型工作区在仓库外，原生沙箱保留，源码目录不作为可写根。此处只证明上述有限运行边界及受保护产品文件前后未变化；全进程 OS 强制只读尚未验证。
