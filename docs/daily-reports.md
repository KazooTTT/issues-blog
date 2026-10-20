# 每日收集自动发布与旧佳明流程

佳明早报现使用[本地 Magpie 流程](local-garmin-reports.md)，线上佳明定时触发已移除。以下佳明 Issue 投递说明仅用于旧脚本兼容；每日收集流程继续有效。

代码在 `scripts/publish-daily-reports.py`，调度在 `.github/workflows/daily-reports.yml`。
默认生成预览；只有显式传入 `--publish` 才创建 Issue 和发送 Telegram。

## 数据和时间

- 佳明早报：北京时间 09:00 请求当天的睡眠数据，10:00、11:00、12:00 再运行以等待手表同步。入眠时间与起床时间使用 `sleepStartTimestampGMT` / `sleepEndTimestampGMT` 转换，起床时间指设备检测到的睡眠结束，并非手动确认的离床时间。无有效睡眠或返回日期不匹配时失败，不发布空报告。
- 早报包含睡眠时长、评分、深睡、浅睡、REM、清醒时间，以及设备提供的静息心率、夜间 HRV、身体电量变化；缺失字段显示“未提供”。
- 每日收集：北京时间 00:00 读取 daily-reports 的正式 D1 数据库，按 `saved_date` 汇总前一天，01:00–03:00 重试。使用与 daily 页面相同的标题/摘要回退规则和分类：增强完成才展示增强内容，否则使用原始内容；pending 进入待分类。
- 无收藏时发布“这一天没有新增收藏”；D1 请求失败则失败，不能误报无收藏。
- 每个日期保留首次发布的快照，后续重试不会覆盖正文或人工修改；午夜之后才到达 D1 的前日收藏不会补进已发布快照。
- GitHub Actions 在整点可能排队延迟，不能承诺精确到 00:00 或 09:00。要求严格准点时需改用专用调度器。

数据库 ID 默认来自本地 `daily-reports/wrangler.jsonc`：`4da564b6-3fc1-4d42-89a1-f96af4ad9f58`。
本地 `daily-reports/data/daily.sqlite` 只用于预览，不作为生产数据源。

## 一次性配置

在 **KazooTTT/issues-blog** 配置 Actions Secrets（不能直接读取另一个仓库的 Secrets）：

| Secret | 用途 |
| --- | --- |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | 已有的佳明凭据，继续复用 |
| `REPORT_GITHUB_TOKEN` | 仓库所有者的 fine-grained PAT，仅授权本仓库 Issues 读写；创建标签也使用此权限 |
| `TELEGRAM_BOT_TOKEN` | Telegram BotFather 创建的 Bot Token |
| `TELEGRAM_CHAT_ID` | 接收人的 chat ID，或群组/频道 ID |
| `CLOUDFLARE_ACCOUNT_ID` | daily-reports 所在账号，已有配置在 daily-reports 仓库，需要另行配置到本仓库 |
| `CLOUDFLARE_API_TOKEN` | 允许查询 daily D1 的令牌，尽量仅授予所需账号的 D1 读取权限 |

不能使用默认 `GITHUB_TOKEN` 创建文章，因为博客只认仓库所有者创建的 Issue。
脚本会在任何发布写入前核对 PAT 对应的用户名。
Token 值不要写入 Git、工作流文件、聊天或命令行参数。

Telegram 私聊需要先给机器人发送 `/start`；群组/频道需要把机器人加入并授予发消息权限。
chat ID 必须是确定的目标，不会自动选取 `getUpdates` 中的任意会话。

Repository Variables：

| Variable | 默认/含义 |
| --- | --- |
| `REPORTS_ENABLED` | 未设置时关闭定时发布；配置齐全后设置 `true` |
| `GARMIN_IS_CN` | `true`，复用现有中国区设置 |
| `REPORT_TELEGRAM_ENABLED` | 默认 `true`；设为 `false` 只创建 Issue |
| `GARMIN_BLOG_ENABLED` | 默认 `true`；设为 `false` 后，新早报 Issue 不加发布标签，仍作为 Telegram 投递记录 |
| `DAILY_D1_DATABASE_ID` | 默认上述 daily 数据库 ID |

Issue 自动添加“总结”“AI 写作为主”标签；发布时添加 `blog:publish`，标签缺失时创建。
早报发布到博客后会公开健康数据。`GARMIN_BLOG_ENABLED=false` 仅阻止新早报进入博客，公开仓库中的草稿 Issue 仍是公开的；需要私密早报时应使用私有投递记录仓库。
已有 Issue 的发布标签不会被重试更改，撤回由作者移除 `blog:publish` 完成。

代码合入默认分支、Secrets 配置完成后，先在 Actions 手动执行工作流，`preview=true` 只验证读取与生成，不发送或发布。预览不上传为公开 artifact，也不把睡眠正文写入 Actions 日志。
再手动以 `preview=false` 执行验证投递，最后设置 `REPORTS_ENABLED=true` 启用定时任务。

## 本地预览

```bash
# 只读已有 SQLite，显式选定收藏日期
python3 scripts/publish-daily-reports.py daily \
  --date 2026-09-24 \
  --database ../daily-reports/data/daily.sqlite \
  --output .local-reports/daily.md

# 从已有佳明会话读取，不需要把账号密码复制到本仓库
GARMIN_IS_CN=true \
GARMIN_TOKEN_STORE=../garmin-grafana/garminconnect-tokens \
uv run --no-project --python 3.12 --with garminconnect==0.3.6 \
  python scripts/publish-daily-reports.py sleep --output .local-reports/sleep.md

# 也可通过 GARMIN_EMAIL / GARMIN_PASSWORD 环境变量登录，或 --input 使用已保存 JSON
python3 -m unittest discover -s tests -p 'test_*.py'
```

`.local-reports/` 已加入 Git 忽略。命令不带 `--output` 时会把预览打印到本地终端。
`--date` 对早报表示醒来的日期，对日报表示收藏日期。
实际发布需配置环境变量，再加 `--publish`；`--no-telegram` 只生成 Issue；
`--draft` 不加 `blog:publish`，仍创建用于投递记录的 Issue。

## 重试与投递状态

- Issue 正文末尾保存 `<!-- automated-report:<kind>:<date> -->`，按日期查找已有 Issue（包括已关闭的 Issue）。
- 工作流串行执行，避免定时任务和手动执行同时创建同日报告。
- Telegram 成功后在 Issue 正文追加按 chat ID 哈希区分的隐藏发送标记，正常重跑不会重复发送。
- Telegram 失败后保留 Issue，下一次运行仅补发；单条消息最长保留约 3800 个 UTF-16 单位，超长报告提供 Issue 全文链接。聊天正文使用纯文本，不启用 Telegram Markdown 解析。
- Telegram 成功与 GitHub 状态保存属于两个系统：若消息已发送但保存标记失败，或者网络超时但 Telegram 实际已接收，重试仍可能重复。Telegram Bot API 不提供本流程可用的幂等键，不能承诺严格恰好一次。
- 不自动重试单次发送请求，以降低网络不确定性导致的重复投递。需要人工补发时，可移除该目标的隐藏发送标记再运行。

接口参考：[D1 Query](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)、[Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage)、[Garmin 时间字段说明](https://github.com/cyberjunky/python-garminconnect/issues/405)、[GitHub 定时任务](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。
