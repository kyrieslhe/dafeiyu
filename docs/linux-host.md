# 常开 Linux 主机部署

适用于已有、由你管理的 Linux x64/arm64 常开设备；本项目不购买服务器或迁移登录凭据。需要 Python3.12、Git、lsof，以及当前用户可用的 Docker。现有 Mac 继续使用会话守护，不能因为增加 Linux 支持就声称 Mac 关机或合盖也在线。

1. 在目标机克隆仓库；执行 `python3 scripts/setup_runtime.py` 安装官方校验过的固定 Node 与已审计微信运行时。脚本现在区分 macOS/Linux、x64/arm64，归档路径和链接均限制在安装目录。
2. 在目标机按官方流程安装并登录 Codex CLI，再用 `scripts/openclaw channels login --channel openclaw-weixin` 完成微信登录。本机操作扫码，不把 token 或个人浏览器档案复制过去。需要记忆时按加密恢复指南恢复数据库/报告，并检查绑定与任务。
3. 验证 `scripts/openclaw --version`、`python3 -m dafeiyu run '/status'`，按需安装浏览器、语音或短视频运行时。先完成真实微信往返，再安装用户服务。
4. 若已有本项目手动会话监管，先 `python3 scripts/stay_online.py stop`。执行 `python3 scripts/linux_service.py print` 可查看具体单元；`install` 仅安装当前用户的 `dafeiyu.service`，拒绝覆盖其他项目的同名服务。
5. 查看 `python3 scripts/linux_service.py status`、`python3 scripts/services.py status`、`scripts/openclaw channels status` 和 `journalctl --user -u dafeiyu.service`。服务 active 是 systemd 状态，不是登录、消息送达或跨重启验证。

`python3 scripts/linux_service.py uninstall` 移除当前项目用户服务。用户服务使用 supervisor 现有的排他锁与有界修复，不循环登录、不调用模型探测。启动失败会尝试恢复原单元，不修改系统服务、用户 linger 或机器电源设置。用户管理器能否在退出登录或重启后运行，需目标机管理员按实际系统设置验证；没有把启用 linger 写成已完成。

## 可验证的健康采样

监管器会原子写入私人 `var/runtime-health.json`：进程、HTTP、渠道状态、采样时间、主机运行间隙及修复决策。`/health` 输出白名单字段，超过120秒的采样会标为过期，不充作当前在线证明。文字队列状态也能查看，但不输出聊天内容或身份。

当前验证：Mac 上的 POSIX 包装器实际启动版本命令成功；平台/架构选择、systemd 字段转义与健康过期行为通过本机检查。新增 Linux CI 会真正安装运行时并执行兼容测试、验证单元语法。尚未在用户的常开 Linux 主机上登录、安装服务或验证重启恢复。
