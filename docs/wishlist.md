# 愿望清单

博客固定页面 `/wishlist/`，入口在「生活 → 愿望清单」。GitHub Projects 是内容来源，Cloudflare Worker 提供只读接口；修改看板不触发博客部署。页面每分钟检查更新，Worker 缓存 60 秒，正常情况下修改会在约两分钟内显示。GitHub API 出错时页面保留本次浏览期间已加载的数据并提示同步失败；没有可用数据时显示错误和看板链接。

## 看板字段

使用 **用户所有的公开 Projects v2**（当前实现不支持组织看板）。可以使用 draft 卡片，无需创建博客 Issue。推荐按 Status 分组为 Board 视图。排序沿用看板项目顺序；归档卡片、不可读卡片、Pull Request 和来自私有仓库的 Issue 不会显示。私有看板不会返回数据。

| 字段                   | 类型       | 选项 / 说明                                                         |
| ---------------------- | ---------- | ------------------------------------------------------------------- |
| Title                  | 内置       | 愿望标题                                                            |
| Body                   | 卡片正文   | 备注，网页按纯文本展示，不执行 HTML                                 |
| Status / 状态          | 单选       | Todo / To do / 待实现，In Progress / 进行中，Done / 已实现 / 已完成 |
| 类型 / Type / Kind     | 单选       | 想买 / buy、想做 / do、其他                                         |
| 分类 / Category        | 文本或单选 | 数码、旅行、音乐等                                                  |
| 优先级 / Priority      | 单选       | 高、中、低（不自动改变看板排序）                                    |
| 预算 / Budget          | 数字或文本 | 数字默认不指定币种；需要币种时使用文本                              |
| 目标日期 / Target date | 日期       | 可选                                                                |

未识别的类型显示「其他」，未识别的状态显示「待实现」。所有 draft 卡片属于公开看板的公开内容，请不要在此看板维护私密愿望。

## 初次配置

1. 创建一个用户看板「愿望清单」，设为公开。
2. 获取 Project number（看板 URL 最后的数字）。
3. 预览导入文件，再创建字段与 draft 卡片：

```bash
node --import tsx scripts/import-wishlist.ts --file '/path/to/愿望清单.md'
# 写入需要 GitHub CLI 的 project 权限。
gh auth refresh --hostname github.com -s project
node --import tsx scripts/import-wishlist.ts \
  --file '/path/to/愿望清单.md' --owner KazooTTT --project PROJECT_NUMBER --apply
```

导入器只读取 Markdown 任务行，保留原来的完成状态、标签和记录日期。不导入 frontmatter、普通段落或私密笔记链接。只创建缺少的字段和标题；重跑时跳过已有同名卡片，不覆盖后续编辑。中途失败时已经创建的卡片会保留，重新运行前请检查其字段。类型按标题简单推断，可在看板修正。

4. 编辑 `workers/wishlist/wrangler.jsonc`：设置 `PROJECT_NUMBER`；`ALLOWED_ORIGINS` 填写实际博客域名（只写 origin，不带子路径，逗号分隔）。
5. 创建专用只读 GitHub classic PAT，权限为 `read:project`。将凭据存为 Worker Secret，勿放入仓库、前端或 `PUBLIC_` 变量。[GitHub 授权说明](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects)、[Cloudflare Secrets](https://developers.cloudflare.com/workers/configuration/secrets/)。

```bash
pnpm dlx wrangler login
pnpm dlx wrangler deploy --config workers/wishlist/wrangler.jsonc
pnpm dlx wrangler secret put GITHUB_TOKEN --config workers/wishlist/wrangler.jsonc
# 在命令的输入提示中粘贴专用只读 PAT。
```

首次部署后、设置 Secret 前接口返回 503。Worker 只提供 `GET /api/wishlist` 和 OPTIONS，不提供写入或代理任意 GitHub 查询。Origin 白名单控制浏览器跨域读取；它不是私密数据访问控制，接口数据本身公开。每次读取最多 2000 项，超过或分页异常会报错，不返回悄悄截断的清单。

6. 设置仓库 Actions Variables：

- `PUBLIC_WISHLIST_API_URL=https://issues-blog-wishlist.<your-subdomain>.workers.dev/api/wishlist`
- `PUBLIC_WISHLIST_PROJECT_URL=https://github.com/users/KazooTTT/projects/PROJECT_NUMBER`

仅页面代码和首次设置这些 URL 需要部署一次。之后直接在 Projects 新增、编辑、移动卡片，无需改博客代码。移除或归档卡片也会自动反映到网页。

## 页面没有数据时

- 显示「愿望清单正在准备中」：构建时没有配置 `PUBLIC_WISHLIST_API_URL`。在仓库 Settings → Secrets and variables → Actions → Variables 添加上述两个公开 URL，再手动运行 `Build and deploy blog`；只保存 Variable 不会更新已部署页面。
- 显示同步失败：确认 Worker 已部署、`PROJECT_NUMBER` 已填写、Worker Secret `GITHUB_TOKEN` 有 `read:project` 权限，且 `ALLOWED_ORIGINS` 包含博客实际 origin（当前为 `https://blog.kazoottt.top`）。
- 接口正常但清单为空：确认看板属于配置的用户、已公开，且有未归档的 draft 卡片或公开仓库 Issue。博客文章不会自动成为愿望卡片。

## 本地开发

在 `.env` 设置上面的公开 URL 即可。调试 Worker 时在 `workers/wishlist/.dev.vars` 放 `GITHUB_TOKEN`，并加入本地网页的 origin 到 `ALLOWED_ORIGINS`。`.dev.vars` 已被 Git 忽略。

```bash
pnpm dlx wrangler dev --config workers/wishlist/wrangler.jsonc
PUBLIC_WISHLIST_API_URL=http://localhost:8787/api/wishlist pnpm dev
```

生产页面仅允许 HTTPS 接口；开发环境额外允许 localhost HTTP。没有配置接口时显示「愿望清单正在准备中」，不会用测试数据冒充真实愿望。固定页面不进入文章、标签、归档、RSS。

## 验证

`pnpm test` 包含字段转换、私有/归档数据过滤、分页、CORS、缓存、错误脱敏、Markdown 导入和静态页面入口检查。另运行 `pnpm check`、`pnpm build`，以及 Worker 打包检查：

```bash
pnpm dlx wrangler deploy --config workers/wishlist/wrangler.jsonc --dry-run
```
