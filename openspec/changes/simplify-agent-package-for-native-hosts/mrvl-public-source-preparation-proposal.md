# 待批准：MRVL公开资料准备与新截止点

- `source_id`: `mrvl-public-source-preparation-proposal:20261007`
- `as_of`: 2026-10-07T07:14:03.839612+00:00
- `retrieved_at`: 2026-10-07T07:14:03.839612+00:00
- 状态：`APPROVED_CONFIGURATION_STOP_BEFORE_CALLS`。用户随后回复“是”批准本方案；配置缺失时按约定停止，实际调用0。见[最新结果](mrvl-authorized-source-configuration-stop.md)。

## 具体范围

仅处理已选MRVL公开样本的研报、Macro和Market三项资料发现，沿用当前已实现OpenAlex适配器和来源策略，域名限`api.openalex.org`与`content.openalex.org`。每项最多3次检索、5次正文尝试，总上限9次检索＋15次正文尝试；失败计入上限，不自动重试或换提供商，不购买服务、不新增付费或凭据、不读取账户。检索问题和正文选择由获准原生作者完成，确定性层只检索/记录/验证，不替作者选择证据。主线程和准备任务计入原Claude15任务额度，不另加模型预算。

正文适配器要求宿主本地安全环境已有可用OpenAlex API配置；只核对可用性，不显示/复制密钥到报告或Git。配置不存在时在模型/来源调用前停止，不为了探测消耗额度。来源失败、正文不适用或核心依赖未就绪时停止相应链路，不承诺补采一定成功。

如批准新取证，使用新的latest公开研究请求，在资料准备完成后冻结合法的新共同cutoff并保留旧Gate/准备的血缘；不把当前retrieved_at回填到2026-09-28旧时点，不改变原冻结包或旧状态，不宣称历史复现。正式研究仍须逐项验证覆盖/时效、合格依赖与真实读取，缺口不能因新cutoff豁免。

旧安装/配置保持原样；新版候选安装对齐及原生权限确认在执行前按已知精确差异处理，不用来源批准推导覆盖配置或关闭权限。其他两个宿主和最终完成批准保持待定。

相关证据：[本次预检](claude-bounded-acceptance-precheck.md)、[原来源策略](../../../product/mcp/live/research-source-policy.json)、[当前实现差异](no-model-archive-scope-check.json)。
