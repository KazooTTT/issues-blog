import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { access } from "node:fs/promises";
import { resolve } from "node:path";

import { beforeAll, describe, expect, it } from "vitest";

import { siteConfig } from "@/config";
import { fixtureIssues } from "@/data/fixture";
import { workouts as workoutSnapshot } from "@/data/workouts";
import { classifyIssues } from "@/domain/content-policy";

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

  it("marks writing sources consistently for the persisted navigation filter", () => {
    const home = readFileSync(resolve(root, "dist/client/blog/index.html"), "utf8");
    const archive = readFileSync(resolve(root, "dist/client/blog/archive/index.html"), "utf8");
    for (const html of [home, archive]) {
      expect(html).toContain('role="switch"');
      expect(html).toContain("只看人工");
      expect(html).toContain('data-writing-source="人工写作为主"');
      expect(html).toContain('data-writing-source="AI 写作为主"');
      expect(html).toContain('data-writing-source="unknown"');
      expect(html).toContain("暂无以人工写作为主的文章。");
    }
    expect(archive).toContain("data-writing-group");
  });

  it("provides a popular page with an honest fallback and groups navigation into three dropdowns", () => {
    const popular = readFileSync(resolve(root, "dist/client/blog/popular/index.html"), "utf8");
    expect(popular).toContain("热门文章");
    expect(popular).toContain("访问统计暂时不可用");
    expect(popular).toContain('href="/blog/archive/"');
    const navigation = popular.match(/<nav aria-label="主导航">([\s\S]*?)<\/nav>/)?.[1] ?? "";
    expect(navigation.match(/<details /g)).toHaveLength(3);
    expect(navigation.match(/<summary /g)).toHaveLength(3);
    for (const path of ["popular", "archive", "tags", "projects", "tools", "workouts", "friends", "wishlist", "about"]) {
      expect(navigation).toContain(`href="/blog/${path}/"`);
    }
    expect(navigation).toMatch(/<summary[^>]*nav-link-active[^>]*>文章<\/summary>/);
  });

  it("builds a wishlist shell without baking personal data into the page", () => {
    const html = readFileSync(resolve(root, "dist/client/blog/wishlist/index.html"), "utf8");
    expect(html).toContain("愿望清单");
    expect(html).toContain("data-wishlist");
    expect(html).toContain("data-search");
    expect(html).toContain("data-status");
    expect(html).not.toContain("换一个 iPhone Pro");
    const navigation = html.match(/<nav aria-label="主导航">([\s\S]*?)<\/nav>/)?.[1] ?? "";
    expect(navigation).toMatch(/<summary[^>]*nav-link-active[^>]*>生活<\/summary>/);
  });

  it("shares About discussion on home and About with older messages collapsed", () => {
    for (const route of ["index.html", "about/index.html"]) {
      const page = readFileSync(resolve(root, "dist/client/blog", route), "utf8");
      expect(page).toContain('aria-label="留言"');
      expect(page).toContain("11 条留言");
      expect(page).toContain('href="https://github.com/kazoottt/issues-blog/issues/1">去 GitHub 留言');
      const older = page.match(/<details class="older-comments">([\s\S]*?)<\/details>/)?.[1];
      expect(older).toContain("第 1 条访客留言");
      expect(older).not.toContain("第 2 条访客留言");
      expect(page).toContain("第 11 条访客留言");
      expect(page.match(/class="comment"/g)).toHaveLength(11);
    }
    const emptyPost = readFileSync(resolve(root, "dist/client/blog/posts/100/index.html"), "utf8");
    expect(emptyPost).toContain("还没有留言，欢迎来打个招呼。");
    expect(emptyPost).toContain("去 GitHub 留言");
  });

  it("generates stable article routes and sends the full-list action to archive", async () => {
    await expect(access(resolve(root, "dist/client/blog/posts/101/index.html"))).resolves.toBe(
      undefined,
    );
    const home = readFileSync(resolve(root, "dist/client/blog/index.html"), "utf8");
    const sitemap = readFileSync(
      resolve(root, "dist/client/blog/sitemap-0.xml"),
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
    const article = readFileSync(resolve(root, "dist/client/blog/posts/101/index.html"), "utf8");

    expect(article).toContain("data-image-lightbox");
    expect(article).toContain("data-copy-code");
    expect(article).toContain('target.matches(".prose img")');
    expect(article).toContain("event.preventDefault()");
    expect(article).toContain("navigator.clipboard.writeText(code)");
    expect(article).toContain("external-link-favicon");
    expect(article).toContain("${target.origin}/favicon.ico");
  });

  it("renders linked article tags once at the top of the post", () => {
    const article = readFileSync(resolve(root, "dist/client/blog/posts/101/index.html"), "utf8");
    const header = article.match(/<header class="post-header">([\s\S]*?)<\/header>/)?.[1];
    const footer = article.match(/<footer class="post-footer">([\s\S]*?)<\/footer>/)?.[1];

    expect(header).toContain('href="/blog/tags/');
    expect(header).toContain('class="tag"');
    expect(article.match(/class="post-tags"/g)).toHaveLength(1);
    expect(footer).not.toContain('class="tag"');
  });

  it("keeps archive rows focused on dates and titles", () => {
    const archive = readFileSync(resolve(root, "dist/client/blog/archive/index.html"), "utf8");
    const article = readFileSync(resolve(root, "dist/client/blog/posts/101/index.html"), "utf8");

    expect(archive).not.toContain('class="archive-tags"');
    expect(archive).not.toContain('class="archive-tag"');
    expect(archive).toContain(
      'href="https://github.com/KazooTTT/issues-blog/issues/new?template=article.md"',
    );
    expect(archive).toContain(
      'href="https://github.com/KazooTTT/issues-blog/issues/new?template=article-draft.md"',
    );
    expect(archive).toContain("新增博文");
    expect(archive).toContain("新增草稿");
    expect(article).not.toContain("新增博文");
    expect(article).not.toContain("新增草稿");
  });

  it("groups periodic review tags under one summary menu item", () => {
    const home = readFileSync(resolve(root, "dist/client/blog/index.html"), "utf8");
    const summary = readFileSync(
      resolve(root, "dist/client/blog/collections/summary/index.html"),
      "utf8",
    );

    expect(home).toContain('href="/blog/collections/summary/">总结</a>');
    const navigation = home.match(/<nav aria-label="主导航">([\s\S]*?)<\/nav>/)?.[1];
    expect(navigation).toBeDefined();
    expect(navigation).not.toContain('href="/blog/tags/%E5%91%A8%E6%8A%A5/">周报</a>');
    expect(summary).toContain("欢迎来到我的博客");
    expect(summary).toContain("第 100 次记录");
    expect(summary).toContain("第 99 次记录");
    expect(summary).toContain("第 98 次记录");
    expect(summary).toContain("COLLECTION · 4 POSTS");
  });

  it("renders a standalone projects page with its own card layout", () => {
    const home = readFileSync(resolve(root, "dist/client/blog/index.html"), "utf8");
    const projects = readFileSync(
      resolve(root, "dist/client/blog/projects/index.html"),
      "utf8",
    );

    expect(home).toContain('href="/blog/projects/">项目</a>');
    expect(projects).toContain("PROJECTS · 2 ENTRIES");
    expect(projects).toContain("issues-blog：以 GitHub Issues 为源的博客");
    expect(projects).toContain("声控烤箱：把日常记录变成长期资产");
    expect(projects).toContain('class="project-grid"');
    expect(projects).not.toContain('class="post-list"');
  });

  it("keeps the selected theme synchronized across page loads and tabs", () => {
    const home = readFileSync(resolve(root, "dist/client/blog/index.html"), "utf8");
    const article = readFileSync(resolve(root, "dist/client/blog/posts/101/index.html"), "utf8");

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
    const rss = readFileSync(resolve(root, "dist/client/blog/rss.xml"), "utf8");
    const sitemap = readFileSync(
      resolve(root, "dist/client/blog/sitemap-0.xml"),
      "utf8",
    );

    expect(rss).toContain("第 76 次记录");
    expect(rss).toContain("<content:encoded>");
    expect(rss).toContain("&lt;h2&gt;这次记录什么&lt;/h2&gt;");
    expect(sitemap).toContain("https://example.com/blog/posts/101/");
  });

  it("keeps site-owned pages outside the Issues CMS", async () => {
    await expect(access(resolve(root, "dist/client/blog/friends/index.html"))).resolves.toBe(
      undefined,
    );
    await expect(access(resolve(root, "dist/client/blog/tools/index.html"))).resolves.toBe(
      undefined,
    );

    const friends = readFileSync(resolve(root, "dist/client/blog/friends/index.html"), "utf8");
    const tools = readFileSync(resolve(root, "dist/client/blog/tools/index.html"), "utf8");
    // Workouts are SSR routes now, so the page is verified at its source and data
    // instead of a prerendered dist/client/blog/workouts/index.html artifact.
    const workouts = readFileSync(resolve(root, "src/pages/workouts.astro"), "utf8");
    const workoutDetails = readFileSync(
      resolve(root, "src/components/WorkoutDetails.astro"),
      "utf8",
    );
    const latestWorkoutDate = workoutSnapshot
      .map(({ activityDate }) => activityDate)
      .sort()
      .at(-1);
    expect(friends).toContain("Yuang&#39;s Blog");
    expect(workoutSnapshot.some(({ activityType }) => activityType === "strength_training")).toBe(
      true,
    );
    expect(workoutDetails).toContain('strength_training: "力量训练"');
    expect(workouts).toContain("最近 7 天");
    expect(workouts).toContain("统计截至 {latestDate}");
    expect(latestWorkoutDate).toBeDefined();
    expect(workouts).toContain('data-workout-view="list"');
    expect(workouts).toContain('data-workout-view="calendar"');
    expect(workouts).toContain('role="tablist"');
    expect(workouts).toContain('class:list={["workout-kind", `workout-kind--${kind}`]}');
    expect(workouts).toContain("strength: { label: \"力量\", mark: \"力\" }");
    expect(workouts).toContain('class="workout-calendar"');
    expect(workouts).toContain("aria-describedby={detailId}");
    expect(workouts).toContain('role="tooltip"');
    expect(workouts).toContain("<WorkoutDetails workout={workout} summary />");
    // The summary tooltip renders display labels only; the field names are used
    // solely for the summary whitelist and never printed.
    expect(workoutDetails).toContain(
      '!summary || ["activityDate", "durationSeconds", "caloriesKcal", "averageHeartRateBpm", "maxHeartRateBpm", "trainingEffectLabel"].includes(key)',
    );
    expect(workoutDetails).toContain(
      "{details.map(([, label, value]) => <div><dt>{label}</dt><dd>{value}</dd></div>)}",
    );
    expect(workouts).not.toContain("数据快照更新于");
    expect(tools).toContain("Mac mini M2 Pro");
    expect(tools).toContain("软件工具");
    expect(tools).not.toContain("Nikon");
    expect(tools).not.toContain("唯卓仕");
  });

  it("keeps workout labels readable without exposing source field names", () => {
    // The detail route is SSR; assert the label mapping in the component and the
    // actual snapshot values it renders.
    const workoutDetails = readFileSync(
      resolve(root, "src/components/WorkoutDetails.astro"),
      "utf8",
    );
    const workout = workoutSnapshot.find(({ externalId }) => externalId === "612229533");
    expect(workout).toBeDefined();

    expect(workoutDetails).toContain('["startTimeLocal", "本地开始",');
    expect(workoutDetails).toContain("（Asia/Shanghai）");
    expect(workoutDetails).not.toContain("GMT 开始");
    expect(workoutDetails).not.toContain("startTimeGmt");
    expect(workoutDetails).not.toContain("移动时长");
    expect(workoutDetails).not.toContain("movingDurationSeconds");
    expect(workout?.distanceMeters).toBe(0);
    expect(workout?.averageSpeedMps).toBe(0);
    expect(workoutDetails).toContain(
      ".filter(([key]) => workout[key as keyof Workout] !== 0)",
    );
    expect(workoutDetails).toContain('["activityType", "Garmin 类型",');
    expect(workout?.activityType).toBe("indoor_cardio");
    expect(workoutDetails).toContain('indoor_cardio: "室内有氧"');
    expect(workoutDetails).toContain('["trainingEffectLabel", "主要训练效果",');
    expect(workout?.trainingEffectLabel).toBe("SPEED");
    expect(workoutDetails).toContain("SPEED: {");
    expect(workoutDetails).toContain('name: "速度"');
    expect(workoutDetails).not.toContain("查看 Garmin 原始字段名");
    expect(workoutDetails).not.toContain("（startTimeLocal）");
    expect(workoutDetails).not.toContain("（activityType）");
    expect(workoutDetails).not.toContain("（trainingEffectLabel）");
    expect(workoutDetails).toContain("主要训练收益偏向速度");
  });

  it("places the review before the activity summary and links adjacent workouts", () => {
    // Workout detail is SSR; verify the template order and that the review
    // action points at the fixture's review Issue.
    const workout = readFileSync(resolve(root, "src/pages/workouts/[id].astro"), "utf8");
    const workoutDetails = readFileSync(
      resolve(root, "src/components/WorkoutDetails.astro"),
      "utf8",
    );
    const { workoutReviews } = classifyIssues(fixtureIssues, siteConfig.owner);
    const review = workoutReviews.find(({ workoutId }) => workoutId === "622983356");
    const reviewIndex = workout.indexOf('class="workout-review"');
    const summaryIndex = workout.indexOf("<WorkoutDetails workout={workout} />");

    expect(reviewIndex).toBeGreaterThan(-1);
    expect(summaryIndex).toBeGreaterThan(reviewIndex);
    expect(workoutDetails).toContain("<h4>活动摘要</h4>");
    expect(workout).toContain('class="workout-detail-navigation"');
    expect(workout).toContain("上一个运动");
    expect(workout).toContain("下一个运动");
    expect(workout).toContain('rel="prev"');
    expect(workout).toContain('rel="next"');
    expect(workout).toContain("编辑复盘 ↗");
    expect(review?.number).toBe(202);
    expect(review?.url).toBe("https://github.com/kazoottt/issues-blog/issues/202");
    expect(workout).toContain("href={reviewActionUrl}");
  });

  it("marks reviewed workouts in the list and calendar", () => {
    // Workouts index is SSR; the review mark is rendered in all three workout
    // renderings (list row, calendar marker, calendar agenda).
    const workouts = readFileSync(resolve(root, "src/pages/workouts.astro"), "utf8");
    const { workoutReviews } = classifyIssues(fixtureIssues, siteConfig.owner);
    const reviewedWorkoutIds = new Set(workoutReviews.map(({ workoutId }) => workoutId));

    expect(workouts).toContain('class="workout-review-mark"');
    expect(workouts).toContain("已有复盘");
    expect(workouts).not.toContain(">复</span>");
    expect(
      workouts.match(/reviewsByWorkoutId\.has\(workout\.externalId\)/g)?.length,
    ).toBeGreaterThanOrEqual(3);
    expect(workoutReviews.length).toBeGreaterThan(0);
    expect(workoutSnapshot.some(({ externalId }) => reviewedWorkoutIds.has(externalId))).toBe(
      true,
    );
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
