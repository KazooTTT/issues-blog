import { describe, expect, it } from "vitest";

import { classifyIssues } from "@/domain/content-policy";
import type { SourceIssue } from "@/domain/types";

const owner = "kazoottt";

function issue(overrides: Partial<SourceIssue> = {}): SourceIssue {
  return {
    number: 17,
    title: "浅尝一篇",
    body: "正文",
    url: "https://github.com/kazoottt/issues-blog/issues/17",
    author: owner,
    state: "OPEN",
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-04T00:00:00Z",
    labels: ["blog:publish", "技术"],
    labelEvents: [
      { label: "blog:publish", createdAt: "2026-07-03T08:00:00Z" },
      { label: "blog:publish", createdAt: "2026-07-04T08:00:00Z" },
    ],
    reactions: [],
    comments: [],
    ...overrides,
  };
}

describe("content publication policy", () => {
  it("publishes only owner-authored labeled issues and preserves the first publication time", () => {
    const result = classifyIssues(
      [
        issue(),
        issue({
          number: 18,
          state: "CLOSED",
          labelEvents: [
            { label: "blog:publish", createdAt: "2026-07-05T08:00:00Z" },
          ],
        }),
        issue({ number: 19, labels: ["技术"] }),
        issue({ number: 20, author: "reader" }),
      ],
      owner,
    );

    expect(result.posts.map((post) => post.number)).toEqual([18, 17]);
    expect(result.posts[1]).toMatchObject({
      publishedAt: "2026-07-03T08:00:00Z",
      updatedAt: "2026-07-04T00:00:00Z",
      tags: ["技术"],
      permalink: "/posts/17/",
    });
  });

  it("separates the single About page from the article timeline", () => {
    const result = classifyIssues(
      [issue(), issue({ number: 2, labels: ["blog:about"] })],
      owner,
    );

    expect(result.about?.number).toBe(2);
    expect(result.posts.map((post) => post.number)).toEqual([17]);
  });

  it("preserves an imported historical publication time instead of the current label time", () => {
    const result = classifyIssues(
      [
        issue({
          body: "正文\n\n<!-- issues-blog:published-at=2021-03-04T00:00:00.000Z -->",
          labelEvents: [
            { label: "blog:publish", createdAt: "2026-07-24T08:00:00Z" },
          ],
        }),
      ],
      owner,
    );

    expect(result.posts[0]?.publishedAt).toBe("2021-03-04T00:00:00.000Z");
  });

  it("rejects multiple About pages", () => {
    expect(() =>
      classifyIssues(
        [
          issue({ number: 2, labels: ["blog:about"] }),
          issue({ number: 3, labels: ["blog:about"] }),
        ],
        owner,
      ),
    ).toThrow("Exactly one blog:about issue is allowed");
  });
});
