import cloudflare from "@astrojs/cloudflare";
import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

const siteUrl = new URL(process.env.SITE_URL ?? "https://blog.kazoottt.top");
const base = siteUrl.pathname.replace(/\/$/, "");

export default defineConfig({
  site: siteUrl.origin,
  base: base || undefined,
  output: "static",
  // 预渲染放在 Node 里跑，避免构建机上的 workerd 限制，也让构建结果更稳定。
  adapter: cloudflare({ imageService: "compile", prerenderEnvironment: "node" }),
  integrations: [sitemap()],
  markdown: {
    syntaxHighlight: "shiki",
  },
  vite: {
    // 把 base 固化成构建期常量：预渲染在 Node 里跑，SSR 在 Worker 里跑，
    // 两边都不能依赖运行时的 process.env.SITE_URL。
    define: {
      __SITE_BASE__: JSON.stringify(base),
    },
    test: {
      include: ["tests/**/*.test.ts"],
    },
  },
});
