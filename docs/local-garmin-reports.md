# 本地佳明早报

数据获取、Magpie 解读、Telegram 投递和状态全部在本机执行，不调用 GitHub，也不创建博客 Issue。代码仍在本仓库维护，线上 Astro 构建不使用它。每日收集的线上调度保持不变。

默认使用 `http://127.0.0.1:3425/v1` 的 `workbuddy-ai/deepseek-v4.1-flash`。Magpie 需要运行，网关会转发给所选模型提供方。也可通过 `MAGPIE_MODEL` 改成网关 `/v1/models` 实际列出的 OpenCode 模型 ID。

配置放在 `~/Library/Application Support/local-garmin-reports/config.json`，目录权限 700、文件权限 600。配置为 JSON 对象，示例：

```json
{
  "GARMIN_IS_CN": "true",
  "GARMIN_TOKEN_STORE": "/absolute/path/to/garminconnect-tokens",
  "MAGPIE_BASE_URL": "http://127.0.0.1:3425/v1",
  "MAGPIE_MODEL": "workbuddy-ai/deepseek-v4.1-flash",
  "TELEGRAM_BOT_TOKEN": "your-bot-token",
  "TELEGRAM_CHAT_ID": "your-explicit-destination"
}
```

`MAGPIE_API_KEY` 可选；未设置时读取已有 OpenCode 配置中与当前网关地址匹配的 Magpie key，不复制或输出它。佳明也支持 `GARMIN_EMAIL` / `GARMIN_PASSWORD`。

```bash
# 私密预览，实际调用佳明和模型；不发送。
uv run --no-project --python 3.12 --with garminconnect==0.3.6 \
  python scripts/local-garmin-report.py \
  --config "$HOME/Library/Application Support/local-garmin-reports/config.json"

# 确认目标配置后投递；不涉及博客。
# 在上述命令末尾加 --send

# 安装或更新登录用户的 launchd 定时任务（安装时不立即发送）
python3 scripts/install-local-garmin-agent.py
```

任务按系统本地时间 09:00、10:00、11:00、12:00 执行，需要系统时区为 Asia/Shanghai。机器关机或未登录时不能保证准时执行；睡眠唤醒后 launchd 可补执行。Magpie 未就绪或手表未同步会失败，后续时段再试。

每个醒来日期保存首份有效原始指标与解读，模型失败保留原始指标供重试；默认不刷新已生成报告。多个进程用文件锁串行执行。每个接收目标单独记录投递状态，成功后跳过。预览、报告和日志位于上述私密目录。

发送前先记录 `sending`，成功后改为 `sent`。网络超时或进程退出会留下 `sending`，后续运行停止自动发送，避免重复。此时先检查 Telegram；确认已收到后，将对应日期 JSON 中该目标状态改为 `sent`；确认未收到时删除该目标的状态以允许补发。不能承诺跨本地磁盘与 Telegram 的严格恰好一次投递。

长报告按段落、句子拆为多条 Telegram 消息，显示序号并保持格式，每条预留长度余量。每条成功回执独立保存；明确拒绝后可从失败分段续发，网络结果不确定时仍停止自动重试。健康数据只留在本地及配置的模型提供方、Telegram，代码仓库中不保存正文。

卸载定时任务：

```bash
launchctl bootout "gui/$(id -u)/com.kazoottt.local-garmin-report"
rm "$HOME/Library/LaunchAgents/com.kazoottt.local-garmin-report.plist"
```

`.github/workflows/daily-reports.yml` 已移除佳明定时触发；此修改需合入并部署到仓库后才影响线上 Actions。迁移期间应避免手动运行旧的 sleep 发布任务。

Telegram 投递将 Markdown 标题、强调、列表、链接、行内代码和代码块转换为 Telegram 支持的 HTML，原始 HTML 会转义。本地预览仍保存 Markdown。需要明确补发已成功的报告时，使用 `--send --resend`；此选项不会绕过投递结果不确定的 `sending` 状态。


早报现结合昨日已记录运动（北京时间，按开始时间归属日期）的类型、时长、距离、平均/最高心率、训练效果与负荷，以及当日 HRV 的昨夜值、7日均值、佳明个人基线范围和佳明状态。仅发送这些摘要，不传送活动坐标、路线或原始时序数据。昨日无记录、接口失败、字段缺失分别说明，不把未知写成零。

HRV 基线读取 `hrvSummary.baseline.balancedLow/balancedUpper`，不会自行估算；佳明状态与单晚相对基线位置分别呈现。字段参考：[Garmin 客户端 HRV 数据结构](https://github.com/cyberjunky/python-garminconnect/blob/master/garminconnect/typed.py)。

模型先输出经过校验的结构化内容，再由程序排版：一句结论、“睡眠与恢复”、“昨日运动”、“今天安排”。每项指标只在所属部分呈现，建议限定2到3条。原始指标仅保存在本地。对既有快照显式使用 `--refresh` 重新读取并解读；已发送报告需要同时加 `--send --resend` 才会补发。刷新不会自动重发；未完成或结果不确定的投递必须先核实处理。

默认只投递精简早报，不附原始指标；通常为一条消息，超长时再按段落分割并使用统一序号。`--rewrite` 使用已保存指标重写解读，不重新拉取佳明数据；重写不自动补发。
