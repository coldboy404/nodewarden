# 同步上游后自动更新现有 Cloudflare Worker

本 fork 的 `.github/workflows/deploy-cloudflare.yml` 在 `main` 收到 push（包括在 GitHub 点击 **Sync fork → Update branch**）后构建、测试并更新**已经存在的 Worker**，也支持 Actions 手动运行。它不负责自动同步上游。

## 一次性设置

仓库 **Settings → Secrets and variables → Actions**：

- **Secrets**：`CLOUDFLARE_API_TOKEN`，填入专用 Cloudflare API Token，不是 Global API Key，也不是短期 Wrangler OAuth Token。
- **Variables**：`CLOUDFLARE_ACCOUNT_ID`，现有 Worker 所在账户 ID。
- **Variables**：`CF_WORKER_NAME`，现有 Worker 的完整名称，必须与 Cloudflare 后台一致，不能填域名。
- **Variables（推荐）**：`CF_HEALTH_URL`，现有站点的 `https://vault.example.com/api/config`。用于部署后验证，不填时只验证部署命令和控制面读取，不宣称站点已验证。

Token 限定在该账户，使用 Cloudflare **Edit Cloudflare Workers** 模板，根据现有绑定允许 Workers Scripts/Edit、D1/Edit、Workers KV Storage/Edit、Workers R2 Storage/Edit；自定义域名/路由需要相应 Workers Routes/Edit、Zone/Read 权限并限定相关 zone。脚本需要读取 Worker 设置、路由、自定义域名、workers.dev 和 Cron。权限不足会停止部署，不会创建替代数据库。按实际部署错误进一步收紧权限；不需要将密码库的 JWT_SECRET 存到 GitHub。

在 **Actions → Deploy existing Cloudflare Worker → Run workflow** 手动验证一次，确认 `deploy` job 成功、站点正常后，再进行日常同步。

缺少以上前三项时，验证仍会运行，但部署 job 明确 **skipped**，不表示已发布。

## 已有部署的保护

- 从 Cloudflare 读取现有 Worker 的 D1、R2/KV 和 Durable Object 绑定，使用原资源 ID；不会执行数据库创建、KV 创建或 SQL 重置。没有现有密码库绑定会直接失败。
- 兼容 R2 / KV 两种附件存储，根据线上绑定选择，不凭仓库模板猜测。
- `--keep-vars` 保留 Dashboard 普通变量；Cloudflare Secret（含 `JWT_SECRET`）不覆盖、不轮换。
- 保留现有路由、自定义域名、workers.dev 开关和 Cron；未知绑定类型或无法识别的 Durable Object migration tag 会中止，要求人工审核。
- 新增的上游 Durable Object 类仍按上游 migrations 发布；不代表禁止一切 schema 变化。应用自身可能在请求时升级 D1 schema。
- 串行部署，不取消正在进行的生产更新。部署前会构建、dry-run；构建失败不替换旧代码。

这是原地代码更新，不是删除重建。域名、账号、密码库和附件保持原资源，但不能保证任何上游更新都零影响：数据库迁移、兼容性变更可能影响服务，WebSocket 连接可能短暂重连。**升级前请在应用中启用备份/导出加密密码库**。代码回滚不能撤销数据库迁移，且不可在不审阅发布说明的情况下保证跨版本回滚安全。

## 避免双重部署

如果现有 Worker 已在 Cloudflare **Settings → Builds** 连接本 GitHub 仓库，正常同步上游通常已经会触发 Cloudflare 自动构建，未必需要额外 Actions。采用本 Actions 流程前，应在确认配置成功后关闭旧的自动构建触发，保留一个部署入口，避免两个构建竞相发布。此仓库变更不会替你断开 Cloudflare Git 连接。

如果上游同步由另一条 Actions 工作流使用默认 `GITHUB_TOKEN` 推送完成，GitHub 不会再次触发 push 工作流。那条同步工作流需要显式 dispatch 本工作流，或者使用用户自己配置的合适 GitHub App/PAT。手动 Sync fork 不受此限制。

不要通过 force-sync/reset 抹掉本 fork 的工作流与脚本；正常 merge 同步会保留。上游未来修改这些同名文件时，需要先解决冲突。
