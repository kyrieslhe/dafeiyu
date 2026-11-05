# 运行时依赖安全记录

核查日期：2026-11-05。

最初开启 Dependabot 后发现 20 条告警，其中 7 条高危。固定 npm、Zod、minimatch 后消除了高危，但仍剩两条中危：

- [glob AbortSignal cancellation bypass](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4)，修复版本 14.0.2。
- [minimatch globparts amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249)，修复版本 11.0.1。

此前 npm 12.2.2 的归档内自带 glob 13 和 minimatch 10，普通 overrides 无法替换 bundled dependencies。审计因此产生 33 个依赖链 finding，根源是这两条 advisory。最新 npm 12.2.2 与最新 OpenClaw 2026.11.1 当时仍未解决该打包问题，直接降级 OpenClaw 也不合适。

## 实际修复

OpenClaw 保持已经验证的 2026.10.10，腾讯插件保持 2.4.10。使用明确标注的 npm **12.2.2+dafeiyu.1 本地安全重打包**：保留上游 npm JavaScript 源码和许可，移除预打包 node_modules/shrinkwrap，将 glob 升至 14.0.3、minimatch 升至 11.0.4，改由项目完整锁文件安装真实依赖。

这是项目维护的本地构建，不是声称 npm 官方已经发布修复版。归档和来源记录在 `integrations/runtime/vendor`，上游源归档通过 npm 注册表 SHA512 校验，本地归档另记录 SHA256。npm 自身的 Artistic-2.0 许可和修改说明保留在归档中。没有伪造依赖版本、压制审计输出或 dismiss 告警。

```sh
python3 scripts/repack_npm.py --check
npm ci --ignore-scripts --prefix integrations/runtime
node tests/runtime/compat.mjs integrations/runtime
npm audit --prefix integrations/runtime --audit-level=low
```

干净真实安装后，审计报告 **info=0、low=0、moderate=0、high=0、critical=0**。实际解析到的 glob/minimatch 均为修复版本；本地 npm CLI 可打包并离线安装测试包，生命周期脚本保持禁用；OpenClaw 版本命令、腾讯插件导入和既有路径/schema 检查通过。

CI 现在以 low 阈值审计，新的中危也会阻止合并，并检查重打包归档可复现。这里的零告警指本项目锁定依赖图在检查时的结果，不是整台电脑或所有未来漏洞的保证。已安装服务仍须按安装器更新并验证渠道健康；GitHub 告警由默认分支依赖图更新后自动关闭。

## 维护

更新官方 npm 或本地依赖时重新运行检查，不直接 `audit fix --force`。上游真正修复并完成兼容验证后，可以撤销本地重打包。安装器复制并验证 vendor 归档，不复制 OAuth/微信凭据，既有 var/gateway 保持在原位置。
