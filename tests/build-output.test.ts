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

  it("renders linked article tags once at the top of the post", () => {
    const article = readFileSync(resolve(root, "dist/posts/101/index.html"), "utf8");
    const header = article.match(/<header class="post-header">([\s\S]*?)<\/header>/)?.[1];
    const footer = article.match(/<footer class="post-footer">([\s\S]*?)<\/footer>/)?.[1];

    expect(header).toContain('href="/blog/tags/');
    expect(header).toContain('class="tag"');
    expect(article.match(/class="post-tags"/g)).toHaveLength(1);
    expect(footer).not.toContain('class="tag"');
  });

  it("keeps archive rows focused on dates and titles", () => {
    const archive = readFileSync(resolve(root, "dist/archive/index.html"), "utf8");

    expect(archive).not.toContain('class="archive-tags"');
    expect(archive).not.toContain('class="archive-tag"');
  });

  it("keeps the selected theme synchronized across page loads and tabs", () => {
    const home = readFileSync(resolve(root, "dist/index.html"), "utf8");
    const article = readFileSync(resolve(root, "dist/posts/101/index.html"), "utf8");

    for (const page of [home, article]) {
      expect(page).toContain("window.blogTheme");
      expect(page).toContain('document.cookie = `theme=${theme}; Path=/;');
      expect(page).toContain('new BroadcastChannel("blog-theme")');
      expect(page).toContain('addEventListener("pageshow"');
      expect(page).toContain('addEventListener("storage"');

      const themeBootstrap = page.indexOf("window.blogTheme");
      expect(themeBootstrap).toBeLessThan(
        page.indexOf("www.googletagmanager.com"),
      );
      expect(themeBootstrap).toBeLessThan(page.indexOf('rel="stylesheet"'));
    }
  });

  it("keeps the current page visible while navigating to the next theme-aware document", () => {
    const styles = readFileSync(resolve(root, "src/styles/global.css"), "utf8");

    expect(styles).toMatch(
      /@view-transition\s*\{\s*navigation:\s*auto;\s*\}/,
    );
  });

  it("centers Markdown images and gives them a reading-friendly surface", () => {
    const styles = readFileSync(resolve(root, "src/styles/global.css"), "utf8");

    expect(styles).toMatch(
      /\.prose p:has\(> img:only-child\) > img,[^{]*\{[^}]*display:\s*block;/s,
    );
    expect(styles).toMatch(
      /\.prose p:has\(> img:only-child\) > img,[^{]*\{[^}]*margin-inline:\s*auto;/s,
    );
    expect(styles).toMatch(
      /\.prose p:has\(> img:only-child\) > img,[^{]*\{[^}]*border-radius:/s,
    );
    expect(styles).toContain(
      ".prose a:not(.external-link-with-favicon):has(> img:only-child)",
    );
    expect(styles).not.toContain(".prose a:has(> img:only-child)");
    expect(styles).not.toContain(".prose img:not(.external-link-favicon)");
  });

  it("uses the same main content width on home and inner pages", () => {
    const styles = readFileSync(resolve(root, "src/styles/global.css"), "utf8");

    expect(styles).not.toMatch(/\.post\s*\{[^}]*width:/s);
    expect(styles).not.toMatch(/\.discussion\s*\{[^}]*width:/s);
    expect(styles).not.toMatch(/\.about-body\s*\{[^}]*width:/s);
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
    const tooltip = workouts.match(/role="tooltip"[\s\S]*?<section class="workout-data-section is-summary">[\s\S]*?<\/section>/)?.[0];
    expect(tooltip).toBeTruthy();
    expect(tooltip).not.toContain("activityDate");
    expect(tooltip).not.toContain("durationSeconds");
    expect(tooltip).not.toContain("trainingEffectLabel");
    expect(workouts).not.toContain("数据快照更新于");
    expect(tools).toContain("Mac mini M2 Pro");
    expect(tools).toContain("软件工具");
    expect(tools).not.toContain("Nikon");
    expect(tools).not.toContain("唯卓仕");
  });

  it("keeps workout labels readable without exposing source field names", () => {
    const workout = readFileSync(
      resolve(root, "dist/workouts/612229533/index.html"),
      "utf8",
    );

    expect(workout).toContain("<dt>本地开始</dt>");
    expect(workout).toContain("Asia/Shanghai");
    expect(workout).not.toContain("GMT 开始");
    expect(workout).not.toContain("startTimeGmt");
    expect(workout).not.toContain("移动时长");
    expect(workout).not.toContain("movingDurationSeconds");
    expect(workout).not.toContain("<dt>距离</dt><dd>0 m</dd>");
    expect(workout).not.toContain("<dt>平均速度</dt><dd>0 km/h</dd>");
    expect(workout).toContain("<dt>Garmin 类型</dt>");
    expect(workout).toContain("室内有氧</dd>");
    expect(workout).toContain("<dt>主要训练效果</dt>");
    expect(workout).toContain("速度</dd>");
    expect(workout).not.toContain("查看 Garmin 原始字段名");
    expect(workout).not.toContain("（startTimeLocal）");
    expect(workout).not.toContain("（activityType）");
    expect(workout).not.toContain("（trainingEffectLabel）");
    expect(workout).toContain("主要训练收益偏向速度");
  });

  it("keeps workout tooltips pointed at their trigger while avoiding viewport edges", () => {
    const workoutPage = readFileSync(resolve(root, "src/pages/workouts.astro"), "utf8");
    const styles = readFileSync(resolve(root, "src/styles/global.css"), "utf8");

    expect(workoutPage).toContain('event.clientX');
    expect(workoutPage).toContain('"--tooltip-anchor-x"');
    expect(workoutPage).toContain('"--tooltip-shift-x"');
    expect(workoutPage).toContain('"--tooltip-arrow-x"');
    expect(workoutPage).toContain('tooltipRect.top < viewportGap ? "bottom" : "top"');
    expect(workoutPage).toContain(
      'event.target.closest(".workout-calendar-detail")',
    );
    expect(styles).toContain("left: var(--tooltip-arrow-x, 50%)");
    expect(styles).not.toContain(
      ".workout-calendar-day:nth-child(7n + 1) .workout-calendar-detail",
    );
    expect(styles).not.toContain(
      ".workout-calendar-day:nth-child(7n) .workout-calendar-detail",
    );
  });
});
