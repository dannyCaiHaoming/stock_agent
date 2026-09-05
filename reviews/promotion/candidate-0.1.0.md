# 候选版本 0.1.0 晋升评审

状态：**已获人工批准，候选版本尚未启用为生产默认版本**

## 技术证据

- 版本清单：`product/version-manifest.json`
- Capability Map：`evals/capabilities/registry.json`
- Eval 报告：`evals/reports/candidate-0.1.0.json`
- 架构边界评审：`reviews/architecture/mvp-boundary-review.md`
- OpenSpec Change：`establish-llm-native-portfolio-council`

该候选版本只使用 fixture/reference 数据，并且只提供研究建议。它不包含生产数据供应商、券商接入、账户修改、订单路由或真实交易能力。技术验证可以生成本候选记录，但只有人工评审者可以将状态改为批准或启用版本指针。

## 人工决策记录

- 决策：批准候选版本 `0.1.0`
- 评审人：项目所有者（用户）
- 评审时间：`2026-09-05T13:10:48+08:00`
- 理由：项目所有者已对整体架构和交付产物进行审阅，确认整体大致没有问题，同意候选版本通过人工评审门禁。
- 批准范围：fixture/reference MVP；本次批准不授权连接生产数据供应商、启用真实交易或修改任何券商及金融账户。
- 回滚条件：出现硬风险约束回归、Evidence/Trace 血缘完整性破坏、运行时越权写入、未来数据泄漏，或留出集发生实质退化时，恢复上一已批准版本并保留全部 Trace 与评估记录。
