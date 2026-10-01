## Context

既有 `product/model-routing.json` 的 `runtime_repeated` 和 `product/version-manifest.json` 锁定 Terra；fixture Council 要求模型与候选版本一致。普通股、多维研究和独立反证的宿主入口目前默认选该路由，独立评分 `dev_eval` 也使用 Terra。需求仅针对产品 Agent 开发测试。

## Goals / Non-Goals

**Goals:** 仓库内明确固定开发期 Agent 测试默认模型为 `gpt-6-luna`，并在无显式覆盖的宿主研究测试中真实传递、校验和记录它。

**Non-Goals:** 不修改候选版本、完整 fixture Council、历史 Replay、`dev_eval`、开发主会话默认模型或生产发布指针；不启动付费模型验证调用。

## Decisions

1. 在现有模型选择模块增加一个仓库固定的开发测试模型常量，受支持的显式研究模型包括该值。宿主入口只在普通股、多维研究、独立反证阶段读取它。既有 `runtime_repeated` 路由及候选版本锁保持原值。选择独立开发默认值，是因为直接替换该路由会和 fixture 候选模型锁冲突。
2. 保留现有 `--model` 显式选择供有意的对照测试；未指定时总是 Luna，任何不可用/不受支持结果均失败，不回退。实际模型在 Invocation/执行事件中验证，配置测试只证明选择而不声称已调用模型。
3. `dev_eval` 继续自己的模型，不与研究 Agent 默认值绑定。更新开发说明和未实施的 CIO Change 验收模型描述，历史已归档文档仍表示当时的测试记录。

## Risks / Trade-offs

- [完整 fixture Council 仍使用 Terra] → 明确其候选锁是另一类运行；需要 Luna 的新候选须另行版本化，不能直接覆盖旧锁。
- [用户以为仓库配置已切换当前 Desktop 会话] → 明确该设置只影响未来宿主研究测试；当前会话由应用自身模型设置决定。
- [Luna 账户或 CLI 支持未通过真实验收] → 确定性选择检查后仍需观察实际运行事件；不可用时报告，不隐式回退。

## Migration Plan

配置和宿主调用更改后执行聚焦确定性测试及 OpenSpec 严格校验。历史运行不改写，后续新研究测试的运行清单记录 Luna；如果运行条件不满足，保留请求与失败证据。
