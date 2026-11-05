# 开源与仓库保护

仓库为公开 MIT 项目。用户的聊天、身份绑定、模型授权、微信凭据、数据库、报告、备份和本机配置均留在忽略的 var 目录，不属于公开项目。

main 使用 GitHub 分支保护，配置快照在 `.github/branch-protection.json`：

- 所有修改经 PR，必须通过 test (3.9)、test (3.12)、bridge、isolation、privacy，检查绑定 GitHub Actions app。
- 合并前分支必须更新，管理员同样受限制。
- 仅允许 squash merge，要求线性历史和解决所有讨论，合并后自动删除分支。
- 禁止强推和删除 main。
- 单维护者项目不强制第二人批准；这保留 PR 与 CI 闸门，同时避免作者不能自我批准造成永久锁定。

已启用 GitHub secret scanning、push protection、依赖漏洞提醒、Dependabot 安全更新与私密漏洞报告。普通依赖升级仍需维护者验证，不能把自动升级当成可用性保证。

公开仓库即可使用此分支保护，不依赖确认个人是否订阅 Pro。CLI 返回的账户信息没有可用的 plan 字段，因此没有把 Pro 资格写成已核实事实。

本地 `python3 scripts/privacy_audit.py` 扫描完整可达 Git 历史，不打印命中的秘密正文。启发式检查不覆盖所有隐私类型，也不替代对新素材和集成的人工审查。
