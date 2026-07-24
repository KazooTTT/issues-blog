import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { access } from "node:fs/promises";
import { resolve } from "node:path";

import { beforeAll, describe, expect, it } from "vitest";

const root = resolve(import.meta.dirname, "..");

describe("static blog build", () => {
  beforeAll(() => {
    execFileSync("pnpm", ["exec", "astro", "build"], {
      cwd: root,
      env: {
        ...process.env,
        CONTENT_MODE: "fixture",
        SITE_URL: "https://example.com/blog",
      },
      stdio: "pipe",
    });
  }, 30_000);

  it("generates stable article routes and sends the full-list action to archive", async () => {
    await expect(access(resolve(root, "dist/posts/101/index.html"))).resolves.toBe(
      undefined,
    );
    const home = readFileSync(resolve(root, "dist/index.html"), "utf8");
    const sitemap = readFileSync(
      resolve(root, "dist/sitemap-0.xml"),
      "utf8",
    );
    expect(home).toContain('href="/blog/posts/100/"');
    expect(home).toMatch(
      /<a class="view-all" href="\/blog\/archive\/">查看全部文章 →<\/a>/,
    );
    expect(sitemap).not.toContain("/blog/page/2/");
  });

  it("generates full-text RSS and sitemap output", () => {
    const rss = readFileSync(resolve(root, "dist/rss.xml"), "utf8");
    const sitemap = readFileSync(
      resolve(root, "dist/sitemap-0.xml"),
      "utf8",
    );

    expect(rss).toContain("第 76 次记录");
    expect(rss).toContain("<content:encoded>");
    expect(rss).toContain("&lt;h2&gt;这次记录什么&lt;/h2&gt;");
    expect(sitemap).toContain("https://example.com/blog/posts/101/");
  });
});
