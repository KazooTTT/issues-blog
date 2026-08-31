# AGENTS.md

Issues Blog 的协作入口。领域术语、发布规则以 [CONTEXT.md](CONTEXT.md) 为准；内容规则以 [README.md](README.md) 为准。

## 博客架构速览

- 内容源：**本仓库的 GitHub Issues**（仅仓库所有者创建的 Issue 会成为文章）
- 生成：Astro → GitHub Pages（`.github/workflows/deploy.yml`，Issue/评论变动自动触发重建）
- 发布 = 给 Issue 打 `blog:publish` 标签；移除标签 = 撤回
- `blog:featured` = 首页精选（最多 5 篇）；`blog:about` = About 页面
- 其他非 `blog:*` 标签都是内容标签；导航标签三选一（至少一个）：**随笔 / 笔记 / 总结**

## 从 Obsidian 新建并发布文章（推荐流程）

作者在 Obsidian vault 里写文章，定稿后用 `gh` 发布为 Issue：

```bash
# 1. 在 Obsidian 里写好文章（正文即 Issue body，Markdown 原样使用）

# 2. 发布（title 自取，labels 按需替换；body 直接引用笔记文件）
gh issue create --repo KazooTTT/issues-blog \
  --title "文章标题" \
  --label "blog:publish" \
  --label "笔记" \
  --label "javascript" \
  --body-file "/Users/kazoottt/personal/quartz/content/path/to/note.md"
```

注意事项：

- 标签必须已存在于仓库（`gh label list --repo KazooTTT/issues-blog` 查看）；不存在的内容标签先 `gh label create` 再使用
- **导航标签（随笔/笔记/总结）至少加一个**，具体主题标签不能代替导航标签（见 CONTEXT.md 的 Publishing Rules）
- 想先存草稿：去掉 `blog:publish` 标签创建即可，之后随时在 GitHub 上补标签发布
- 更新文章 = 直接编辑 Issue（网页或 `gh issue edit <number> --body-file ...`），会触发重新部署
- 首次发布时间以**第一次打上 `blog:publish` 的时间**为准；历史迁移文章才用 `<!-- issues-blog:published-at=... -->` 标记

### 更新已发布文章

```bash
gh issue edit <issue-number> --repo KazooTTT/issues-blog \
  --body-file "/Users/kazoottt/personal/quartz/content/path/to/note.md"
```

建议在 Obsidian 笔记 frontmatter 里记录 `blog_issue: <number>`，方便后续更新时定位（约定俗成，博客系统不读取该字段）。

### 与旧发布方式的关系

vault 里的 **KazooTTT Blog Publisher** 插件（`kazoottt-blog-publisher`）对接的是旧版博客 API（kazoottt-blog-v2 / D1），已停用，**不要**用它往 issues-blog 发文章。

## 本地开发

```bash
pnpm install
pnpm dev          # 默认演示内容，无需 token
pnpm test && pnpm check && pnpm build   # 提交前验证
```

读取真实仓库内容：`CONTENT_MODE=github GITHUB_REPOSITORY=KazooTTT/issues-blog GITHUB_TOKEN=<token> pnpm dev`

## 维护约定

- `archive` 分支由工作流维护，仅用于灾难恢复，不要手动编辑
- 部署只有在测试与构建全部成功后才会替换线上版本
