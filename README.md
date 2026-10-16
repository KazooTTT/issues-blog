# KazooTTT 声控烤箱

浅尝辄止，技艺不精。

一个以 GitHub Issues 为内容源、由 Astro 生成并部署到 GitHub Pages 的个人博客。

## 内容规则

- 仓库所有者创建的 Issue 才能成为文章。
- 添加 `blog:publish` 发布；移除后撤回。
- 添加 `blog:featured` 进入首页精选区，最多展示 5 篇。
- 一个带 `blog:about` 的 Issue 提供 About 页面；其评论作为首页和 About 共用的留言区，通过 GitHub 留言，自动重建后显示。
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

## 文章访问统计

热门文章页 `/popular/` 按近 30 天 GA4 浏览量排序，最多展示 20 篇有访问记录的
已发布文章；同分时按首次发布时间倒序，仍同分时按 Issue 编号升序。统计不可用
或暂无访问记录时显示相应提示，可继续浏览归档。

主导航收拢为“文章 / 探索 / 生活 / 关于”：热门、归档、随笔、笔记、总结和标签
位于文章菜单；项目、工具与每日收集位于探索菜单；运动和友链位于生活菜单。
下拉菜单支持点击、键盘操作、Escape 收起与点击外部关闭。
顶部“只看人工”开关会筛选首页精选、文章列表及归档，仅保留明确标记为
“人工写作为主”的文章；未标记或同时标记两种写作来源的文章不进入筛选结果。
选择保存在当前浏览器中，跨页面保留，默认关闭。

文章详情、首页文章列表和精选区展示 GA4 的近 30 天浏览量（PV）与访客数
（`totalUsers`）。统计为 GA4 媒体资源时区内、截至昨天的 30 天，按当前站点域名
及页面路径查询；访客数由 GA4 对整个时间范围去重，不累加每日 UV。

Actions Secret `GA4_SERVICE_ACCOUNT_JSON` 保存服务账号的完整 JSON 凭据，
Repository Variable `GA4_PROPERTY_ID` 保存数字媒体资源 ID。服务账号需要该
GA4 媒体资源的查看者权限，其 Cloud 项目需要启用 Google Analytics Data API。
凭据仅在构建进程使用，不进入公开页面。每天北京时间 10:00 定时重建，文章变更
及手动部署也会刷新统计；GA4 自身的数据处理可能有延迟。

未配置凭据或查询失败时隐藏统计，文章仍可正常构建。有效报表中未出现的路径
显示 0；未配置凭据的本地演示不显示统计。为避免重复访客相加，带尾斜杠路径
优先匹配，无该记录时才匹配不带尾斜杠的路径。

## 站点自有数据

GitHub Issues 负责文章、About、评论和运动复盘。友链保存在
`src/data/friends.ts`；Garmin 运动记录保存在 `src/data/workouts.json`，构建时会执行
Schema 校验。运动详情页可以创建带 `workout:review` 标签的复盘 Issue，Issue
正文中的 `workout-id` 会与 Garmin 的 `externalId` 匹配，并将 Markdown 正文渲染回
对应详情页。Issue 新建或编辑后，现有部署工作流会自动重新构建网站。

同步脚本使用 Python 从 Garmin 拉取最近 14 天的活动，并与现有快照合并：

```bash
GARMIN_EMAIL=you@example.com \
GARMIN_PASSWORD=your-password \
python scripts/fetch-garmin-workouts.py \
  --days 14 \
  --merge \
  --output src/data/workouts.json
```

也可以导入数组或 `{ "workouts": [...] }` 形式的已有 JSON：

```bash
python scripts/fetch-garmin-workouts.py --merge --input /path/to/workouts.json
cat /path/to/workouts.json | python scripts/fetch-garmin-workouts.py --merge --input -
```

同步脚本会校验、按外部 ID 去重、按日期倒序排列，再更新仓库中的静态快照。

佳明活动由 `.github/workflows/sync-workouts.yml` 每天北京时间 00:00
同步最近 14 天的数据。首次启用前，在仓库 Actions Secrets 中添加
`GARMIN_EMAIL` 和 `GARMIN_PASSWORD`。中国区账号无需额外设置；国际区账号
需要添加 Repository Variable `GARMIN_IS_CN=false`。也可以从 Actions 页面
手动运行 `Sync Garmin workouts` 完成首次验证。

同步采用增量快照语义：新活动和最近 14 天内的修改会覆盖同 ID 记录，更早的
历史记录会保留；若一次运行遇到主分支并发更新而推送失败，下次定时运行会重试。

## Telegram 备忘

`.github/workflows/notify-sleep.yml` 和 `.github/workflows/notify-rss.yml`
只把消息发到 [Telegram 频道](https://t.me/kazootttmemos)。它们不会创建 Issue，
也不会添加 `blog:publish`。

### 配置

- Secret `TELEGRAM_MEMOS_BOT_TOKEN`：机器人 token。不要写进代码、工作流或日志。
- Secret 或 Variable `TELEGRAM_MEMOS_CHAT_ID`：频道用户名 `@kazootttmemos`，
  或数字 chat id。两处都填时使用 Secret。
- 睡眠日报复用已有的 `GARMIN_EMAIL`、`GARMIN_PASSWORD`，以及可选 Variable
  `GARMIN_IS_CN`（默认 `true`，中国区）。脚本使用 `garminconnect==0.3.6`。

把机器人加为频道管理员，否则 Telegram 会拒绝发送。

### 睡眠日报

北京时间 07:00–14:00 每小时读一次 Garmin 睡眠。对应 UTC cron 是 `0 23 * * *`
（07:00）和 `0 0-6 * * *`（08:00–14:00）。中国没有夏令时。

一条记录算完整，才会发消息：总睡眠大于 0，并且有起床时间（睡眠结束时间），
而且这个时间已经到了或不晚于当前时间。没有记录、时长为 0、没有起床时间，
或结束时间还在未来，都视为还在睡或手表还没同步。这种情况只在日志里说明原因，
不发消息，workflow 也不会失败。登录或 Telegram 发送失败仍会让任务失败。

发出去之后把日期写入 `data/telegram/sleep-sent.json` 并提交。同一天后续的
整点检查看到这个日期就跳过。14:00 之后当天不再自动尝试；如果那时还没有完整
睡眠，这一天就不会发。只改这个状态文件不会重新部署站点。

在 Actions 页面手动运行 `Notify Garmin sleep` 即可试跑。`date` 留空时用
Asia/Shanghai 的今天。`dry_run` 只打印将要发送的消息，不调用 Telegram，也不
记录已发送。`force` 在数据完整时再发一次，用来覆盖“今天已经发过”；数据不完整
时即使勾选 `force` 也仍然跳过。

```bash
python scripts/notify-garmin-sleep.py --input sleep.json --dry-run
```

### 博客 RSS

每小时第 17 分检查 <https://blog.kazoottt.top/rss.xml>。新文章只发送标题和链接。
已推送的 guid 记在 `data/telegram/rss-seen.json`，由 workflow 提交回当前分支。
只改这个文件的推送不会触发站点部署。

首次启用要先播种，否则定时任务会失败，而不是把历史文章发进频道：

1. 打开 Actions → `Notify blog RSS` → Run workflow。
2. 勾选 `seed`。不要同时勾选 `resend_latest`。
3. 这一步不发消息，只把当前 feed 里的条目标成已推送，并提交状态文件。

之后只有新文章会发送。`dry_run` 只打印将要发送的内容。`resend_latest`
把 feed 里最新一篇再发一次，用来确认机器人能发言；它不修改状态，也不能代替 seed。

状态文件丢失时，定时任务同样失败且不发送。重新勾选 `seed` 即可。再次 seed
会把当时 feed 里的文章全部标成已推送，包括还没发过的新文章。若消息已经发出
但状态提交失败，下次运行可能会再发一次。
