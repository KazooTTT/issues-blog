# 免费文章访问统计 API 调研

调研日期：2026-10-11。仅使用 Google 与 Microsoft 官方资料；没有实际登录项目或调用私有统计数据。

## 结论

推荐使用 **Google Analytics 4 Data API**，在 GitHub Actions 构建时读取每个文章路径的浏览量和访客数，生成到 Astro 页面。免费标准版 GA4 可用，不需要购买 Analytics 360。Clarity 也有免费的 Data Export API，但只导出最近 1–3 天，不能直接查询历史累计或最近 30 天的文章 PV/UV。

Google 的服务条款第 2 节明确 GA4 属性服务免费；Data API 官方配额表包含 Standard 属性，无付费升级前置要求。这里的免费结论限于标准版报表查询，不包含另行使用 BigQuery、Cloud Run 等 Cloud 产品的费用，也不承诺所有 Cloud SDK 开通流程都无需启用结算。[Google Analytics 服务条款](https://marketingplatform.google.com/about/analytics/terms/gb/)、[Data API 配额](https://developers.google.com/analytics/devguides/reporting/data/v1/quotas)

## GA4 的字段与认证

- `pagePath`：主机名与查询串之间的路径，适合按文章永久链接匹配。
- `screenPageViews`：浏览次数，包含重复浏览；用于网站的 PV。
- `totalUsers`：所选范围内记录过事件的去重用户，适合展示“访客数（GA4）”。
- `activeUsers`：活跃用户，含参与度条件，不能与 `totalUsers` 混称。

以上定义见[官方维度和指标表](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)。建议在实现中用 `eventName = page_view` 过滤，使按路径的访客数对应页面浏览事件；还需在真实属性上验证指标兼容性。UV 是 GA4 用户识别口径，不是对真实自然人的精确计数。

Data API 支持 OAuth 用户账户或服务账户；官方 Node.js SDK 为 `@google-analytics/data`。后台自动任务适合服务账户：创建 Cloud 项目、启用 Google Analytics Data API，将服务账户邮箱加入 GA4 属性访问管理并给予只读权限。使用数值型 **Property ID**，不是前端 `G-...` Measurement ID。凭证放入 Actions Secret，由 SDK 获取访问令牌，不能把前端采集 ID 或普通 API key 当作私有属性报表授权。[官方快速开始](https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart)、[访问管理](https://support.google.com/analytics/answer/9305587)

标准属性 Core 配额为每属性每天 200,000 tokens、每小时 40,000 tokens、每项目每属性每小时 14,000 tokens，并发 10；token 消耗取决于行列、日期范围及过滤复杂度。[官方配额](https://developers.google.com/analytics/devguides/reporting/data/v1/quotas)

标准版日内数据通常延迟 2–6 小时，处理可能持续 24–48 小时。因此页面适合显示统计范围和更新时间，不能承诺实时递增。[官方数据新鲜度](https://support.google.com/analytics/answer/11198161?hl=en)

## Clarity 的能力与限制

Clarity 官方说明服务免费，不要求升级付费版。[官方 FAQ](https://learn.microsoft.com/clarity/faq/)

项目管理员可在 Settings → Data Export 创建 API token，调用：

```text
GET https://www.clarity.ms/export-data/api/v1/project-live-insights?numOfDays=1&dimension1=URL
Authorization: Bearer <token>
```

API 支持 `URL` 维度以及 Traffic、Popular Pages 等指标。官方样例有 `totalSessionCount`、`distantUserCount` 等字段，但没有完整稳定的按 URL PV/UV 响应契约。它可以提供近期 URL 维度数据，不能仅凭文档认定所有字段等价于 GA4 的文章 PV/UV；需要真实 token 验证返回结构。

限制为每项目每天 10 请求；只查询滚动的最近 24、48 或 72 小时；每请求最多 3 维度；最多 1,000 行且无法分页。限制与认证步骤均见[官方 Data Export API 文档](https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api)。

自行持续保存快照可以留存未来的近期数据，但重叠滚动窗口的 PV 不能直接相加，跨天去重 UV 也不能通过每日用户数相加得到；漏抓超过 3 天无法从此 API 补齐。这是根据其窗口限制与去重语义做出的工程判断。

## 本仓库接入建议

现有 `.github/workflows/deploy.yml` 已在 GitHub Actions 中构建 Astro，再上传 GitHub Pages，适合新增构建前统计查询和每天一次定时触发：

1. 一次批量按 `pagePath` 拉取所有文章统计；真实数据按 `hostName` 限定本站，避免同一属性其他站点混入。
2. 固定统计范围为“最近 30 天”或“自 GA4 开始采集至昨日”，直接查询整个范围的去重用户数。
3. 仅生成 `{path, views, users, startDate, endDate, fetchedAt}` 公共快照，在详情页展示。
4. 凭证只存在于 Actions Secret 和构建进程，不进入 `dist` 或仓库；如果 API 失败，保留上一次有效快照或暂时隐藏统计，不能显示假 0。

以上为方案建议，尚未改动应用代码或工作流。下一步所需配置是 GA4 Property ID 与拥有该属性只读权限的服务账户凭证。
