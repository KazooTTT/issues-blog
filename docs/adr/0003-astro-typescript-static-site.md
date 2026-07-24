# 使用 Astro 与 TypeScript 构建静态博客

博客使用 Astro 与 TypeScript 构建，并优先采用原生 Astro 组件，不在 MVP 中引入 React 或 Vue。该组合可以在构建时读取远程文章数据、生成稳定的静态路由并部署到 GitHub Pages，同时以较少的客户端 JavaScript 服务阅读场景；代价是团队需要维护 Astro 的内容加载与构建约定。
