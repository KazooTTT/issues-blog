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
    expect(home).toContain("https://t.me/kazootttmemos");
    expect(home).toContain("https://www.youtube.com/@kazoottt255");
    expect(home).toContain("在别处找到我");
    expect(home).toContain("https://github.com/KazooTTT/issues-blog");
    expect(home).toContain(
      "https://www.googletagmanager.com/gtag/js?id=G-F4KLD4XCDB",
    );
    expect(home).toContain("https://www.clarity.ms/tag/");
    expect(home).toContain('"kvbyuhu6d2"');
    expect(home).toContain("https://cloud.umami.is/script.js");
    expect(home).toContain(
      'data-website-id="247d7726-70c1-46fd-9453-fbe95630c3d6"',
    );
    expect(sitemap).not.toContain("/blog/page/2/");
  });

  it("includes code copy and image preview controls on article pages", () => {
    const article = readFileSync(resolve(root, "dist/posts/101/index.html"), "utf8");

    expect(article).toContain("data-image-lightbox");
    expect(article).toContain("data-copy-code");
    expect(article).toContain('target.matches(".prose img")');
    expect(article).toContain("event.preventDefault()");
    expect(article).toContain("navigator.clipboard.writeText(code)");
    expect(article).toContain("external-link-favicon");
    expect(article).toContain("${target.origin}/favicon.ico");
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

  it("keeps site-owned pages outside the Issues CMS", async () => {
    await expect(access(resolve(root, "dist/friends/index.html"))).resolves.toBe(
      undefined,
    );
    await expect(access(resolve(root, "dist/workouts/index.html"))).resolves.toBe(
      undefined,
    );
    await expect(access(resolve(root, "dist/tools/index.html"))).resolves.toBe(
      undefined,
    );

    const friends = readFileSync(resolve(root, "dist/friends/index.html"), "utf8");
    const workouts = readFileSync(resolve(root, "dist/workouts/index.html"), "utf8");
    const tools = readFileSync(resolve(root, "dist/tools/index.html"), "utf8");
    const workoutSnapshot = JSON.parse(
      readFileSync(resolve(root, "src/data/workouts.json"), "utf8"),
    ) as Array<{ activityDate: string }>;
    const latestWorkoutDate = workoutSnapshot
      .map(({ activityDate }) => activityDate)
      .sort()
      .at(-1);
    expect(friends).toContain("Yuang&#39;s Blog");
    expect(workouts).toContain("力量训练");
    expect(workouts).toContain("最近 7 天");
    expect(workouts).toContain(`统计截至 ${latestWorkoutDate}`);
    expect(workouts).toContain('data-workout-view="list"');
    expect(workouts).toContain('data-workout-view="calendar"');
    expect(workouts).toContain('role="tablist"');
    expect(workouts).toContain('class="workout-kind workout-kind--strength"');
    expect(workouts).toContain('class="workout-calendar"');
    expect(workouts).toContain('aria-describedby="workout-detail-');
    expect(workouts).toContain('role="tooltip"');
    expect(workouts).not.toContain("数据快照更新于");
    expect(tools).toContain("Mac mini M2 Pro");
    expect(tools).toContain("软件工具");
    expect(tools).not.toContain("Nikon");
    expect(tools).not.toContain("唯卓仕");
  });
});
