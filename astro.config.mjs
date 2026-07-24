import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

const siteUrl = new URL(
  process.env.SITE_URL ?? "https://kazoottt.github.io/issues-blog",
);
const base = siteUrl.pathname.replace(/\/$/, "");

export default defineConfig({
  site: siteUrl.origin,
  base: base || undefined,
  output: "static",
  integrations: [sitemap()],
  markdown: {
    syntaxHighlight: "shiki",
  },
  vite: {
    test: {
      include: ["tests/**/*.test.ts"],
    },
  },
});
