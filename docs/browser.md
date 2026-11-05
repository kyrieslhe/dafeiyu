# 公开网页视觉浏览

```sh
python3 scripts/setup_browser.py
```

需要 Docker Desktop 和 Node 26。安装固定 Playwright core 1.64.1（npm 完整锁文件），以及固定摘要的微软 Playwright 浏览器镜像；不导入个人 Chrome、Safari、Cookie、模型认证或平台登录。运行时包保存在私人 var/browser-runtime，不进入 Git。

微信或本机可发送：

```text
大肥鱼 /browse https://www.python.org 看看首页用途，并沿相关链接找文档入口。
帮我浏览 https://www.python.org，解释页面的主要入口。
```

没有给出地址时，会使用 Codex 原生搜索寻找一个公开 HTTPS 入口。任务最多查看三个页面；每页使用真实 Chromium 渲染、截图和 DOM 文字，模型只可结束回答或选择实际提取出的链接继续导航。报告记录实际访问页面、时间与资源哈希；没有访问的内容不能当成事实。网页和图片中的指令不是权限。

## 浏览隔离

浏览器运行在独立 Docker 容器，网络完全关闭、根文件系统只读、非 root 用户、CPU/内存/PID/文件大小受限，不挂载 Docker socket 或用户目录。Chromium 自身沙箱保持开启，使用上游 seccomp 策略；在 cap-drop ALL 后仅增加 SYS_CHROOT，以便 Chromium 在用户命名空间内完成沙箱初始化，未添加 SYS_ADMIN 或特权模式。

浏览器通过标准输入/输出请求公开资源，宿主 HTTPS broker 逐项验证 DNS、拒绝私网/特殊地址、固定已检查 IP 并验证 TLS。只发无 Cookie/Authorization 的 GET，不转发页面请求中的认证头；浏览器不能直接访问本机或内网。每页最多 20 项、每项 1MB、合计最多 20MB，整个渲染阶段最多45秒；WebSocket、服务工作线程、音视频流和上传被拒绝。容器关闭时清理本次进程，取消不留下继续浏览的容器；已开始的资源抓取最多等待各自10秒时限退出。

这些限制可能使复杂网站部分空白、样式/脚本缺失或任务失败。报告明确标记阻断资源，不把部分渲染当成完整网站。当前只支持公开页面查看和链接导航，**没有账号登录、表单填写、购买、点赞、评论或社交发布**。同一任务的每一步使用全新浏览上下文，不保持登录或表单状态。

## 证据与检查

截图、页面和资源记录在私人 var/browser-runs/任务编号。普通后台报告仍在 var/reports。微信发送仍受有效上下文窗口限制；accepted 不代表已读。

实际本机已完成：Chromium 自身沙箱+非 root+无网络容器启动，渲染 Python 官网，拿到标题/正文/链接/截图；截图目视检查通过。另通过真实 Codex 读取该次实际渲染截图，任务成功并返回有实际页面来源的观察。部分资源受限，未声称验证整站。

默认 CI 不调用模型。可选浏览器集成使用固定离线 HTML 资源，验证真实容器渲染；它不是网站长期可用性或微信送达测试。

上游参考：[Playwright Docker](https://playwright.dev/docs/docker)、[网络路由](https://playwright.dev/docs/network)。上游 seccomp 策略保留 Apache 2.0 授权说明，应用代码仍为 MIT。
