---
name: research-report-analysis
description: 自动发现、核实、读取并比较公开公司或行业研报，区分事实、转引、观点、预测和估值假设，并说明其对已有研究主张的作用。
metadata:
  version: "1.2.0"
---

# 公开研报读取与比较

资料准备 invocation 可依据持仓与核心问题构造至多三条查询，并调用明确授权的 `research_search`、`research_fetch` 只读工具。所有调用必须使用 packet 提供的 run/agent/invocation/security/cutoff 身份；不得自行更换证券或运行目录。正式分析 invocation 只能读取冻结且通过 PIT Gate 的 `verified_documents`，不继承搜索权限，也不能调用通用 Web 补充。

每份材料写入 `documents`，核实证券/行业、标题、作者或机构、材料类型、发布日期、原始出处、正文 hash、页码/章节、解析范围、重复/修订关系。只有正文实际取得并核对后才标记 `BODY_VERIFIED`；搜索线索为 `LEAD_ONLY`。缺 `OPENALEX_API_KEY` 等配置错误输出 `BLOCKED_CONFIGURATION`，实际来源或正文路径受限输出 `SOURCE_LIMITED`；两类状态都必须引用工具保存的实际尝试产物，不能由 Agent 事后补写。搜索摘要、评级新闻、公司宣传和转载不能冒充独立研报正文；登录或付费内容不得绕过。

内容必须分为：原始资料已核实事实、研报转引未独立核实、作者观点、预测、估值假设。每条 Claim 通过 `document_refs` 引用文档，通过 `evidence_refs` 引用冻结事实；文档本身不能替代事实 Evidence。比较时解释口径、期间、信息集、方法和假设差异，不用评级投票。对具体已有主张在 `research_relationships` 中标记 SUPPORT、CHALLENGE、REVISE 或 NO_NEW_INFORMATION，并说明理由；目标必须引用当前或上游允许的 Claim，结果必须引用本报告 Claim。修订通过 `revision_of` 和关系记录保留旧新版本，不静默覆盖。

通过 Moomoo OpenD 取得的 Morningstar 必须按 section 和各自更新时间解释，标记为用户有权访问的供应商观点；不得自动读取 `pdf_url` 或声明再分发许可。机构/分析师 rating summary 的推荐日与供应商更新时间必须分开，评级 URL/摘要不等于已读正文。单一 Morningstar 来源或一页评级列表不能宣称完成多机构独立研报比较。

利益关系只记录材料明确披露的内容和定位；无法确认时为 UNKNOWN，不推断独立性。准备模式输出 `ResearchMaterialPreparation`，正式模式输出 `ResearchDimensionReport` 且 `capability=RESEARCH_REPORT`。正式报告的 documents 必须原样复制 allowed `report_document` 元数据；`COMPLETE` 至少要有一份 `BODY_VERIFIED` 文档。只有一份正文时只能证明读取，不能声称完成多报告比较；正文受限时明确 `SOURCE_LIMITED`，并保留线索、失败原因和影响。
