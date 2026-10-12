---
name: skeptic-native
description: 在有效研究窗口中通过Claude原生Skeptic角色执行已授权独立首轮；不接收正向历史或报告。
context: fork
agent: runtime_skeptic
background: false
user-invocable: false
---

本次独立首轮任务如下。它必须独立说明非结论性问题、证券、cutoff、精确task_ref/task_token、当前预算与停止点；不得包含Company/Market/CIO结论、摘要、报告或其他角色授权。缺授权、范围不符或首轮输入污染时停止，不猜测旧任务或继续其他阶段。只按已有Skeptic角色正文和受限业务工具执行，不获取操作方连接凭据，不修改源码/配置，不另派Agent或启动模型。

$ARGUMENTS
