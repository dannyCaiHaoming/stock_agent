# 开发环境：仅在配置、路径、权限或启动问题时读取

## 入口和路径

Claude Code正常使用当前仓库的 `product/` 原生产品项目，显式薄发现/连接准备见 [产品使用说明](../../product/hosts/INSTALL.md)，不要求外置源码副本。根目录用于开发；私有任务、连接和产物外置。共享 [portfolio-council](../../product/skills/portfolio-council/SKILL.md)、[角色正文](../../product/agents/README.md)和[薄宿主模板](../../product/hosts/README.md)保持单一来源；Codex/OpenCode遗留未验收。Python只提供授权、资料/计算、提交/读取与持久化，不启动另一模型或改用户设置。实际加载/权限/模型与配置准备分别验证；以下CLI版本、run-scoped Hook和旧锁仅用于明确历史维护。

在仓库根用 `python3 -m venv .venv` 创建项目环境，并用 `source .venv/bin/activate` 选择它，然后执行 `python -m pip install -e .` 安装已有基础依赖。新 Terminal 运行确定性检查或宿主脚本前须重新选择该环境；从仓库外可使用 `source <仓库路径>/.venv/bin/activate`。宿主脚本的 `python3` 沿用这个 PATH，MCP 的解释器与依赖目录由宿主绑定，不依赖子 Agent 的偶然 PATH。可选 live/券商依赖仅在对应授权任务需要时安装。

排障先记录所用Python路径/版本和依赖状态。只有明确历史维护需要时，才按冻结锁核对所选Codex CLI路径/实际版本与二进制hash；桌面内置与终端CLI可以不同，不自动升级或重签旧锁。测量记录绑定对应invocation，纯命令渲染不代表已测量。当前正常研究不使用这些CLI探针或旧Stage launcher。

历史运行的CLI归属、版本差异和隔离记录保持原样；配置声明不冒充观测，也不推定当前原生宿主通过。缺依赖是环境未就绪，不报告成产品断言通过或失败。

产品插件在普通开发会话中只提供 Skills 发现，研究权限默认不可用。原生研究 MCP 仅在具体产品请求、角色及冻结输入/Gate授权成立后启用；当前主线程通过准备能力发放精确task_ref/task_token，专业角色没有准备凭据，业务调用逐次验证。独立 Intake、交易记录和复盘不自动启动研究 MCP。当前 `.claude/`、用户配置与其他插件不被导出或安装操作覆盖；配置/工具清单可读不代表实际加载。

现有底层入口 `python3 -m product.runtime.cli` 仅用于确定性数据/报告和明确历史维护。`nested-codex-smoke`及普通股/多维/资料/反证/CIO旧launch命令在读取运行、写入或模型调用前拒绝，指向当前原生会话。显式冻结Execution Replay经宿主脚本进入`execute-frozen-replay`，先重验来源与密封快照，再加载冻结版本自己的旧入口；不恢复当前代码的正常launcher。旧preflight执行入口继续退役。

路径无关转发入口为 `python3 <仓库路径>/scripts/council-dev.py <既有确定性子命令> ...`。普通命令省略 `--repo` 时从脚本位置定位，相对路径按调用目录解析。`prepare-execution-replay`仍物化密封快照并保存外置来源绑定；`check-frozen-replay`仅校验，`execute-frozen-replay`仅接受已准备的EXECUTION_REPLAY及其仓库外封闭workspace，并交给冻结旧版本执行。准备及finalizer不修改原运行或锁。Regression显式消费run-index，缺案例不自动启动模型；普通原生研究不继承这些维护授权。

开发自检在当前所选宿主环境进行。`council-dev.py self-check check-run --run-dir ...` 或 `self-check trace-check ...` 仅转发确定性检查；其他命令拒绝。确定性单元测试直接按授权范围运行，不调用项目沙箱或完整 Council。

| 名称 | 来源与约束 |
|---|---|
| repo_root | 普通运行显式 `--repo`；Execution Replay 使用准备阶段返回的冻结 workspace，冲突时拒绝 |
| product_root | 对应 repo_root 下的 product；产品子进程和 MCP 必须使用该目录，不依赖操作者当前目录 |
| run_dir | 显式参数，对应唯一 run_id 与 manifest output_dir；新执行不得覆盖已有 invocation |
| state_dir | run_dir 下 `.codex-runtime`，每次运行独立 sqlite/logs/tmp，不共用 |
| research_memory_root | 普通股自动 live 采集的仓库外稳定目录；`--memory-root` 优先于 `RESEARCH_MEMORY_ROOT`，不得使用 run_dir 或源码目录 |

相对参数在入口按原调用 cwd 解析一次，随后传规范路径。活跃源码/模板禁止个人绝对路径；实际环境 manifest 中的绝对路径是审计事实，应保留。内容寻址并密封的 Replay Capsule 物化是合法重放，不等同于临时复制源码绕过加载。

显式旧会话兼容中的`smoke-prompt`与`eval-smoke-prompt`支持`--sessions-root`；省略时仅解析`CODEX_HOME/sessions`，未设置CODEX_HOME则解析用户主目录下的`.codex/sessions`。模板生成不扫描或读取会话；需要读取旧会话时仅使用明确授权目录。冻结旧launcher的run-scoped事件仅解释其原执行契约，不表示当前正常入口仍可启动。

## 权限与保证边界

- 开发只修改授权源码；保留当前 Codex 原生权限，不自动提权或修改系统配置。
- 独立 Reviewer 默认读取代码差异、规格和已有运行包。补跑只报告具体缺口，由用户授权宿主入口执行；不把独立性实现为新建沙箱。
- 全进程源码强制只读为 **UNVERIFIED**。产品专属工具白名单、输入隔离和源码写入限制必须实际生效；配置存在或事后hash不能代替权限证明。旧普通股launcher的一次性源码副本/进程保护仅解释冻结旧产物，当前正常研究不创建该副本，也不继承其保证。
- 历史隔离与 preflight 产物保留供审计，不授权当前启动；旧启动函数明确拒绝，不再根据外部沙箱声明关闭原生沙箱。原生权限、Hook、run-scoped 状态、Evidence/PIT/Risk 和 fail-closed 校验不变。
- 不重新排查代理、不修改 Shadowrocket 或域名、不关闭 network_proxy、不开放整个 CODEX_HOME、不复制认证或会话。
- 旧 --review、review-run/review-probe/nested-codex-probe、environment-preflight、permission-probe 和 --preflight-report 在薄入口及底层入口明确非零拒绝，不回退、不读取运行包、不创建产物或调用模型；直接旧启动 API 同样拒绝。
- preflight 不再执行；本机 doctor 仅按既有授权用途使用，不作为日常源码检查、证据读取的必需前置。缺少预备 run 或权限探针不是普通开发的阻断条件。

## 宿主代理与显式冻结维护

正常原生Smoke不运行本节脚本、不追加代理探针或启动另一宿主。以下仅适用于另获执行授权、版本/来源锁满足要求的旧Execution Replay；一次维护授权不扩展为新研究权限。

获得对应冻结Replay场景、模型调用预算与执行授权后，从已选择项目环境的宿主Terminal运行 `bash <仓库路径>/scripts/run-product-smoke.sh --prepared-run <新重放run目录> <新的外置调用证据目录>`。旧normal/stage/resume模式全部在代理或模型调用前拒绝。
脚本每次调用 `detect-host-proxy.sh`，保存只读系统查询的原始输出与退出码，
优先使用 `scutil --proxy` 的生效 HTTP/HTTPS 设置；禁用服务中的旧端口和进程名称不作为代理依据。
HTTP/HTTPS 地址分别传递大小写代理环境变量；仅 SOCKS 时使用 `socks5h`，先由现有
`codex doctor` 验证 transport，未知结果或失败即停止，不猜 HTTP 端口。
已连接 VPN/隧道路由且没有显式代理时不新增代理变量；UNKNOWN 停止并保留证据。

默认产物位于新的系统临时目录，代理地址只保存在本地产物中，不写入业务配置或提交 Git。
脚本不重新prepare，仅校验来源和封闭workspace后转发冻结旧版本的nested-codex-smoke及check-run；冻结版本按原契约保留原生沙箱、Hook、run-scoped状态和完成判定。当前源码不保留正常模型执行体，不创建额外项目沙箱、不修改代理/域名/权限。本维护入口不是独立只读复核权限或全进程源码保护证明；它也不恢复已退役的日常研究串联。
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

旧普通股运行包仍可验证原紧凑上下文、附件、重建绑定及进程结果；256 KiB、进程组TERM/KILL与远端取消UNKNOWN是冻结旧执行契约，不是当前正常研究的进程实现。当前业务校验和显式维护均不授予自动模型重试或额外预算。

普通股自动采集、增量 checkpoint、报告严格复用、确定性补存及备份恢复见 [Company Research Memory 运行说明](company-research-memory.md)。全复用运行会直接确定性收尾，不启动父模型；`checked_at` 不能解释为报告已由模型重新研究到该时间。

## 模型与消耗

保留用户手动选择开发主会话及既有开发分工，不额外切换模型。正常原生研究使用所选宿主实际生效的用户选择或合法默认，公共方法和业务工具不强制gpt型号；actual model未知保持UNVERIFIED，配置值不替代执行观察。另获授权的旧冻结执行维护与独立dev_eval语义评分/Calibration仍按原`gpt-6-luna`默认及各自冻结锁；历史Terra等不改写，评分不跟随原生研究模型自动切换。Reviewer使用实际生效配置，未知时不承诺跟随主会话。

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
