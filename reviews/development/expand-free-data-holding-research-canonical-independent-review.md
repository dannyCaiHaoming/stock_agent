# expand-free-data-holding-research canonical 独立复核

TASK_8_4_REVIEW: PASS

复核日期：2026-09-16

## 复核范围与方法

本记录是对 OpenSpec Change `expand-free-data-holding-research` 的最终限定独立复核。已读取当前 `proposal.md`、delta spec、`design.md`、`tasks.md`、当前聚焦源码差异、`reviews/development/expand-free-data-holding-research-verification.md`，并直接重新读取和核对底层 canonical 目录 `/private/tmp/stock-agent-canonical-handoff-20260915-v4`，没有把既有验证记录中的结论当作替代证据。

本次未运行测试、产品 LLM、网络请求、Regression、Replay、Calibration、Ablation、Promotion 或完整 Gate，也未启动新的产品研究。除本复核文件外未编辑任何仓库文件。工作树已知很脏；复核只把 Change 的聚焦文件和指定产物纳入结论，不将无关用户或其他 Agent 修改归入本 Change。

## 源码快照标识

- `git HEAD`: `d738110e712ee94de38488478556e7400453a948`
- 完整 `git status --porcelain=v1 -z --untracked-files=all` 条目数：`315`
- 上述完整 status 字节流 SHA-256：`0aa95493b0c470bd9321ca2d8b24ebdeb837479ac3c9f439868e35cda09a56ce`
- canonical implementation 聚焦 7 文件的有序 `shasum -a 256` 输出聚合 SHA-256：`d86375723d4f36a4be92f489d4e6a43deb84836f652d2df76ee5bd121be86efb`
- SEC 接缝聚焦 5 文件的有序 `shasum -a 256` 输出聚合 SHA-256：`6fbc34bf1aa1d5a0a42f9f550c8dbd7416e8680edd8dfc59bd04a12f0973562e`
- 上述 12 文件合并后的有序聚合 SHA-256：`28517632fb5e66bc461b1f58f206aaf829e64e9da6780b02293d53f32f3ff987`

canonical proof 声明的 implementation hash 均与当前磁盘文件一致：

| 文件 | SHA-256 |
| --- | --- |
| `product/council/multidimensional_output.py` | `fd5bd0af3e58d0d6e9d7472314aee6b6fa104233285ba74193a6021a5876c937` |
| `product/council/multidimensional_research.py` | `f3983fac80be3f834845e097d8dbeab6d5686b68a87650db72d493f518a406c8` |
| `product/runtime/cli.py` | `930c48f59479a2bb1944644e33fa58c26a6f199377cd572737362235cae372ae` |
| `product/runtime/multidimensional_stage.py` | `f0ed08e74b42d34d82fce422ad6add75c1918ceda03a9474179bf61972806339` |
| `product/schemas/runtime/holding-research-bundle-v1.1.schema.json` | `9dc67e23a875382f21d15410d70d5b6f7ad0719983e8e9d5e2acedc166952836` |
| `product/skills/portfolio-council/SKILL.md` | `c222ef7371fb569eb32a86acc36ce537a33d1fb95e2eef705ee6014ee12b25fa` |
| `product/version-manifest.json` | `cdc6abdc5d3cd6cb1c827fc6e3e71ce6bfd89c0159c7eca8537f4005a3802a03` |

SEC 接缝聚焦源码 hash 也与其验证记录和 v37 证据一致：

| 文件 | SHA-256 |
| --- | --- |
| `product/mcp/live/sec.py` | `9ea5ac7e22c6c409da4043d1e9a3178ab2eedf206cf4fadcd06dc9466e72c0e9` |
| `product/mcp/live/sec_client.py` | `297e114dfde734d5a5182e534b52ebd0e428696cc99e1dec00e3d3d9ab471760` |
| `product/mcp/live/ownership.py` | `b5f3158ac5c95b3f1c5d478f39e05c543d85eb084968cce4cba5d2cde7f5a821` |
| `product/mcp/live/collection.py` | `1b1f9df3c23f5dcf3c49dfd0621baf7a5feccfaadcc03f997bd80881431b14c5` |
| `product/runtime/evidence_gate.py` | `96972f53740a596b63bf3f72dfb83e50fa2951797e31307a534aa0e7abb71c33` |

## canonical package 直接核对

canonical run 为 `host-common-stock-925bc3c9-3362-4d19-b825-bdca2e5c2a4f`，统一 `decision_cutoff` 为 `2026-09-15T03:22:26.059573Z`。对 proof 声明的输入逐项重新计算文件 hash，均与磁盘一致：

| 输入 | SHA-256 |
| --- | --- |
| v32 base manifest | `4d2dec18b153e326d75ef19651e87fb8929d9f84489ba1094b318639f6475efd` |
| v32 base Gate | `5c98c9c95bc88b22bbaf2353afc4a93383b139cd7832d3bc9d713d393facf6a7` |
| v32 base bundle | `478c9a2e4a282612620dc956c9d286a250414f3196d400c73158e1583365c396` |
| COMPANY_RESEARCH source manifest | `3c61e22e89fa0fb19d26f718a37ab58e38b86714e95a9da3c09ae6aa43b40d3b` |
| COMPANY_RESEARCH source Gate | `08181494c0ea84a65bcbe27fbb6a6dccbd8b6f38626d620acde60654b786d2d4` |
| v34 manifest | `eba1ad64e596e331b8fe306a8ba882bc95e3f4fd7d3d7efee25d0279dd09e548` |
| v34 Gate | `7f19a32f224a572958b7ee39319dfedebf4e1734ea6b97c7c63134b1a84c3dd6` |
| v34 task proof | `a4b153221055006cd983d497d0ff5ed5dcd081b3b2089e7300c1835ea2dfe577` |
| v34 report | `15193f5b1c23d63edc55b0ba8f80718e061e3d4358206fac99fec00689f9c823` |
| v37 manifest | `2eb8b76f3fc185b8490af9e976ebda5fd10c6ac4a25996a670f11cd721569fb2` |
| v37 Gate | `7bf83477c6046f5c5195537a3b74442bb63b3bac050047a83fa75ef31500504b` |
| v37 task proof | `5440c455057d8b4eff7fd08b642005e2de0b6917fc66262f54b56eca5994e36e` |
| v37 report | `ec616be297bf916f5924b850936c766bbbbf9ab0a61725bf9a14fce5245cc5a1` |

canonical 输出文件的实际 SHA-256 为：

| 输出 | SHA-256 |
| --- | --- |
| `run_manifest.json` | `0c0bec37d9ab4b6d59ae8b871ca9dc7463463c531643d609fa11c1538e9de5e5` |
| `evidence/gate.json` | `875c4dce57ba9858f13868f217e829b554fecd5d9d44ebf7e089d5ecbfc833d5` |
| `research/holding-research-bundle.json` | `e5ecb3336b06e053ea4c5a75e625e6f62c370c9ad881265662bc9e66da040b41` |
| `research/holding-research-bundle.md` | `1d82a9973fdfc8601fd050965a9a25f6d823d658b919f2f5e776ea2cfee31353` |
| `research/canonical-package-proof.json` | `98429c3e4699686896e43c7fe11f4a389f5cd0b52d453f361baea93ea50cb91c` |
| `research/consumption-proof.json` | `706384202f912c6dc3a4f4f2a22fa47a682c33a6b5ed0d853f640a6b0a2896d8` |

除文件 hash 外，还重新按各自 canonicalization 规则核对了内部 hash：`canonical-package-proof.proof_hash` 为 `15a15941263f545ab9dc865c7b2ebfb0ce6d366983e6d1e32b777204d34b1791`，bundle 内部 hash 为 `41d453ac4771f1c8a5f1635acf04c3d9f48526e02c0d07117ac0d45409f40c09`，consumer proof 内部 hash 为 `672ac2b33bc70e2eaa08c86a1c5f8942c61bbe7e30bfedb7215706ed956be1f8`，Gate 内部 hash 为 `e30725470d5002fa79a347053cf67fa578b03699df79c5f9d02b2c3f0a975017`，manifest 内部 hash 为 `3e3199d7e099a5a9e5351eb5b7abe799e8f2d4286477d918e60a79778b9ea194`；重算结果均一致。bundle 与 consumer proof 的 bundle/Gate 绑定一致，consumer inventory 中 22 份报告的路径、身份和文件 hash 均能闭合。

## Evidence closure、PIT 与导入闭合

- canonical Gate 有 `7569` 条 allowed evidence；ID 唯一且 allowed entries 与 allowed ID 集合一致。
- 全部 `7569` 条均具备 `source_id`、`as_of`、`retrieved_at`；未发现晚于 canonical cutoff 的 `as_of`、`retrieved_at` 或 `published_at`。
- 22 份研究报告全部存在，报告引用 hash 与报告内部 hash 均一致；共引用 105 个唯一 evidence ref，未发现相对 canonical Gate 的悬空引用。
- 3 份 `COMPANY_RESEARCH`（ALB、MRVL、WOLF）均完成 `REVALIDATED` 导入。源 JSON/Markdown 与复制件逐字节一致，source/copied request hash 和 report canonical hash 均闭合；源 cutoff `2026-09-12T17:01:08.945940Z` 早于目标 cutoff，且组合/交接绑定一致。报告状态分别为 ALB `LOW_CONFIDENCE`、MRVL `COMPLETE`、WOLF `LOW_CONFIDENCE`，没有被包装成超出证据的确定性结论。
- bundle 中 28 个待反证问题 ID 唯一；逐份报告从 observation/invalidation 条件独立重建后数量与集合一致，问题到报告、claim 的引用均闭合。
- bundle 的 56 个 artifact ref 均存在。

## Design 第 5 节与 Task 8.4 内容抽查

| 维度 | 内容核对与缺口出口 |
| --- | --- |
| Technical | ALB/MRVL/WOLF 均覆盖 20/60 日趋势、相对 SPY、波动/回撤、量价关系及推翻条件；252 日历史因样本仅 240/250、少于所需 253 日而明确走缺口出口。 |
| Fundamentals / events | 三家公司均覆盖业务驱动、利润与 OCF/capex、估值假设限制、事件或一次性因素，并显式记录未知项与观察条件。ALB 的锂价/资产处置、MRVL 的 AI/客户/供应及期间差异、WOLF 的 fresh-start 可比性和流动性边界均有实质内容。 |
| Research reports | 三家公司均因缺少 `PUBLIC_RESEARCH_CONTENT_API_KEY` 而走明确的 source-limited/失败出口，正文、观点关系和 claims 不可用；没有把仅有候选或标题包装成 `RESEARCH_VALIDATED`。 |
| Industry comparison | ALB-DD、MRVL-ALAB、WOLF-PLAB 均有实际可比数据与行业/公司传导说明，同时明确期间、业务可比性、样本或未授权计算限制；没有机械排名。 |
| Macro / market | canonical v32 报告使用官方 10Y/CPI/失业率及公司债务/现金，明确缺少 SPY 序列。v34 展示了 SPY 与 ALB/WOLF 差异化传导能力，但因输入绑定不兼容被排除，仅作为能力证据。 |
| Ownership | canonical v32 对三家公司均诚实标为证据不足。v37 只证明免费 SEC Form 4 接缝与受限语义能力，不进入 canonical 用户研究。 |
| Options / flow | 三家公司均走证据不足出口，不形成方向性资金流或期权结论。真实动态快照留待后续 Change。 |
| COMPANY_RESEARCH / assembly | 三份公司报告导入、22 份总报告、24 个 coverage 项、Markdown/JSON consumer 绑定及 28 个待反证问题均闭合。 |

这些结果满足 Design 第 5 节的“最低必答问题或明确缺口出口”要求，也满足 Task 8.4 对当前源码快照、canonical package、各维度内容、公司报告导入、待反证问题和 SEC 接缝的独立复核要求。缺口出口是本 Change 设计允许的显式结果，不等同于宣称相应外部数据能力已完成。

## v34/v37 排除与 SEC 接缝边界

- v34 与 canonical 使用相同 run/cutoff，但其 `CouncilRequest` input binding 与目标不一致，因此以 `INPUT_BINDING_MISMATCH` 明确排除；`incorporated_supplements` 为空。v34 只支持宏观/SPY 差异化分析能力验收，不进入该 canonical 用户包。
- v37 的 run、cutoff、input binding 均与 canonical 不同，且其一条 ownership evidence 不在 canonical Gate 中，因此以 `RUN_ID_MISMATCH`、`DECISION_CUTOFF_MISMATCH`、`INPUT_BINDING_MISMATCH`、`EVIDENCE_NOT_IN_CANONICAL_GATE` 明确排除。没有把 v37 与 canonical 跨 run 或跨 cutoff 混用。
- 已直接读取 v37 ownership 产物：ALB/MRVL/WOLF 各有一条最新 Form 4 结构化 evidence，均含 `source_id`、`as_of`、`retrieved_at` 及交易代码、数量、价格、直接/间接所有权等元数据。v37 语义报告仅覆盖 ALB 且为 `SOURCE_LIMITED`，明确说明交易代码 A、价格 0 和 footnote ID 不能证明公开市场买入、动机或趋势，缺口为历史序列及 footnote 上下文。
- 已读取 SEC 接缝验证记录并核对其底层证据：3/3 标的、13 个 fetched request、预算 30、每家公司一条最新 Form 4、provenance 完整；v37 Gate 中 5131 条 allowed、745 条 excluded、3 条 ownership allowed、0 条 ownership excluded。该材料只证明 SEC 接缝、PIT/provenance 和有限 ownership 解析能力，不是 canonical 用户研究，不是两期 13F 比较，也不证明完整内部人历史。

## 安全与证据边界

- canonical proof 明示 `llm_calls=0`、`downstream_models_started=[]`、`complete_portfolio_decision=false`。consumer proof 同样没有启动下游模型。
- 对 bundle 及其 22 份报告的结构字段和动作词扫描未发现 `action`、`trade_action`、`target_weight`、订单数量等投资动作字段，也未发现 BUY/SELL/REDUCE/HOLD 或买入、卖出、目标仓位、下单等动作输出。
- 聚焦实现的 runtime 工具保持只读数据/研究边界；结构校验递归禁止投资动作和订单字段。该研究阶段未启动 Skeptic/CIO/Risk 下游模型。Risk Engine 仅允许明确硬约束；学习优化面未修改生产系统或版本指针。工作树中与本 Change 无关的修改不构成本复核结论的一部分。
- 旧证据仅用于当前改动未影响的既有能力验收；canonical package 和新增 SEC 接缝均以上述当前底层产物及当前源码 hash 为准，没有用旧记录替代。
- 公开研报正文、13F 两期机构比较、期权/资金真实快照均延期到 `capture-futu-client-research-data`。本次只确认后续 Change 的任务映射存在，不把未执行任务写成 `RESEARCH_VALIDATED`，也不把后续 Change 的存在当作能力已完成。

## 阻断与剩余审批

Task 8.4 范围内未发现阻断问题，也没有尚未核对的必需项。已知数据缺口均已通过规格允许的 source-limited/insufficient-evidence 出口显式保留，未被伪装成已验证能力。

在本 Change 的既定收尾序列中，只剩 Task 8.5 的明确人工完成批准。本复核结论不是该人工批准，不代表候选晋升、生产批准或任何投资建议通过，也不授权归档、Promotion、交易或生产变更。
