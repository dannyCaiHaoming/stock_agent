## Why

产品 Agent 开发测试当前沿用 Terra 的默认路由，用户已指定今后固定使用 `gpt-6-luna`。需要让真实研究阶段的开发测试入口默认选择 Luna，同时保留既有候选版本及语义评分的独立模型锁。

## What Changes

- 将普通股、多维研究和独立反证宿主开发测试的默认模型固定为 `gpt-6-luna`；明确指定其他已支持模型时保留显式选择及实际记录。
- 让阶段模型选择器接受 Luna，配置和模型传递保持可验证；不以文档声明代替真实运行证据。
- 更新开发模型说明与正在规划的 CIO Change 的测试模型；既有 fixture 候选锁、历史运行及 `dev_eval` 语义评分模型保持各自版本。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `codex-development-environment`：开发期产品 Agent 测试默认模型从 Terra 调整为 Luna，保持产品候选、评分和开发主会话选模边界。

## Impact

- 影响宿主产品测试入口、产品阶段模型选择器、相关开发文档和聚焦配置测试。
- 不修改 candidate version manifest、产品模型路由文件、`dev_eval` Agent、历史运行包或根 Codex 主会话模型。
