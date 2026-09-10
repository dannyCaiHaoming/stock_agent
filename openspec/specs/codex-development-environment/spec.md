# codex-development-environment Specification

## Purpose

为本仓库开发、测试和独立复核提供可重复且权限明确的 Codex 执行环境，复用现有运行能力，以可验证路径、加载事件和最小诊断结果减少环境故障及不必要的模型消耗，同时保留产品安全边界。

## Requirements

### Requirement: 执行入口必须复用统一启动契约
系统 SHALL 让 Smoke、Execution Replay、Regression 中需要新 Council LLM 执行的路径复用已有统一 launcher、run-scoped 状态目录、Hook 和完成判定，不建立第二套编排框架。确定性验证和已验证证据复用 MUST 保持零 LLM。

#### Scenario: 三类入口启动新运行
- **WHEN** 任一入口需要新的 Council 执行
- **THEN** 系统使用同一启动契约并保存相同格式的 invocation、原始执行事件与完成判定，不通过临时脚本绕过

#### Scenario: 无需模型的操作
- **WHEN** 执行 Artifact Replay、确定性 Regression 案例或有效缓存复核
- **THEN** 系统不启动 Codex LLM，不强迫历史合法包具备新 launcher 字段，也不将旧包伪装为当前加载证明

### Requirement: 宿主代理适配不得猜测或修改网络设置
宿主 Product Smoke 薄入口 SHALL 只读检测生效系统代理，将已启用的 HTTP/HTTPS 或 SOCKS 地址传入现有 launcher；不得使用禁用服务中的旧端口、进程名推测或固定本机端口。仅 SOCKS 时 MUST 先通过现有 Codex transport 检查，失败停止且不得猜测 HTTP 端口。系统查询与判定 SHALL 保存到外置本地证据，不提交代理地址或修改 Shadowrocket、network proxy、域名和产品配置。

#### Scenario: 系统代理与禁用旧值不同
- **WHEN** 生效系统 HTTP/HTTPS 代理与 Wi-Fi 禁用配置中的端口不同
- **THEN** 使用生效设置，并分别导出大小写 HTTP/HTTPS 代理变量，不采用禁用旧值

#### Scenario: 宿主隧道与手动执行
- **WHEN** 存在已连接 VPN 或隧道路由且无显式代理端点
- **THEN** 输出 TUN_OR_VPN 和 LOCAL_PROXY_PORT=NONE，不生成代理变量；用户从宿主 Terminal 经原有 launcher 启动产品，不要求外层嵌套成功，也不将宿主运行冒充全进程只读复核证明；无法确定模式则输出 UNKNOWN 并停止启动

### Requirement: 执行路径必须明确且可移植
系统 MUST 记录 repo_root、product_root、run_dir、state_dir 的解析来源、规范路径和实际子进程 cwd。根目录冲突、manifest 身份不符或路径逃逸 SHALL 在模型调用前失败。产品子进程 MUST 在所选产品根运行，禁止个人绝对路径、偶然 cwd、凭据复制和临时源码复制绕路；内容寻址且校验密封的 Replay 物化不属于禁止的复制。

#### Scenario: 不同调用目录
- **WHEN** 用户从仓库根、product 或仓库外指定同一 repo 和新 run 目录调用
- **THEN** 三种调用解析到同一产品配置，子进程 cwd 均为对应 product_root，带空格路径也不改变参数边界

#### Scenario: 重放根与显式根冲突
- **WHEN** Execution Replay 冻结 workspace 与调用者提供的 repo_root 不一致
- **THEN** 系统拒绝启动并给出冲突来源，不回退到当前工作树或改写历史 hash

#### Scenario: 密封重放目录不包含 Git 元数据
- **WHEN** 宿主启动通过来源 Capsule、manifest 身份、密封内容和 cwd 校验的 Execution Replay
- **THEN** 宿主 transport 适配仅补充 --skip-git-repo-check，保存实际命令和 adapter hash，保留原生权限；冻结 launcher 与历史版本锁不变。缺绑定或校验失败时在模型前拒绝，普通 Smoke 不采用此例外

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

### Requirement: 全进程隔离必须保留未验证状态
系统 MUST 将全进程源码强制只读标为 UNVERIFIED，并明确排除在本 Change 完成保证之外。此范围调整依据人工批准，MUST 保留风险与历史证据，不删除隔离要求、不关闭原生保护、不将功能通过视为隔离或 Promotion PASS。

#### Scenario: 复用宿主 normal
- **WHEN** 复用已成功宿主 normal 及源码前后 hash
- **THEN** 仅复用其功能与运行产物证据；仍报告 launcher/Hook/MCP 全进程禁止源码写入尚未证明，错误调用可能修改允许写入的文件，hash 不能替代预防性保护

### Requirement: 资源发现与实际加载必须分别验证
系统 MUST 区分 AGENTS、Skill、Agent、MCP、Hook 的文件发现/hash、配置解析和实际加载/执行证据。新运行成功 MUST 关联真实事件与所选版本；缺少必要证明不得只凭配置存在或 shell exit code 为零返回成功，合法前置终止按既有终态契约标记阶段不适用而非伪造加载。

#### Scenario: 配置存在但未执行
- **WHEN** 文件和配置可读，但必要 Skill、Agent、MCP 或 Hook 运行证明缺失或与选定 hash 不一致
- **THEN** 新运行完成判定返回非零及具体 failure_code，保留原始事件，不把 preflight 的静态检查称为加载成功

#### Scenario: 完整正常 Smoke
- **WHEN** 新运行通过前置检查并完成正常 Council
- **THEN** 证明关联实际 AGENTS 读取链、Skill、独立 Specialist、CIO、MCP、Hook、Risk、终态和场景要求产物，复用既有严格 Evidence 与完成校验

### Requirement: 版本与模型配置必须以可验证能力为准
系统 SHALL 在使用新的参数和配置键之前记录本机 CLI 版本、帮助或配置解析依据；已验证且未改变的能力依据可以复用，不将重复兼容性检查作为普通开发前置。开发 SHALL 保留 Sol 常规开发、Astra 复杂分析、Terra 产品开发期 LLM 测试分工及既有成本控制；用户明确指定时尊重主会话选择，不要求产品 dispute_id、争议说明或批准凭证，不强制根开发默认模型与产品 development_default 一致。开发子 Agent SHALL 按职责和已有配置选模；Reviewer MUST 使用自身实际生效配置，不承诺自动跟随主会话，实际模型未知时如实标注。系统 MUST 尊重用户选择，不通过 Prompt 声称已切换模型，也不自行修改用户模型配置。

产品执行、重复 Runtime 测试及真实 Runtime Eval 的既有模型路由和版本锁 MUST 独立保留；开发模型自由选择不得改写产品模型、历史配置或路由校验。实际执行的模型 MUST 由受支持配置或显式参数选择，并如实记录请求值与实际值；仅文档/配置检查不得宣称账户模型可用或已运行。

#### Scenario: 参数或模型不可确认
- **WHEN** 所需配置不被当前 CLI 支持，或所选模型无法确认可用
- **THEN** 系统报告不支持或待确认，不静默替换模型，不启动付费试错循环；帮助中存在 model 参数不等于某模型已获账户授权

#### Scenario: Hook 信任受限
- **WHEN** 当前 launcher 依赖 Hook 信任豁免但本机政策不允许或来源未核验
- **THEN** 系统报告所需的精确信任范围并停止，不自动增大信任范围或关闭权限控制

#### Scenario: 用户手动选择开发模型
- **WHEN** 用户为开发会话选择可用模型，包括 Astra、Sol 或其他模型
- **THEN** 开发规则和 Reviewer 不要求额外架构争议证明才能继续授权任务；保留平台实际可用性限制，不修改产品 Runtime/Eval 路由或其版本锁

#### Scenario: 产品仍使用原路由
- **WHEN** 后续按另行有效授权启动产品或真实 Runtime Eval
- **THEN** 仍使用该任务要求的原产品路由和锁；不能根据开发界面模型选择绕过产品显式路由所需条件，不把这些产品条件反向施加到手动开发会话

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

### Requirement: 项目权限残留清理不得改变现用权限边界
根项目配置 SHALL 删除没有现用消费者的 `permissions.project-edit.network.domains` 残留，继续保留当前原生 `workspace-write` 配置、模型选择和开发 Agent 注册。清理 MUST 不迁移新权限框架，不修改 Shadowrocket、用户级配置、宿主代理适配或 network proxy，不以清理为由关闭原生保护或扩大网络授权。

#### Scenario: 清理未使用的命名权限表
- **WHEN** 解析清理后的根项目配置并与修复前配置比较
- **THEN** 不再存在废弃的 project-edit 域名表，现用原生沙箱设置、对应网络设置、模型及 Agent 注册语义不变，也不新增命名权限框架或域名授权
