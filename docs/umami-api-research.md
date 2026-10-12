# Umami Cloud API 接入调研

核实日期：2026-10-11。来源均为 Umami 官方文档和官网；本次未登录账户、创建密钥或更改订阅。

## 获取 API key

1. 登录 [Umami Cloud](https://cloud.umami.is/)。
2. 点击侧栏的个人资料按钮，进入 **Settings**。
3. 打开 **API keys**，点击 **Create key**。
4. 保存完整密钥。官方 API key 文档说可通过显示图标查看；较新的官方 MCP 发布文章说完整密钥仅在创建时显示一次，因此建议创建后立即保存。

来源：[API Key](https://docs.umami.is/docs/cloud/api-key)、[Introducing Umami MCP](https://umami.is/blog/introducing-umami-mcp)。

## 套餐要求

- **Hobby：免费，不包含 API access。**
- **Pro：$20/月，包含 API access。** Business 和 Enterprise 继承这一能力。
- 官方 MCP 发布文章同时明确 Cloud API keys 在 Pro 套餐中提供。
- Pro 数据保留期为 2 年；不能将超过保留期的数据查询结果称为完整历史累计。

来源：[Pricing](https://umami.is/pricing)、[Introducing Umami MCP](https://umami.is/blog/introducing-umami-mcp)。以上是当前公开套餐，未核实作者账户的实际订阅或历史套餐权益。

## 认证和 SDK

Cloud API 基址是 `https://api.umami.is/v1`，当前文档要求 `Authorization: Bearer <api-key>`。每个 key 的限流为 **每 15 秒 50 次调用**。默认使用密钥所属账户的区域，也可使用 `/v1/us` 或 `/v1/eu`。

来源：[API Key](https://docs.umami.is/docs/cloud/api-key)。

官方 TypeScript/JavaScript SDK 为 `@umami/api-client`，Cloud 模式配置 `UMAMI_API_KEY` 和 `UMAMI_API_CLIENT_ENDPOINT=https://api.umami.is/v1`；文档要求 Node.js 18.18 或更新版本。

来源：[API client](https://docs.umami.is/docs/api/api-client)。

## 按文章路径查询 PV / UV

使用 `GET https://api.umami.is/v1/websites/{websiteId}/stats`，带时间范围 `startAt` / `endAt`（Unix 毫秒时间戳）和 `path`（页面 pathname）。当前返回 `pageviews` 和 `visitors` 两个数值，可分别用于展示 PV 和 Umami 独立访客数。亦支持 ISO 日期 `startDate` / `endDate`。

来源：[Get website summary statistics](https://docs.umami.is/docs/api-reference/get-website-stats)。

批量获取各页面 PV 可查询 `/websites/{websiteId}/metrics?type=path`；当前文档明确页面维度的计数是 pageviews/events，不能把该结果直接解释为每页 UV。单页同时显示 PV/UV 时，优先使用带 `path` 的 stats 接口。

来源：[Get ranked website metrics](https://docs.umami.is/docs/api-reference/get-website-metrics)。

Umami 的 Visitors 是按匿名 session 标识去重，标识包含按月轮换的 salt；它不是永久识别真实人数的指标。建议页面注明统计时间范围，直接查询整个时间范围的 UV，避免把每天的 UV 简单累加。

来源：[Metric definitions](https://docs.umami.is/docs/metric-definitions)；最后一句为基于去重语义的接入建议。

## 本项目建议

密钥保存到 GitHub Actions Secret `UMAMI_API_KEY`，只在构建时调用 API；另需 website ID 和统计范围。生成的公开页面只包含统计结果。这是针对 GitHub Pages 静态部署的实施建议，本次仅调研，尚未修改集成代码。
