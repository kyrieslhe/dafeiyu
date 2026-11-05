# v0.1 验证记录

日期：2026-11-05，Asia/Hong_Kong。

## 实际环境与真实模型

- macOS、本机 Python 3.9.6；Codex CLI 0.166.0-alpha.6。
- `codex login status`：Logged in using ChatGPT。应用没有读取或复制认证文件。
- 本机终端真实聊天成功：返回「你好呀，我是大肥鱼，今天想聊点什么，我陪你唠唠。」
- 独立临时数据库里，写入测试记忆「测试用户喜欢简洁中文」，创建 daily 任务，worker 调用真实 Codex 后状态 succeeded，并原子创建一条 outbox。札记明确区分已知偏好与相处愿望，没有编造当日活动。临时测试数据随测试目录清理。
- 以上验证证明当前账号在测试当时可推理，不证明无限额度、未来可用性或费用余额。

## 自动验证

`python3 -m unittest discover -s tests -v`：10 项通过。

覆盖：重启记忆与聊天持久化、删除后上下文清理、到期与 outbox 去重、暂停取消、模型失败不虚构成功、过期租约不重复执行、预算与非法输入、执行中取消丢弃结果、每日计划去重与离线合并、计划暂停与删除。

`python3 -m compileall -q dafeiyu` 通过。CI 另在 Python 3.9、3.12 上运行；不调用真实模型。

## 尚未验证／未实现

- 微信未安装、未扫码、未验证身份及后台投递，不是微信 MVP。
- 无联网研究、隔离编程 Worker、动作审批、自动加密备份、系统推送或常驻服务。
- 首版遗忘不清除历史任务成果；备份中的旧数据也需手动清理。不是对抗恶意输入的多用户服务。
- 未做跨日真实平台测试；每日去重和休眠补跑使用测试时钟验证，不能当成真实微信跨日结果。
- 后台 worker 需保持终端运行；Mac 休眠时不会执行。

官方参考：

- https://developers.openai.com/codex/noninteractive ：官方非交互 CLI、stdin 与最终回复输出流程。
- https://github.com/Tencent/openclaw-weixin ：微信后续接入参考，本次未安装。
