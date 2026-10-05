# 开发环境：仅在配置、路径、权限或启动问题时读取

## 入口和路径

在仓库根用 `python3 -m venv .venv` 创建项目环境，并用 `source .venv/bin/activate` 选择它，然后执行 `python -m pip install -e .` 安装已有基础依赖。新 Terminal 运行确定性检查或宿主脚本前须重新选择该环境；从仓库外可使用 `source <仓库路径>/.venv/bin/activate`。宿主脚本的 `python3` 沿用这个 PATH，MCP 的解释器与依赖目录由宿主绑定，不依赖子 Agent 的偶然 PATH。可选 live/券商依赖仅在对应授权任务需要时安装。

排障时记录实际 Python 路径/版本、依赖状态以及 Codex CLI 路径/版本。桌面内置与终端 CLI 可以不同；不自动升级或改写历史运行锁。当前后续候选要求 `codex-cli/0.160.0`。宿主启动会解析所选二进制并执行零模型 `--version` 核验，在本次 invocation 保存路径、文件 hash、实际版本和锁来源；不匹配会在模型调用前拒绝。纯命令渲染不执行核验，实际各阶段 launcher 使用同一核验包装。完整 fixture 优先消费冻结 run 锁；其他尚无 CLI 运行字段的阶段明确消费所选产品 manifest，不宣称它们已有冻结 CLI 锁。

在桌面内置 CLI 与终端默认版本不同时，可在宿主调用的 PATH 中显式选择已核验的 0.160.0 目录，然后运行既有宿主脚本；不写入机器路径到版本化配置。新的 ephemeral 完整 Council 证明消费宿主测量记录，子 Agent 的 CLI 归属是同一宿主进程运行时，不能从声明推断为观测。原运行及其版本差异记录保持不变。缺少依赖属于环境未就绪，不把未完成的检查报告为产品断言失败或通过。

产品插件在普通开发会话中只提供 Skills 发现，`fixture_runtime` 与 `live_runtime` 默认禁用。研究 MCP 仅由现有宿主 launcher 按具体运行显式启用并绑定产品根、解释器、run 和阶段工具权限；独立 Intake、交易记录和复盘不自动启动研究 MCP。配置/工具清单可读不代表实际加载，须分别记录。

现有底层入口为 `python3 -m product.runtime.cli`（模块调用从仓库根），`nested-codex-smoke` 是宿主脚本消费的统一 LLM launcher，不是开发自检的直接模型入口。真实运行使用下文宿主方式，不复制旧管道命令或创建第二套 Python LLM 编排。旧 preflight 执行入口已退役，历史产物仅供读取。

路径无关转发入口为 `python3 <仓库路径>/scripts/council-dev.py <既有子命令> ...`。它复用底层 CLI 参数；普通命令省略 `--repo` 时从脚本位置定位，其他相对路径按调用时目录解析。`prepare-execution-replay` 仍由原实现物化密封快照，之后 `nested-codex-smoke --run-dir ...` 自动选择该运行 manifest 的冻结 workspace，最后调用原 `finalize-execution-replay`。Regression 仍显式消费 run-index，缺案例不会自动启动模型；已获授权的新案例先经 prepare 和同一 nested-codex-smoke 执行。

开发自检在当前 Codex 环境进行。`council-dev.py self-check check-run --run-dir ...` 或 `self-check trace-check ...` 仅转发确定性检查；其他命令拒绝。确定性单元测试直接按授权范围运行，不调用项目沙箱或完整 Council。

| 名称 | 来源与约束 |
|---|---|
| repo_root | 普通运行显式 `--repo`；Execution Replay 使用准备阶段返回的冻结 workspace，冲突时拒绝 |
| product_root | 对应 repo_root 下的 product；产品子进程和 MCP 必须使用该目录，不依赖操作者当前目录 |
| run_dir | 显式参数，对应唯一 run_id 与 manifest output_dir；新执行不得覆盖已有 invocation |
| state_dir | run_dir 下 `.codex-runtime`，每次运行独立 sqlite/logs/tmp，不共用 |
| research_memory_root | 普通股自动 live 采集的仓库外稳定目录；`--memory-root` 优先于 `RESEARCH_MEMORY_ROOT`，不得使用 run_dir 或源码目录 |

相对参数在入口按原调用 cwd 解析一次，随后传规范路径。活跃源码/模板禁止个人绝对路径；实际环境 manifest 中的绝对路径是审计事实，应保留。内容寻址并密封的 Replay Capsule 物化是合法重放，不等同于临时复制源码绕过加载。

兼容旧式会话证明时，`smoke-prompt` 与 `eval-smoke-prompt` 支持显式 `--sessions-root`；省略时仅解析 `CODEX_HOME/sessions`，未设置 CODEX_HOME 则解析用户主目录下的 `.codex/sessions`。模板生成不扫描或读取会话。统一 launcher 的正常运行仍使用 run-scoped 事件，不转回全局会话查找；需要读取旧会话时仅使用明确授权的目录。

## 权限与保证边界

- 开发只修改授权源码；保留当前 Codex 原生权限，不自动提权或修改系统配置。
- 独立 Reviewer 默认读取代码差异、规格和已有运行包。补跑只报告具体缺口，由用户授权宿主入口执行；不把独立性实现为新建沙箱。
- 全进程源码强制只读为 **UNVERIFIED**。`COMMON_STOCK_RESEARCH` launcher 的窄范围保证是：模型工作区改为运行目录下的一次性隔离源码副本，当前开发工作区做前后 protected-runtime hash；隔离副本写入会被记录并在进程结束后丢弃。Hook/MCP 读取当前运行时模块仍受原生沙箱约束，这不是操作系统级不可变证明，也不推广为其他阶段的全进程只读保证。
- 历史隔离与 preflight 产物保留供审计，不授权当前启动；旧启动函数明确拒绝，不再根据外部沙箱声明关闭原生沙箱。原生权限、Hook、run-scoped 状态、Evidence/PIT/Risk 和 fail-closed 校验不变。
- 不重新排查代理、不修改 Shadowrocket 或域名、不关闭 network_proxy、不开放整个 CODEX_HOME、不复制认证或会话。
- 旧 --review、review-run/review-probe/nested-codex-probe、environment-preflight、permission-probe 和 --preflight-report 在薄入口及底层入口明确非零拒绝，不回退、不读取运行包、不创建产物或调用模型；直接旧启动 API 同样拒绝。
- preflight 不再执行；本机 doctor 仅按既有授权用途使用，不作为日常源码检查、证据读取的必需前置。缺少预备 run 或权限探针不是普通开发的阻断条件。

## 宿主代理与手动 Product Smoke

获得对应场景、模型调用预算与执行授权后，从已选择项目环境的宿主 Terminal 运行 `bash <仓库路径>/scripts/run-product-smoke.sh`。
脚本每次调用 `detect-host-proxy.sh`，保存只读系统查询的原始输出与退出码，
优先使用 `scutil --proxy` 的生效 HTTP/HTTPS 设置；禁用服务中的旧端口和进程名称不作为代理依据。
HTTP/HTTPS 地址分别传递大小写代理环境变量；仅 SOCKS 时使用 `socks5h`，先由现有
`codex doctor` 验证 transport，未知结果或失败即停止，不猜 HTTP 端口。
已连接 VPN/隧道路由且没有显式代理时不新增代理变量；UNKNOWN 停止并保留证据。

默认产物位于新的系统临时目录，代理地址只保存在本地产物中，不写入业务配置或提交 Git。
脚本复用 `prepare → nested-codex-smoke → check-run`，保留已有 Codex 原生沙箱、Hook、
run-scoped 状态及严格完成判定；不启动额外外层沙箱，不修改代理/域名/源码权限配置。
这是一条用户授权的宿主产品启动方式，不是独立只读复核权限证明；不得将它冒充
全进程源码保护证据。TUN 网络下不再要求外层嵌套成功。
脚本聚焦测试与已授权的宿主只读检测不自动授权模型或完整 Gate；实际执行与验收状态记录在对应 Change 证据中。

Execution Replay 的准备与 finalizer 仍复用既有确定性 CLI。准备完新运行后，仅在宿主 Terminal 使用：
`bash <仓库路径>/scripts/run-product-smoke.sh --prepared-run <新重放run目录> <新的外置调用证据目录>`。
该分支不重新 prepare，不强制使用当前工作树；现有转发器按 manifest 选择冻结根。
完成后按既有手册显式执行 finalize-execution-replay；check-run 不替代配置等价性 finalizer。

重放 prepare 必须经当前 council-dev.py，以保存外置 host-replay-source.json；
该来源指针不修改历史锁。宿主 transport 校验来源 manifest/Capsule 和冻结内容后，
给冻结 launcher 调用的 Codex 补 --skip-git-repo-check，实际命令及适配器 hash
存入 run/invocation/host-transport.json。普通运行不使用该参数；缺来源指针拒绝。
既有失败 run 不复用、不补写；使用原 source_run 和新的目录/run_id 重新 prepare。
只有对应重放的真实执行与 finalizer 证据齐全时才能声明该次 Replay 通过；文档中的入口说明不是实际验收证明。

普通股专项运行在启动模型前还会验证实际 Hook 紧凑 JSON 不超过 256 KiB。超限、附件绑定不完整或运行包重建漂移都在创建 Codex 进程前失败。模型运行采用独立本地进程组；超时后有界发送 TERM/KILL 并记录清理结果，远端取消状态无法核实时保持 `UNKNOWN`。这些行为不授予自动模型重试或额外模型预算。

普通股自动采集、增量 checkpoint、报告严格复用、确定性补存及备份恢复见 [Company Research Memory 运行说明](company-research-memory.md)。全复用运行会直接确定性收尾，不启动父模型；`checked_at` 不能解释为报告已由模型重新研究到该时间。

## 模型与消耗

保留 Sol 常规开发、Astra 复杂分析的分工与成本控制；新产品运行（完整 fixture、普通股、多维、独立反证、CIO、重复 Runtime）及新 `dev_eval` 语义评分/Calibration 默认统一为 `gpt-6-luna`。用户明确选择主开发会话模型时尊重其选择，不额外要求产品 `dispute_id` 或批准凭证，也不要求根开发默认模型等于产品 `development_default`。开发子 Agent 继续按职责和已有配置选模；Reviewer 使用其实际生效配置，不承诺跟随主会话自动切换，未观测到实际模型时标未确认。

当前产品路由权威来源为 [model-routing.json](../../product/model-routing.json)，政策版本为 1.1.0。新评分准备由确定性层冻结 `grader_model`，实际模型、可信结果装配、局部修订与完成校验必须一致，错误模型拒绝。旧候选、历史包和密封 Replay 保留原模型与 hash；没有新模型字段的历史 Runtime Eval 沿用原 Terra 读取契约，历史证明仍按其原冻结资源核验，不重标为 Luna，也不因当前配置改变改写历史。显式受支持模型请求如实记录；已批准历史包可显式消费其原模型，不静默回退。产品 `architecture_dispute` 仍需原争议 ID 和人工批准，该条件不反向约束手动开发选模。新默认和配置一致不等于实际模型可用、评分质量或候选晋升通过。

模型由本机支持的配置或显式 `--model` 参数选择，而非 Prompt 自动切换。记录请求模型、配置来源及运行中实际模型；未知时标未确认，不把帮助包含 `--model` 当账户模型可用证明。Desktop 当前会话若无法由仓库配置改变，明确告知用户选择，不声称切换成功。

未变输入复用已验证缓存；真实运行次数按当前 Change 明确预算执行。失败保留事件并先定位，不重复调用 LLM 猜原因。

## 排障顺序与证据

组件版本只读取 `product/version-manifest.json` 的批准值；Agent 的实际内容 hash
从文件取得，Skill frontmatter 和当前 Schema 的版本声明是必须核对的镜像，
不是第二份批准来源。通用 MCP、普通股字段查询和独立 Skeptic 查询分别使用
清单中的 `fixture-gate-scoped`、`common-stock-field-query`、
`independent-skeptic-query` 作用域，不按最大版本号统一替换。阶段准备与工具调用
检查对应作用域；版本相符不等于模型或工具已经加载。

`python3 scripts/check-product-version-mirrors.py --repo <仓库> --check` 只读核对
当前声明；`--render` 只输出从批准清单派生的 fixture profile。
`--render --skill <名称>` 只输出该 Skill 的预期版本镜像，保留方法正文。
两种渲染均不写文件、不调用模型、不批准版本或晋升；显式审阅后才能应用差异。
已退役 `live-us-equity` profile 保留冻结字节供历史读取，不参加当前镜像升级。
内部合成兼容构造必须显式标记 `compatibility_fixture` 且无真实执行证明；
当前 Invocation/launcher 不允许将退役路径用于真实启动。

先读取已有路径/manifest、命令与配置、加载事件和终态。只调用明确授权的确定性检查，不自动执行 doctor、网络探针或模型；需要补证先说明缺口。

区分 `DISCOVERED`（文件/hash）、`CONFIG_VALIDATED`（配置解析）与 `LOAD_VERIFIED`（真实加载事件）。静态检查不得输出加载成功，模型自述“已加载”不能替代执行证明。

指定失败 run 时读取 `invocation/prompt.txt`、invocation/environment manifest、Codex/Hook 事件、stderr、process-result 和终态产物，输出 FIRST_DIVERGENCE、ROOT_CAUSE 或证据不足。Codex 退出码为零不等于 Council 完成：仍须检查 Skill、Specialist、CIO、Risk、终态和场景要求的 decision/report/trace/eval。合法前置终止按原契约标阶段不适用，不伪造执行。

仅诊断任务默认不重跑、不修复、不归档、不推送；已获 apply 授权的普通错误在范围内自行修复并做限定检查，不能把诊断规则当作逐步停点，也不自动启动产品或扩大模型预算。报告仅保留白名单字段、必要路径及 hash，不复制全局配置、Token 或用户消息。遇范围外问题只记录；验收升级需按 [开发流程](workflow.md) 请求批准。
