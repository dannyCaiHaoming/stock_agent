## Why

研究交接修复已经形成可复用方法，但散落在源码、实施记录和历史失败中，后续开发容易重复让模型抄录机械字段、扩大补验或混淆发布归属。本需求只将这些方法沉淀为两个开发 Skill，并扩充现有诊断 Skill，减少重复阅读和排障，不增加产品运行框架。

## What Changes

- 新增 `agent-handoff-development`：在设计或修改交接时，指导字段所有权、真实生产者消费者接缝、语义选择与确定性装配、最小依赖调试及有界局部纠正。
- 新增 `change-evidence-closeout`：在判断工作是否完成时，按当前验收依据和实际影响复用证据，识别真正缺口，区分实现、批准、发布及晋升；处理脏工作区共享改动时不猜归属。
- 扩充 `codex-development-diagnostics`：按需读取研究交接诊断参考，区分结构、引用、身份、执行、收集、装配、来源与语义问题；保留原环境诊断及只读边界。
- 两个新Skill采用可跨项目复用的方法核心，在入口内单列简短的“本仓库适配”；不强制依赖OpenSpec、固定目录、金融规则或本仓库批准流程。现有诊断Skill继续作为本仓库专用能力，不扩建通用适配框架。
- 入口简短，中文为主，以“观察→区分→处理”的具体判断补充已有开发指令，不重复堆叠原则或历史失败规则。三个入口按用户目的选择，不串成开发必经流程。
- 沿用当前任务已有授权，不因加载Skill重复询问；仅诊断时不擅自修复，已授权修复时继续范围内工作。诊断仅按需读取授权运行的事件及错误片段，身份或一致性相关时才核对hash。

## Capabilities

### New Capabilities

无新增产品能力或独立平台。

### Modified Capabilities

- `codex-development-environment`：开发 Skill 的按需选择、研究交接方法、证据收尾及研究诊断边界。

## Impact

交付限定为 `.agents/skills/agent-handoff-development/SKILL.md`、`.agents/skills/change-evidence-closeout/SKILL.md`、现有诊断 `SKILL.md` 和其 `references/research-handoff-diagnostics.md`；必要的语法、链接及聚焦检查在 apply 中完成并记录。本轮只生成规划，显式 apply 后实施。

不修改根AGENTS、开发Agent配置、全局Skill目录、`product/`、模型路由、权限、Risk/PIT、历史证据或版本锁；不添加运行脚本、自动执行钩子或新的验收门禁。旧交接修复的批准与待发布状态、其他活跃需求及暂停任务保持不变，本需求不并入已批准Change。

交付是三个Skill、四个文件，不是四个Skill。验收覆盖结构、链接、职责/授权边界，并在已有的一次独立复核内检查具体情境下的处理选择，不另增评测平台或复核轮次。Reviewer先根据请求、Skill及最少原始材料给出判断，再核对验收依据；不把预期答案作为提示。不启动产品LLM或完整Gate，静态检查和情境复核均不宣称已证明生产效果、跨项目普遍适用或token下降。最终人工批准及发布仍按既有流程，不自动执行。
