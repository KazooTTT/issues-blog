# KazooTTT 声控烤箱

浅尝辄止，技艺不精。

一个以 GitHub Issues 为内容源、由 Astro 生成并部署到 GitHub Pages 的个人博客。

## 内容规则

- 仓库所有者创建的 Issue 才能成为文章。
- 添加 `blog:publish` 发布；移除后撤回。
- 添加 `blog:featured` 进入首页精选区，最多展示 5 篇。
- 一个带 `blog:about` 的 Issue 提供 About 页面。
- 其他非 `blog:*` Labels 都作为内容标签。
- Issue 的 Open/Closed 状态不影响发布。
- 历史迁移文章可在正文末尾使用
  `<!-- issues-blog:published-at=2021-03-04T00:00:00.000Z -->`
  保留原发布日期；日常发布仍以首次添加 `blog:publish` 的时间为准。

## 本地开发

```bash
pnpm install
pnpm dev
```

本地默认使用确定性的演示内容，不需要 GitHub Token。读取真实仓库：

```bash
CONTENT_MODE=github \
GITHUB_REPOSITORY=owner/repo \
GITHUB_TOKEN=github-token \
pnpm dev
```

## 验证

```bash
pnpm test
pnpm check
pnpm build
```

## GitHub 设置

1. 创建 `blog:publish`、`blog:featured` 和 `blog:about` Labels。
2. 在 Settings → Pages 中选择 GitHub Actions 作为 Source。
3. 如需自定义域名，在 Actions Variables 中设置 `SITE_URL`。
4. 保持 Actions 的 Pages 写权限；归档工作流还需要 Contents 写权限。

部署只会在完整测试与构建成功后替换线上版本。`archive` 分支由工作流维护，仅用于恢复，不是编辑入口。

## 从旧博客迁移

迁移命令默认只做预检；加入 `--apply` 才会创建 Labels 和 Issues。每篇文章带有
D1 来源标记，因此重复执行会跳过已迁移内容。

```bash
pnpm migrate:d1 \
  --source /Users/kazoottt/personal/kazoottt-blog-v2 \
  --repo owner/repo

pnpm migrate:d1 \
  --source /Users/kazoottt/personal/kazoottt-blog-v2 \
  --repo owner/repo \
  --apply
```

设计与领域决策见 [docs/MVP.md](docs/MVP.md)、[CONTEXT.md](CONTEXT.md) 和 [docs/adr](docs/adr)。

## 站点自有数据

GitHub Issues 只负责文章、About 和评论。友链保存在
`src/data/friends.ts`；运动记录保存在 `src/data/workouts.json`，构建时会执行
Schema 校验。

可将数组或 `{ "workouts": [...] }` 形式的 JSON 交给同步脚本：

```bash
pnpm sync:workouts --input /path/to/workouts.json
cat /path/to/workouts.json | pnpm sync:workouts
```

同步脚本会校验、按外部 ID 去重、按日期倒序排列，再更新仓库中的静态快照。

佳明活动由 `.github/workflows/sync-workouts.yml` 每天北京时间 10:15
同步最近 14 天的数据。首次启用前，在仓库 Actions Secrets 中添加
`GARMIN_EMAIL` 和 `GARMIN_PASSWORD`。中国区账号无需额外设置；国际区账号
需要添加 Repository Variable `GARMIN_IS_CN=false`。也可以从 Actions 页面
手动运行 `Sync Garmin workouts` 完成首次验证。

同步采用增量快照语义：新活动和最近 14 天内的修改会覆盖同 ID 记录，更早的
历史记录会保留；若一次运行遇到主分支并发更新而推送失败，下次定时运行会重试。
