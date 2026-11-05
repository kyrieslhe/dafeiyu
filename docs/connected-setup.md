# v0.2 接入和运行

## 运行时

macOS：`python3 scripts/setup_runtime.py`。安装 Node 26.13.0、OpenClaw 2026.10.10、腾讯插件 2.4.10 到忽略版本控制的 var。Node 下载校验官方 SHASUMS256，npm 依赖由 integrations/runtime/package-lock.json 固定，禁用安装脚本。已有配置与登录不会覆盖。Docker Desktop 需可用，编程使用固定 digest 的 Python 镜像。

`./scripts/openclaw --version`，`./scripts/openclaw plugins inspect dafeiyu-bridge` 检查加载。大肥鱼插件必须 activation.onStartup=true，否则非能力型插件可能只在命令发现时加载，普通消息将落到 OpenClaw 默认模型。

## 微信扫码和绑定

1. `./scripts/openclaw channels login --channel openclaw-weixin`，由本人在微信完成扫码；不要分享二维码或 token。
2. `python3 scripts/services.py start` 启动回环网关和后台 worker。网关绑定 127.0.0.1:18791，使用本机随机 token，不对公网开放。
3. 从机器人会话发送普通文字；绑定前只回复本机确认提示，不提供记忆或工具访问。
4. 在本机 `python3 -m dafeiyu.channel status` 查看候选稳定账号和发送者；核对后执行 `python3 -m dafeiyu.channel bind ACCOUNT SENDER`。候选 10 分钟有效，不能按昵称绑定。
5. 再发普通文字验证。管理命令写成 `大肥鱼 /tasks` 等形式；裸 slash 可能由 OpenClaw 自己处理。`/fish` 仅显示帮助，不执行写操作，因为当前 native command 接口没有稳定消息编号。
6. `python3 -m dafeiyu.channel unbind` 可断开本地绑定；停止新投递，认证凭据仍由腾讯插件管理。

腾讯插件 2.4.10 没有设置通用 SenderId，但源码明确 From、To、OriginatingTo 均来自平台 from_user_id。桥接仅在已确认的私聊事件中使用 host context.conversationId 中的 `@im.wechat` 稳定 ID，保持大小写。缺字段、群聊或身份不符均拒绝。接入不是普通个人微信号，不能读取已有聊天或随意加入群。

## 联网研究

`帮我研究 问题` 或 `大肥鱼 /research 问题`。后台使用 Codex 原生搜索发现最多四个来源，再实际抓取 HTTPS 正文，交给模型综合。也可直接给 HTTPS URL，跳过搜索发现。

抓取器检查每次重定向的 DNS 结果，拒绝内网和保留地址，将 TLS 连接固定到已经检查的 IP，并按原域名验证证书。每来源包含 DNS 在内最多 15 秒、400KB 上限，最多四次重定向，暂仅支持 HTML、纯文本、JSON，不支持 PDF 或登录页面。搜索发现和综合各消耗一次模型调用；抓取本身不消耗模型额度。

成果在 SQLite 和 var/reports/TASK.md，另保存 TASK.sources.json，含实际 URL、抓取时间、内容哈希和截断后的来源正文。抓取成功不保证来源真实可靠；报告仍需根据引文判断。没有成功抓取的来源则失败，不用无来源草稿冒充研究。

## 隔离编程

项目必须放在 var/projects/项目名。目前只支持小型、无外部依赖的 Python 项目，最大 80 个文本文件、300KB、10 个变更文件；不读取隐藏文件，不接受符号链接。

`帮我修改项目 hello 具体功能目标`，或 `大肥鱼 /code hello 目标`。模型只生成候选文本。候选和测试保存到 var/code/TASK；容器仅只读挂载这个快照，不挂载主目录、凭据或 Docker socket。容器无网络、非 root、只读根文件系统、限制 CPU/内存/PID，测试限时 60 秒。失败不在宿主机降级执行。

测试通过后状态 waiting_approval。`大肥鱼 /diff TASK` 查看完整差异与测试；`大肥鱼 /approve TASK SHA256` 确认绑定完整候选的动作摘要，5 分钟有效、仅消费一次。应用前重新检查原项目哈希；项目变更则拒绝。这里只应用文本文件，不执行宿主机测试、不自动 commit、push 或发布。审批消费先于文件写入，崩溃时需检查项目并重新生成，不会自动重复应用。

## 投递与进程

后台 `worker --deliver` 只向已绑定的账号发送结果，最近用户来信必须在本地保守的 90 秒以内；这不是平台必达承诺。超出则 waiting_context，等下一条真实用户来信。发送超时进入 delivery_unknown，不盲目重发；成功仅记 accepted，不代表已读。没有备用通知。23:00–08:00 除明确的一次提醒外不主动投递。

`/inbox` 查看所有未标记查看的成果；`/ack 编号` 标记查看。微信回传限制为短摘要，完整成果用 `/result TASK` 或本地报告读取。`/pause` 同时停止新任务和新投递；`/cancel TASK` 终止在途 Codex 或容器工作，抓取操作最多等待当前网络超时，取消后的结果不发布。

`python3 scripts/services.py status|stop|restart` 管理本项目进程。日志在 var/service-gateway.log、var/service-worker.log，不进入 Git。系统休眠或退出登录不保证运行；当前没有安装自动登录启动项。升级前停止服务并备份整个私人 var 目录。初版数据库采用幂等建表升级，仍需保留恢复用备份。
