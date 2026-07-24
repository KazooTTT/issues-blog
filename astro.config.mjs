import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

const site = process.env.SITE_URL ?? "https://kazoottt.github.io/issues-blog";

export default defineConfig({
  site,
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

