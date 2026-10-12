import { describe, expect, it } from "vitest";
import { classifyIssues } from "@/domain/content-policy";
import { fixtureIssues } from "@/data/fixture";
import { sitePath } from "@/utils/presentation";
import { popularPosts } from "@/utils/popular-posts";
import type { PageAnalytics } from "@/data/page-analytics";

const posts = classifyIssues(fixtureIssues, "kazoottt").posts;
const report = (pages: PageAnalytics["pages"]): PageAnalytics => ({ generatedAt: "2026-10-12T00:00:00Z", throughDate: "2026-10-11", pages });

describe("popular articles", () => {
  it("ranks published articles by views, resolves ties by publication date, and excludes missing or zero views", () => {
    const [a, b, c, d] = [...posts].sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
    const ordered = popularPosts(posts, report({
      [sitePath(a!.permalink)]: { views: 10, users: 3 },
      [sitePath(b!.permalink)]: { views: 10, users: 8 },
      [sitePath(c!.permalink).replace(/\/$/, "")]: { views: 20, users: 4 },
      [sitePath(d!.permalink)]: { views: 0, users: 0 },
      [sitePath("/posts/999999/")]: { views: 1000, users: 99 },
    }));
    expect(ordered.map((post) => post.number)).toEqual([c!.number, a!.number, b!.number]);
  });

  it("limits the ranking to 20 without changing the original article order", () => {
    const before = posts.map((post) => post.number);
    const analytics = report(Object.fromEntries(posts.map((post, index) => [sitePath(post.permalink), { views: index + 1, users: 1 }])));
    expect(popularPosts(posts, analytics)).toHaveLength(20);
    expect(posts.map((post) => post.number)).toEqual(before);
    expect(popularPosts(posts, report({}))).toEqual([]);
  });
});
