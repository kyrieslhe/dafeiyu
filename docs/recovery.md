# 加密备份、恢复与常驻

## 设置加密备份

```sh
python3 scripts/setup_age.py
python3 -m dafeiyu.backup setup
python3 -m dafeiyu.backup create
```

安装的是固定 age v1.3.2 官方发行包，按 GitHub 发布资产 SHA256 校验；不自行实现密码学。安装脚本支持 macOS/Linux 的 arm64、amd64，二进制留在私人 var/runtime。

setup 在 `var/secrets/recovery.agekey` 创建恢复私钥（0600），以及用于加密的 recipient.txt；不打印私钥正文。**请将恢复私钥单独、安全地保管，并将加密备份另存到独立存储。** 只保留本机副本不能覆盖整机丢失风险。公钥存在而原私钥缺失时，不会偷偷生成新身份覆盖旧公钥。

setup 明确启用后台每天一次的加密快照，按香港日期去重，最多保留最近 14 个加密文件；默认未 setup 时关闭。worker 至多每分钟检查一次。备份失败等待一小时后再试，审计只记录脱敏失败事件，不形成模型循环。

备份包含 SQLite 的一致性快照和报告，附文件 SHA256 清单；不包含 OAuth、微信凭据、恢复私钥、项目源码工作区或整个主目录。临时明文位于私人临时目录，操作完成后移除；不承诺取证级擦除。无需模型调用或网络上传。

## 恢复演练和迁移

```sh
python3 -m dafeiyu.backup --home var restore var/backups/备份文件.tar.gz.age --target var-restored
python3 -m dafeiyu --home var-restored doctor
```

目标必须是全新的目录，防止覆盖现有数据。可用 `--key /私密路径/recovery.agekey` 指定单独保管的恢复密钥。密钥不要粘贴进聊天或公开 issue。

恢复先校验 age 认证、归档路径、大小上限、文件哈希和数据库结构；拒绝路径穿越、符号链接、重复文件和非允许文件。当前数据目录里的删除哈希记录会重新应用到旧快照，避免已忘记的内容再次出现。若是在全新机器上恢复旧备份而没有最新删除记录，则无法知道备份之后发生的删除，应使用最新备份或保留当前数据目录用于合并。

恢复后自主执行默认暂停、在途任务不重放、微信上下文清空，备份开关关闭。请先检查记忆、计划与待汇报记录，再决定启用服务或 `/resume`。独立项目源码、微信和模型登录需按各自官方流程重新准备。恢复文件不会自动替换运行中的 var。

## macOS 登录常驻

```sh
python3 scripts/login_service.py install
python3 scripts/login_service.py status
```

仅安装当前用户的 `io.github.kyrieslhe.dafeiyu` LaunchAgent，不安装系统 daemon。后台监管只检查进程，不调用模型；异常退出会有界重启，连续异常时暂停并留下本机日志。

`python3 scripts/services.py stop` 是明确停止，会写暂停标记，监管器不会擅自把服务启动回来；`start` 明确恢复。`/pause` 只暂停自主任务和投递，仍保留聊天。移除登录项并停止服务：

```sh
python3 scripts/login_service.py uninstall
```

网关仍只监听回环地址。电脑休眠、退出登录或网络断开期间不保证工作；Docker Desktop 也需要可用才能运行隔离编程。日志在私人 var 中。升级时先停止服务，保留恢复快照，再更新并启动。
