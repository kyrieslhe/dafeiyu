# 🐳 大肥鱼

一个有稳定口吻、可纠正记忆和共同日记的私人 AI 伙伴。受 DeepSeek 蓝鲸社区二创启发，不是 DeepSeek 官方产品。这里不包含社区角色图片或他人的人设卡。

**v0.1 是本地终端版。默认通过官方 Codex CLI 和现有 ChatGPT 登录推理，无需 API Key。微信尚未接入，不能称为微信 MVP。**

## 开始相处

需要 Python 3.9+（含系统时区数据）和已登录的 Codex CLI：

```sh
codex login status
python3 -m dafeiyu setup
python3 -m dafeiyu
```

Mac 用户可以双击 `启动大肥鱼.command`。若系统限制双击，可在终端执行该文件。提示找不到 Codex 时，将 `DAFEIYU_CODEX_BIN` 设置为 CLI 的完整路径。

试试：

```text
/remember 我喜欢简洁中文
你好，大肥鱼。以后我们一起慢慢把日子过起来。
/diary 今天我们第一次见面，决定先把你的记忆做好。
/memories
/daily
/tasks
/inbox
```

`/daily` 和 `/draft 主题` 是后台任务，需要另外一个终端运行：

```sh
python3 -m dafeiyu worker
```

默认数据目录为当前目录的 `var/`。聊天和 worker 必须从同一项目目录启动；也可两边都使用 `python3 -m dafeiyu --home /绝对路径/私人目录 ...`。

`/routine 21:00 回顾我们的相处，写一小段札记` 明确授权每天香港时间 21:00 生成一次札记，会消耗模型额度。最多一个计划；错过多天只生成当天一次。`/routines` 查看，`/unroutine 编号` 删除。默认没有自动启用任何计划。Mac 休眠、终端退出时不执行；worker 重启后恢复。

`/remind 2026-12-01T09:00 记得喝水` 创建一次本地提醒。没有系统通知或微信推送；通过 `/inbox` 查看，`/ack 编号` 标记查看。输入 `/help` 获取所有命令。

## 记忆和人格

人格在 `dafeiyu/persona.txt`，可随项目演进。显式 `/remember` 才写入长期记忆，模型不会自动把玩笑或推断升级成事实。取最近十条记忆、三条用户日记和十六条聊天构建上下文；首版尚无语义检索。

`/forget 编号` 删除记忆时会清空聊天和共同日记，避免旧上下文再次带入该事实，这是首版有意采用的保守行为；任务成果和历史备份需另行删除。`/clear` 仅清空聊天。聊天保留 30 天，每次启动清理过期内容。

## 模型与权限

默认 `DAFEIYU_PROVIDER=codex`。每次调用使用 `codex exec --ignore-user-config --ephemeral`，在临时工作目录以 read-only 沙箱运行，关闭 shell/exec 功能，不加载用户配置中的 MCP 插件。应用不读取、不复制 OAuth 凭据；认证由官方 CLI 自己处理。可通过 `DAFEIYU_MODEL` 显式指定账号可访问的模型；默认使用 CLI 默认模型，不宣称额度无限。

这是受信任本机单用户原型，不是安全隔离的任意代码 Agent。read-only 不代表文件系统完全不可读；首版不接受网页、附件或其他用户输入，也不开放代码执行、支付、发布或任意系统操作。未建立容器隔离前，不扩展这些权限。

调用超时 90 秒会结束整个子进程组；模型失败不自动重试，不切换付费 API。任务取消后在途文本调用可能继续到超时，但结果不会写入待汇报箱。没有账单余额查询，不能显示真实剩余额度。

可选 API 兼容模式需自行显式设置 `DAFEIYU_PROVIDER=api`、`DAFEIYU_ENDPOINT`（以 API base URL 为值）、`DAFEIYU_MODEL` 和 `DAFEIYU_API_KEY`。单独计费；默认关闭，不要把密钥写进 Git。

## 开发与恢复

零第三方 Python 依赖，无需 pip。执行 `make test` 和 `make build`；GitHub Actions 在 Python 3.9、3.12 上测试，不使用私人凭据或真实模型额度。

SQLite WAL 保存记忆、日记、任务与 outbox。成果正文和 outbox 在同一事务提交。启动时未过期的 running 任务会等待 120 秒租约；过期后标为 failed，避免自动重复调用。可通过 `/tasks` 查看错误并重新创建。每 24 小时最多创建十个后台任务。

备份：先停止聊天与 worker，再复制整个 `var/` 至私人加密存储。恢复：停止所有进程，将该目录恢复到 `--home` 指定位置后运行 doctor。备份含私人记忆，请不要上传 GitHub。删除内容后旧备份仍有旧数据，应自行删除。首版不提供自动加密备份。

详见 [验证记录](docs/verification.md) 和 [后续计划](docs/roadmap.md)。原始 `proposal.md` 是更完整的目标规格，不代表现有交付范围。
