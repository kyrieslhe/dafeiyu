# 运行时依赖安全记录

核查日期：2026-11-05。

公开仓库并开启 Dependabot 后发现上游运行时锁文件有 20 条告警，其中 7 条高危。没有将这些告警直接忽略；已固定覆盖版本 npm 12.2.2、zod 4.6.7、minimatch 11.0.4。OpenClaw 保持已验证的 2026.10.10，腾讯插件保持 2.4.10。

实际重新安装并检查后，`npm audit --audit-level=high` 通过，报告 high=0、critical=0。兼容验证包括 minimatch 的工作区/隐藏文件匹配、Zod schema、腾讯插件导入及修补后网关的真实 HTTP 健康检查。所有包仍由 npm 注册表完整性校验；安装脚本保持禁用。

## 尚存的上游中危告警

npm 12.2.2 自带的 bundled dependencies 仍固定旧版 glob 和 minimatch，npm overrides 不会替换它们的归档正文。直接 `npm audit fix --force` 会建议降级到不兼容的旧版 OpenClaw，没有采用该路径。

- [glob AbortSignal cancellation bypass](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4)
- [minimatch globparts amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249)

npm audit 将依赖这些包的模块也标为受影响，因此显示 33 个 moderate dependency findings；这是两条根 advisory 的依赖链计数，不是 33 个独立漏洞。它们位于 bundled npm 工具链，当前安装仅使用固定包规范、禁用脚本；不能因此宣称漏洞不存在或完全不可达。告警保留开启，等待上游修复后再次更新并验证。

CI 增加 runtime job，安装真实固定依赖、检查兼容并以 high 阈值运行审计。中危残留在此公开记录，不修改扫描结果、不伪造版本以消除告警。
