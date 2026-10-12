---
name: research-report-analysis
description: 自动发现、核实、读取并比较公开公司或行业研报，区分事实、转引、观点、预测和估值假设，并说明其对已有研究主张的作用。
metadata:
  version: "1.4.2"
---

# 公开研报读取与比较

资料准备 invocation 可依据持仓与核心问题构造至多三条查询，并调用明确授权的 `research_search`、`research_fetch` 只读工具。所有调用必须使用 packet 提供的 run/agent/invocation/security/cutoff 身份；不得自行更换证券或运行目录。正式分析 invocation 只能读取任务允许的冻结 `verified_documents` 和通过 PIT Gate 的 Evidence（含许可供应商章节），不继承搜索权限，也不能调用通用 Web 补充。

只有 `verified_documents` 中允许的 `report_document` 才可作为文档；旧完整草稿须原样写入 `documents`，显式新版 `submission_contract` 草稿选择其 `document_id` 后由程序装配元数据，两种形式不可混用。核对证券/行业、标题、作者或机构、材料类型、发布日期、原始出处、正文 hash、页码/章节、解析范围、重复/修订关系。许可章节和标题线索不凭空转换成文档。只有正文实际取得并核对后才标记 `BODY_VERIFIED`；搜索线索为 `LEAD_ONLY`。配置缺失与真实来源限制按实际工具结果区分并保留尝试产物，不能事后补写。单一独立正文来源失败不等于已准入许可章节不可读；按本任务实际覆盖保留有限研究与来源缺口。搜索摘要、评级新闻、公司宣传和转载不能冒充独立研报正文；登录或付费内容不得绕过。

内容区分已核实事实、未独立核实的转引、作者观点、预测和估值假设。同一供应商正文若同时转述管理层指引与给出作者自身预测，须按原文分别标明事实主体；发行人资料尚未交叉核验时写“供应商转述的管理层指引、未独立核实”，不能因未核实而改称作者预测。Claim 用 `evidence_refs` 引用实际读取的冻结事实或许可章节；有适用文档时才用 `document_refs`。比较须解释口径、期间、信息集、方法和假设差异，不用评级投票。

来源关系使用两条已有路径，按真实依据选择：

- 许可章节：普通 Claim 用 `evidence_refs` 引用实际读取的章节；仅在本段具体解释其对某条上游主张的支持、补充或挑战时，才填写该条 `research_claim_refs`。独立陈述供应商观点不必附带上游引用，也不为覆盖上游而多连；本段未解释的上游主张不引用。没有对应允许文档时不填 `research_relationships`，空数组合法；不能借 SEC 文档名额承载供应商观点。
- 核验文档：只有该 `document_id` 自身内容确实构成依据时，才在 `research_relationships` 中表达 SUPPORT、CHALLENGE、REVISE 或 NO_NEW_INFORMATION。每个 target 及 resulting claim 都须有对应解释；同属一家公司或报告不够。若理由承认该文档不支持该观点，就不能继续把它作为该关系来源；免责声明不能修正文档归属。

先核对目标原句及限定范围，再解释关系、填写引用。不为覆盖全部上游添加关系；供应商估值观点不等于已量化市场隐含预期，也不等于独立核验的公允价值模型。上游若只有历史收盘及受限 P/E，须保留“历史价格存在、历史倍数不是公允价值”两项边界；新供应商观点可另列，但不得说它已修订上游未被证实的公允价值核验缺口。文档修订仅引用允许的 `revision_of` 元数据，保留原报告，不静默覆盖。

通过 Moomoo OpenD 取得的 Morningstar 必须按 section 和各自更新时间解释，标记为用户有权访问的供应商观点；不得自动读取 `pdf_url` 或声明再分发许可。机构/分析师 rating summary 的推荐日与供应商更新时间必须分开，评级 URL/摘要不等于已读正文。单一 Morningstar 来源或一页评级列表不能宣称完成多机构独立研报比较。

利益关系只记录材料明确披露的内容和定位；无法确认时为 UNKNOWN，不推断独立性。准备模式输出 `ResearchMaterialPreparation`，正式模式输出 `ResearchDimensionReport` 且 `capability=RESEARCH_REPORT`。最终正式报告的 documents 必须等于 allowed `report_document` 元数据；`COMPLETE` 至少要有一份 `BODY_VERIFIED` 文档。只有一份正文时只能证明读取，不能声称完成多报告比较。正文受限须保留该来源的线索、失败原因和影响，不自动决定整份报告状态：许可章节可支持有限研究，按本次任务规则标记 `LOW_CONFIDENCE/PARTIAL`；没有可用正文或许可章节且存在配置阻断时，遵守任务的 `FAILED/FAIL` 规则，不混同为普通 `SOURCE_LIMITED`。
