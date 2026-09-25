# Macro/Market 输入消减基线

正向冻结样本：`/private/tmp/expand-moomoo-research-capabilities-multidimensional-20260921-v4/run`，stage 为 `MULTI_DIMENSIONAL_HOLDING_RESEARCH`，唯一普通股 MRVL。审计原件为 `audit/provider-coverage.json`，`coverage_hash=115028e8fe55767327d055a1eff42fb481b3429ae745f2c2c584b10a05c02e63`。字节数按 JSON 对象的紧凑 UTF-8 序列化统计；旧 packet 从冻结文件直接读取。字节数不是模型 token 数。

| 任务 | 旧 `provider_coverage` 字节 | 旧完整 packet 字节 | `evidence_catalog` 条目 |
| --- | ---: | ---: | ---: |
| `MACRO_CONTEXT` | 87,138 | 308,891 | 321 |
| `MARKET_STATE` | 126,573 | 184,670 | 73 |

对同一正向冻结文件在内存中应用当前投影、任务视图标记及说明（不改写冻结文件）后，紧凑序列化结果如下。旧 packet 的 `packet_hash` 均与 dispatch index 相符；新包各自重算 hash。原件 hash 核对通过，两任务的 `allowed_evidence_ids`、`evidence_catalog` 完全相同。

| 任务 | 新覆盖视图字节 | 新完整 packet 字节 | 新 packet hash |
| --- | ---: | ---: | --- |
| `MACRO_CONTEXT` | 5,756 | 228,047 | `be08e5ad1041745ebbfb639c45c86455f5d5b748d37d4314aeccce5ae912d318` |
| `MARKET_STATE` | 5,632 | 64,267 | `aedeb8d4b0a0b4b38ecfdeb7dd7cf16d2198b1b28cdc4716b19e626f995fd0ac` |

此比较证明冻结输入上的确定性投影减量；真实模型输入 token 和研究效果仍须由宿主 Smoke 验证。

另从同一已冻结的原始 Gate、preparation 和 Handoff 在当前代码准备了新正向 run：`/private/tmp/simplify-macro-market-final.aztaIV/run`。两份新 packet 通过实际 dispatch-index 的 hash 及完整审计绑定检查；覆盖视图仍分别为 5,756 / 5,632 字节，完整 packet 为 228,409 / 64,749 字节。新 run 的 `topology_hash` 与 9 月 21 日旧 run 不同，故不将这组新旧完整 packet 的差异解释成单一代码改动；上表的同文件内存比对承担隔离变量的减量证明。

本正向样本 Macro 允许的带数据集 Evidence 为 `macro_history`、`economic_calendar`、`dot_plot`，另有未标注数据集的 SEC 公司传导背景。Market 允许的带数据集 Evidence 为 `fedwatch_expectations`、`option_market_statistics`，另有 Yahoo 市场事实和 SEC 公司传导背景（未标注数据集）。现有路由额外要求保留 `market_breadth` 的 `NO_GATE_EVIDENCE` 及 Moomoo `SOURCE_LIMITED / MOOMOO_QUOTE_CALL_FAILED`，即使它没有允许的 Evidence。

本次相关观察的确定性选择：每任务既有 `DATASET_CAPABILITY_ROUTES` 集合 ∪ 其允许 Evidence 中非空的 `dataset`；不在已知路由表且无法证明无关的未知 dataset 保守保留。跨域公司/市场背景按任务允许 Evidence 继续交付；没有数据集明细的来源保留其全局状态与限制，不伪造观察。样本中 Macro 的 Moomoo 15 条数据集观察仅 3 条是路由相关；Market 也仅 3 条路由相关，另有 Yahoo 两个 `plane`、各 6 条现有数据集观察但零条与 Market 允许 Evidence 直接相交。

需验证的边界：同名 Yahoo 位于 `BASE_DISCLOSURE` 与 `RESEARCH_SUPPLEMENT`，不能合并；Moomoo `market_breadth` 有失败但零 Evidence；候选 provider 有明细却没有任务相关项时，仅明细范围标为 `NO_RELEVANT_OBSERVATIONS`，不得将全局状态改为未采集。多标的情况用聚焦夹具验证。

另用独立反证 MRVL 冻结样本 `/private/tmp/activate-independent-skeptic-mrvl-20260924-v9/run` 检查阶段隔离与官方来源边界；该样本 BLS、Treasury、Federal Reserve 有 Evidence，却没有数据集观察。其 packet 不参与正向消减字节数比较。
