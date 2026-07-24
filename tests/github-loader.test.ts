import { describe, expect, it, vi } from "vitest";

import { loadGitHubIssues } from "@/github/load-issues";

function response(data: unknown): Response {
  return new Response(JSON.stringify({ data }), {
    headers: { "content-type": "application/json" },
  });
}

interface TestIssueNode {
  [key: string]: unknown;
  comments: {
    nodes: Array<Record<string, unknown>>;
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
  };
}

function issueNode(number: number): TestIssueNode {
  return {
    id: `I_${number}`,
    number,
    title: `Issue ${number}`,
    body: `Body ${number}`,
    url: `https://github.com/kazoottt/issues-blog/issues/${number}`,
    state: "OPEN",
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-02T00:00:00Z",
    author: { login: "kazoottt" },
    labels: { nodes: [{ name: "blog:publish" }, { name: "技术" }] },
    timelineItems: {
      nodes: [
        {
          createdAt: "2026-07-01T08:00:00Z",
          label: { name: "blog:publish" },
        },
      ],
    },
    reactionGroups: [{ content: "THUMBS_UP", users: { totalCount: 3 } }],
    comments: {
      nodes: [],
      pageInfo: { hasNextPage: false, endCursor: null },
    },
  };
}

describe("GitHub content loader", () => {
  it("paginates repository issues and maps them into source issues", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        response({
          repository: {
            issues: {
              nodes: [issueNode(1)],
              pageInfo: { hasNextPage: true, endCursor: "page-2" },
            },
          },
        }),
      )
      .mockResolvedValueOnce(
        response({
          repository: {
            issues: {
              nodes: [issueNode(2)],
              pageInfo: { hasNextPage: false, endCursor: null },
            },
          },
        }),
      );

    const issues = await loadGitHubIssues({
      owner: "kazoottt",
      repo: "issues-blog",
      token: "test-token",
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(issues.map((issue) => issue.number)).toEqual([1, 2]);
    expect(issues[0]).toMatchObject({
      author: "kazoottt",
      labels: ["blog:publish", "技术"],
      labelEvents: [
        {
          label: "blog:publish",
          createdAt: "2026-07-01T08:00:00Z",
        },
      ],
      reactions: [{ content: "THUMBS_UP", count: 3 }],
    });
  });

  it("fails the build when GitHub returns partial GraphQL errors", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: { repository: null },
          errors: [{ message: "Something went wrong" }],
        }),
      ),
    );

    await expect(
      loadGitHubIssues({
        owner: "kazoottt",
        repo: "issues-blog",
        token: "test-token",
        fetcher,
      }),
    ).rejects.toThrow("GitHub GraphQL: Something went wrong");
  });

  it("paginates long discussions without dropping comments", async () => {
    const first = issueNode(7);
    first.comments = {
      nodes: [
        {
          id: "C_1",
          body: "first",
          url: "https://github.com/comment/1",
          createdAt: "2026-07-01T09:00:00Z",
          updatedAt: "2026-07-01T09:00:00Z",
          author: { login: "reader", avatarUrl: "https://avatar/reader" },
          reactionGroups: [],
        },
      ],
      pageInfo: { hasNextPage: true, endCursor: "comment-page-2" },
    };

    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        response({
          repository: {
            issues: {
              nodes: [first],
              pageInfo: { hasNextPage: false, endCursor: null },
            },
          },
        }),
      )
      .mockResolvedValueOnce(
        response({
          node: {
            comments: {
              nodes: [
                {
                  id: "C_2",
                  body: "second",
                  url: "https://github.com/comment/2",
                  createdAt: "2026-07-01T10:00:00Z",
                  updatedAt: "2026-07-01T10:00:00Z",
                  author: {
                    login: "kazoottt",
                    avatarUrl: "https://avatar/owner",
                  },
                  reactionGroups: [],
                },
              ],
              pageInfo: { hasNextPage: false, endCursor: null },
            },
          },
        }),
      );

    const issues = await loadGitHubIssues({
      owner: "kazoottt",
      repo: "issues-blog",
      token: "test-token",
      fetcher,
    });

    expect(issues[0]?.comments.map((comment) => comment.body)).toEqual([
      "first",
      "second",
    ]);
  });
});
