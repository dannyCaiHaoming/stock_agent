## MODIFIED Requirements

### Requirement: 执行模式必须分离且不隐式启动
系统 MUST 将开发自检、宿主产品执行、独立证据复核与全进程隔离验收分开。开发自检 SHALL 在当前 Codex 环境执行确定性检查，不自动启动 Council、模型、网络探针或项目沙箱。产品 Smoke 与 Execution Replay SHALL 复用宿主 launcher 和已有代理适配，保留原生权限，不额外创建项目沙箱。当前启动实现 MUST 删除依据外部沙箱声明或历史 preflight 证明自动关闭原生沙箱的行为；默认宿主模式 SHALL 继续使用 `workspace-write`，不得生成 `--dangerously-bypass-approvals-and-sandbox`、其别名或其他等效自动绕过。

#### Scenario: 自检与旧入口
- **WHEN** 调用自检或旧 `--review` / `review-run` / `review-probe` / `nested-codex-probe`
- **THEN** 自检仅允许声明的确定性检查；旧项目沙箱入口在子进程启动前明确非零拒绝，不静默降级为普通产品运行

#### Scenario: 独立 Reviewer
- **WHEN** 独立复核当前 Change
- **THEN** Reviewer 默认只读差异、规格与既有证据；补跑仅提出缺口，不自行创建沙箱或调用模型

#### Scenario: 绕过薄入口调用历史流程
- **WHEN** 通过薄入口、底层 CLI 或仍保留的直接调用接口请求执行旧 `environment-preflight`、`permission-probe`、`nested-codex-probe` 或项目 review 启动流程
- **THEN** 请求明确失败并提供退役原因，不创建运行状态目录、不启动子进程、网络探测、模型或额外沙箱；更换调用层级不能恢复已退役行为

#### Scenario: 历史沙箱参数不能触发降级
- **WHEN** 当前启动接口收到 `externally_sandboxed=True`、非空 preflight report，或 `--preflight-report` 的分离值/等号值参数
- **THEN** 系统在读取该 report 或运行输入、创建运行状态目录和启动子进程之前明确拒绝；report 是否存在或曾经通过均不能授权关闭沙箱，不能静默改成普通启动

#### Scenario: 正常宿主命令保留原生权限
- **WHEN** 通过现有宿主 launcher 请求普通运行且未指定退役模式
- **THEN** 命令保留 `workspace-write` 与现有审批策略、工作目录、状态目录、Hook、代理传递及完成校验，不包含关闭原生审批和沙箱的参数；该事实不代表全进程源码只读已验证

### Requirement: 开发诊断必须最小化且不自带修复权限
系统 SHALL 复用既有路径/可写性检查及本机 doctor，提供开发专用诊断 Skill。历史 preflight SHALL 仅保留产物读取与审计用途，不再作为当前启动授权或可执行旧沙箱流程。输出 MUST 包含检查项、实际依据、状态、failure_code、首处分歧、下一步最小操作和模型调用数；日常自检模型调用数 MUST 为零，不得以缺少权限探针或尚未准备 run 阻塞普通源码检查。

#### Scenario: 诊断 prepare 后提前退出
- **WHEN** 用户提供完整但未完成的运行包
- **THEN** 诊断读取 invocation、事件、stderr 和终态产物，报告 FIRST_DIVERGENCE、ROOT_CAUSE 或证据不足，不自动重跑、修复或重做全量 Gate

#### Scenario: 私密状态与可共享证据
- **WHEN** 诊断保存或输出检查结果
- **THEN** 仅保存白名单字段与必要 hash，不复制 auth.json、全局会话数据库、用户消息或完整环境变量；发现敏感文件只报告，不自动删除或上传

#### Scenario: 历史 preflight 仅是历史证据
- **WHEN** Reviewer 读取归档运行中的 preflight 报告
- **THEN** 系统保留该证据的原始版本及内容，不改写历史锁，不运行旧探针，也不将历史报告视为当前原生权限或加载证明

## ADDED Requirements

### Requirement: 项目权限残留清理不得改变现用权限边界
根项目配置 SHALL 删除没有现用消费者的 `permissions.project-edit.network.domains` 残留，继续保留当前原生 `workspace-write` 配置、模型选择和开发 Agent 注册。清理 MUST 不迁移新权限框架，不修改 Shadowrocket、用户级配置、宿主代理适配或 network proxy，不以清理为由关闭原生保护或扩大网络授权。

#### Scenario: 清理未使用的命名权限表
- **WHEN** 解析清理后的根项目配置并与修复前配置比较
- **THEN** 不再存在废弃的 project-edit 域名表，现用原生沙箱设置、对应网络设置、模型及 Agent 注册语义不变，也不新增命名权限框架或域名授权
