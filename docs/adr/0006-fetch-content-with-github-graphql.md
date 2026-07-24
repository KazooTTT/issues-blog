# 使用 GitHub GraphQL API 读取博客内容

构建流程以 GitHub GraphQL API 读取 Issue 正文、标签事件、评论、Reaction 与作者信息，并对连接逐级分页、对响应执行运行时校验。GitHub Actions 使用同仓库的短期 `GITHUB_TOKEN`，不配置长期个人访问令牌；我们接受自行维护查询与分页逻辑，以减少 REST 端点拼装并支持首次发布时间等跨对象语义。
