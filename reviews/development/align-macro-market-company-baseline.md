# align-macro-market-company-research-inputs 实施前基线

- 基线 commit：`2dd25a8b43e5c06b884b70c81016d1c78b485698`
- 记录日期：2026-09-19
- 用途：在切换 2.0 默认契约或退役旧 live 分支前，保存受影响确定性路径的可比较基线；本文件不构成 Runtime Eval、Regression 或 Promotion 证据。

## 聚焦测试

命令：

```text
python3 -m unittest tests.test_multidimensional_research_contracts tests.test_multidimensional_stage tests.test_research_supplement tests.test_moomoo_opend tests.test_live_profile tests.test_live_host_entry tests.test_common_stock_research_contracts
```

结果：共 161 项，160 项通过，1 项失败。失败为实施前既有差异：

- `tests.test_live_profile.LiveProfileTests.test_live_mcp_stdio_starts_without_provider_requests`
- 旧断言期望工具集合为 `query/calculate/research_search/research_fetch`，实际还包含 `equity_research_attachments.query`。

后续验收不得把该既有失败误记为本 Change 引入；同时不得新增失败。若本 Change 触及该工具发现契约，应在对应任务范围内修正断言或实现并说明原因。

## 冻结输入 hash

| 路径 | SHA-256 |
| --- | --- |
| `product/profiles/live-us-equity.json` | `c7ad40d3a9323ecd5c72a53df916f1cf10b853da198d159ef6110fde5bb0d497` |
| `product/mcp/live/research-source-policy.json` | `a73fd6714aeadf974fde3f28264f02601ebd947b033a8c3e502adc4be783322a` |
| `product/mcp/live/research-supplement-source-plan.json` | `6177d30482b369f0a37878d6d86b52665334e33fdf9ec5a9b78ed03228ec2b71` |
| `product/mcp/live/moomoo-opend-quote-manifest.json` | `f05f0600065050ec1ded50c7fb89c1cc5d0b72036bda82b09731be198969870c` |
| `product/schemas/runtime/research-dimension-report.schema.json` | `c1381a41a5f809435ac156ba1950ab0d9947dca8ad0f97093e940e3ca3c41b03` |
| `product/schemas/runtime/holding-research-bundle-v1.1.schema.json` | `9dc67e23a875382f21d15410d70d5b6f7ad0719983e8e9d5e2acedc166952836` |

## 实施后对照（2026-09-20）

同一聚焦命令在实施后共运行 165 项，164 项通过，仍只有实施前记录的同一失败：

- `tests.test_live_profile.LiveProfileTests.test_live_mcp_stdio_starts_without_provider_requests`
- 实际工具集合仍比旧断言多 `equity_research_attachments.query`；该差异不是本 Change 引入。

本 Change 新增或直接影响的 topology、Macro、Market、2.0 stage、材料路由、浏览器和旧入口拒绝测试另行运行，均通过。退役对照集合共 56 项通过（其中 6 项按既有环境条件跳过）；拓扑/三域/浏览器集合共 65 项通过。

实施后冻结输入：

| 路径 | SHA-256 | 结论 |
| --- | --- | --- |
| `product/profiles/live-us-equity.json` | `c7ad40d3a9323ecd5c72a53df916f1cf10b853da198d159ef6110fde5bb0d497` | 与实施前完全相同，历史 profile 未改写 |
| `product/profiles/holding-research-inputs.json` | `ed0d3f0c44787b42fdb57826aeef63f3228f6530d32201daa88e0a6826ebfb36` | 新 CURRENT 三域拓扑引用清单 |
| `product/mcp/live/research-source-policy.json` | `694f520b60b3f82f4af6196e885972dd9b8e778e57fbc4fd5597180e08fff1dd` | 增加官方 Macro 与 Yahoo Market 有界来源政策 |
| `product/schemas/runtime/research-dimension-report.schema.json` | `c1381a41a5f809435ac156ba1950ab0d9947dca8ad0f97093e940e3ca3c41b03` | 1.1 历史 schema 未改写 |
| `product/schemas/runtime/research-dimension-report-v2.schema.json` | `3c1e0b2ef84bcd488c1552e4be6b062f42951bea528258e9f1a1297ffa2f9f0d` | 新 2.0 schema |
| `product/schemas/runtime/holding-research-bundle-v1.1.schema.json` | `9dc67e23a875382f21d15410d70d5b6f7ad0719983e8e9d5e2acedc166952836` | 1.1 历史 schema 未改写 |
| `product/schemas/runtime/holding-research-bundle-v2.schema.json` | `1d982d0d78e41a28b893d57184079c28b9d191d07ceb6b0685624fbf1ffc1fee` | 新 2.0 schema |

全仓 `unittest discover` 仅作补充观察：它进入了仓库既有的环境、历史 fixture、promotion/ablation 慢测试并出现多项非本 Change 失败，随后人工中止，不能记作 PASS 或本 Change 回归证据。本 Change 的完成判断只使用上述事先界定的受影响聚焦集合、真实来源观测及宿主 Smoke。
