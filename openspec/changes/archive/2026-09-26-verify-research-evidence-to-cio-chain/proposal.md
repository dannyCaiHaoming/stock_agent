## Why

SEC、Yahoo、Moomoo 及其他允许来源已能形成 Company、Macro、Market 资料，但来源配置、Gate 准入和真实研究使用仍是不同事实。最近 MRVL Company 实验出现“完整财年 EPS 已在目录却未查询”、无支撑 Claim；独立研报还有悬空引用，回退完整配置后未完成新的正反研究到 CIO 的整体验证。需要先证明系统拿到、交付、使用并正确引用了哪些资料，再开放建议。

## What Changes

- 对指定普通股和同一 `decision_cutoff`，沿用现有宿主研究入口形成一份可追溯的 Company、Macro、Market 覆盖与消费核对：来源尝试、原事实、Gate 结果、工具实际交付、正反报告引用、CIO 消费分别呈现。
- 定点修复本链路实际遇到的取证遗漏和报告引用错误，包括 Company 的“已可用但未查询”判别、无支撑 Claim 的失败反馈，以及 `RESEARCH_REPORT` 的悬空观察条件引用；保留原 Schema、PIT 和失败终态，不由 Python 补写投资判断。
- 对合格正反研究交接运行一次同截止点的非动作 CIO 综合，复核关键反证是否影响结论；明确数据不足、未采用和系统校验失败的不同结局。
- 验收从既有 MRVL 冻结样本和回退后的完整配置开始；复用未变化的旧证据，新增模型研究必须事先明确预算与样本，不把准备成功或工具调用成功当研究成功。
- 旧样本用于复现与回归；实施授权后另经现有入口做一次有界的当前资料获取检查。按三域应有数据项列出取得、缓存、失败和未尝试，抽查关键事实标准化正确性；为真实链路预先冻结截止点，旧资料不得冒充当前覆盖。
- 消费核对按 invocation 追踪直接引用及经 calculation、附件、研究报告到 CIO 的间接引用；核对产物仅用于开发验收，不进入 Skeptic 独立首轮。检查既有全部核心报告前置条件，保留合法受限覆盖。
- 本次完成交付限定为三域覆盖与正确性表、关键证据消费记录、一条 MRVL 真实正反研究至 CIO 链路，以及聚焦回归与剩余缺口结论；不承诺所有证券或所有来源字段完整。
- 本 Change 不发布买卖建议、仓位、金额、历史回放或收益回测；不新增 Agent、通用评分平台、第二编排器或来源大迁移。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `research-domain-inputs`：增加按本次真实运行区分来源覆盖、Gate 交付与研究实际使用的可读核对。
- `common-stock-holding-analysis`：明确可用事实与 Company 查询、引用的区别及无支撑报告的有界失败反馈。
- `multi-dimensional-holding-research`：修复独立研报观察条件到 Claim 的引用闭包，并保留维度覆盖语义。
- `portfolio-council-orchestration`：规定同源正反研究至 CIO 的端到端核对和真实内容验收。

## Impact

主要涉及现有来源覆盖、Company/多维研究、报告校验、Skeptic 交接、CIO 准备与只读核对产物；使用现有宿主 launcher 和冻结运行目录。原始研究、事件与失败产物继续留在外置运行目录。当前工作区另有 Tiger、Luna Change，实施与提交应按差异隔离。
