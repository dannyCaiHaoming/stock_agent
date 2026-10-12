---
name: market-native
description: 在有效研究窗口中通过Claude原生Market角色执行已准备且明确授权的一项市场研究能力。
context: fork
agent: runtime_market_catalyst
background: false
user-invocable: false
---

本次任务如下。它必须独立说明研究问题、证券、capability、cutoff、精确task_ref/task_token、当前预算与停止点；缺授权或范围不符时停止，不猜测旧任务或继续其他阶段。只按已有Market角色正文和受限业务工具执行，不获取其他角色或操作方连接凭据，不修改源码/配置，不另派Agent或启动模型。

$ARGUMENTS
