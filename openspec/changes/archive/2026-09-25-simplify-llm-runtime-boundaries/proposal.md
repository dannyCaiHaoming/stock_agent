## Why

当前 `PREDECISION_CIO_SYNTHESIS` 将完整产品说明、Portfolio Council Skill、混合了旧 fixture/Eval 分支的 CIO 协议与冻结研究报告一并放入模型输入。已有 MRVL 真实研究级基线，适合在不改变研究职责和安全门禁的前提下，减少本阶段无关上下文与重复说明；文件变大本身不作为删除依据。

## What Changes

- 为研究级 CIO 构造仅含本阶段适用规则的有效指令输入，保留产品安全边界、研究方法、证据查询、非动作限制和可审计的版本绑定；不把旧 fixture、Eval 或未开放的建议分支交给该阶段执行。
- 对 CIO 重复机械规则保留一处简短、完整的操作说明，删除重复副本并核对现有确定性校验；不能因校验器能拦错就删除模型完成任务所需的指导。现金/债务双侧证据、MD&A 冲突及证券特定 Market 传导等真实验收修复不得因消减而丢失。
- 对 Company、Market、Skeptic 仅做定点只读审计并记录后续建议，本 Change 不修改其派发说明、Agent 行为或运行实现。不得按文件大小拆模块或引入通用提示词框架。
- 指令变更与现有版本清单成套更新和回退，在使用同一源码的受影响运行结束后切换；补充资源发现、旧 fixture 加载、研究停止点及历史 MRVL 来源准备的确定性兼容检查。
- 以同一冻结 MRVL 来源包记录前后提示规模、实际 token 用量及研究内容差异，完成聚焦测试、新宿主真实研究级 Smoke 和独立内容复核；历史运行保持原样。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `portfolio-council-orchestration`：明确研究级 CIO 的阶段适用指令交付、版本与有效内容校验，以及精简后的真实研究质量验收边界。

## Impact

主要影响 `product/runtime/predecision_cio_stage.py`、`product/AGENTS.md`、`product/.codex/agents/runtime_cio.toml`、`product/skills/portfolio-council/SKILL.md` 的本阶段指令装配，以及 `product/version-manifest.json` 的必要资源绑定、对应测试、运行说明和 Change 验收记录。共享指令的调整保留其他阶段原有规则；不改变产品输出 Schema、Evidence Gate、Risk、Research Memory、Agent 拓扑、来源数据、账户/交易能力或其他活跃 Change 的实现。沿用已有运行清单保存有效指令绑定，不新增证明服务。提示及版本锁改变后，旧 MRVL 运行只作历史基线，不冒充新版本验收。
