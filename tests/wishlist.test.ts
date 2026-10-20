import { describe, expect, it, vi, afterEach } from "vitest";
import worker, {
  loadWishlist,
  toWish,
  type ProjectItem,
  type Env,
} from "../workers/wishlist/index";
import { isWishlistData, safeGithubUrl } from "../src/wishlist/types";
import { parseWishlistNote } from "../src/wishlist/import";

const env: Env = {
  GITHUB_TOKEN: "test-secret",
  GITHUB_OWNER: "KazooTTT",
  PROJECT_NUMBER: "1",
  ALLOWED_ORIGINS: "https://example.com",
};
function item(overrides: Partial<ProjectItem> = {}): ProjectItem {
  return {
    id: "a",
    isArchived: false,
    content: {
      __typename: "DraftIssue",
      title: "自驾旅行",
      body: "先练习开车",
    },
    fieldValues: {
      nodes: [
        { field: { name: "类型" }, name: "想做" },
        { field: { name: "Status" }, name: "In Progress" },
        { field: { name: "预算" }, number: 0 },
        { field: { name: "目标日期" }, date: "2027-01-01" },
      ],
    },
    ...overrides,
  };
}
function response(
  nodes: ProjectItem[],
  next = false,
  cursor: string | null = null,
  isPublic = true,
) {
  return new Response(
    JSON.stringify({
      data: {
        user: {
          projectV2: {
            title: "愿望清单",
            url: "https://github.com/users/KazooTTT/projects/1",
            public: isPublic,
            items: {
              nodes,
              pageInfo: { hasNextPage: next, endCursor: cursor },
            },
          },
        },
      },
    }),
    { headers: { "Content-Type": "application/json" } },
  );
}
afterEach(() => vi.unstubAllGlobals());
describe("wishlist project reader", () => {
  it("maps fields while preserving zero budgets and dates", () => {
    expect(toWish(item())).toMatchObject({
      kind: "do",
      status: "doing",
      budget: "0",
      targetDate: "2027-01-01",
    });
  });
  it("omits archived, redacted, private repository and pull request items", () => {
    for (const value of [
      item({ isArchived: true }),
      item({ content: null }),
      item({
        content: {
          __typename: "Issue",
          title: "private",
          repository: { isPrivate: true },
        },
      }),
      item({ content: { __typename: "PullRequest", title: "PR" } }),
    ])
      expect(toWish(value)).toBeNull();
  });
  it("reads all pages and supplies the cursor", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response([item()], true, "cursor"))
      .mockResolvedValueOnce(response([item({ id: "b" })]));
    const result = await loadWishlist(env, fetcher);
    expect(result.items.map((wish) => wish.id)).toEqual(["a", "b"]);
    expect(JSON.parse(fetcher.mock.calls[1][1].body).variables.after).toBe(
      "cursor",
    );
    expect(isWishlistData(result)).toBe(true);
  });
  it("rejects private projects, API errors and malformed pagination", async () => {
    for (const result of [
      response([], false, null, false),
      new Response(JSON.stringify({ errors: [{ message: "secret" }] })),
      response([], true),
    ]) {
      await expect(
        loadWishlist(env, vi.fn().mockResolvedValue(result)),
      ).rejects.toThrow();
    }
  });
  it("fails safely for missing configuration", async () => {
    const fetcher = vi.fn();
    await expect(
      loadWishlist({ ...env, PROJECT_NUMBER: "" }, fetcher),
    ).rejects.toThrow("configuration");
    expect(fetcher).not.toHaveBeenCalled();
  });
});
describe("wishlist endpoint", () => {
  const ctx = { waitUntil: vi.fn() };
  it("restricts origins, methods and paths without reading GitHub", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const cases = [
      [
        new Request("https://worker.test/api/wishlist", {
          headers: { Origin: "https://evil.test" },
        }),
        403,
      ],
      [new Request("https://worker.test/nope"), 404],
      [
        new Request("https://worker.test/api/wishlist", { method: "POST" }),
        405,
      ],
      [
        new Request("https://worker.test/api/wishlist", {
          method: "OPTIONS",
          headers: { Origin: "https://example.com" },
        }),
        204,
      ],
    ] as const;
    for (const [request, status] of cases)
      expect((await worker.fetch(request, env, ctx)).status).toBe(status);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("sets CORS only on the outgoing response and caches successful data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([item()])));
    const cache = {
      match: vi.fn().mockResolvedValue(undefined),
      put: vi.fn().mockResolvedValue(undefined),
    };
    vi.stubGlobal("caches", { default: cache });
    const result = await worker.fetch(
      new Request("https://worker.test/api/wishlist", {
        headers: { Origin: "https://example.com" },
      }),
      env,
      ctx,
    );
    expect(result.status).toBe(200);
    expect(result.headers.get("Access-Control-Allow-Origin")).toBe(
      "https://example.com",
    );
    expect(result.headers.get("Cache-Control")).toBe("no-store");
    expect(cache.put).toHaveBeenCalledOnce();
    const cached = cache.put.mock.calls[0][1] as Response;
    expect(cached.headers.get("Access-Control-Allow-Origin")).toBeNull();
    expect(cached.headers.get("Cache-Control")).toContain("max-age=60");
  });
  it("does not leak upstream errors or tokens and does not cache failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error(env.GITHUB_TOKEN)),
    );
    const cache = { match: vi.fn().mockResolvedValue(undefined), put: vi.fn() };
    vi.stubGlobal("caches", { default: cache });
    const result = await worker.fetch(
      new Request("https://worker.test/api/wishlist"),
      env,
      ctx,
    );
    expect(result.status).toBe(503);
    expect(await result.text()).toBe('{"error":"wishlist_unavailable"}');
    expect(cache.put).not.toHaveBeenCalled();
  });
});
describe("wishlist import and browser data", () => {
  it("only imports tasks, never frontmatter or private note links", () => {
    const result = parseWishlistNote(
      "---\ntitle: private\n---\n# 愿望\n- [x] 2024-01-01 买相机 #数码\n- [ ] 学会吉他 solo #音乐\n[[愿望清单（私密）]]\n",
    );
    expect(result).toHaveLength(2);
    expect(result[0]).toMatchObject({
      title: "买相机",
      kind: "buy",
      status: "done",
      category: "数码",
      description: "记录于 2024-01-01",
    });
    expect(result[1]).toMatchObject({ kind: "do", status: "todo" });
    expect(JSON.stringify(result)).not.toContain("private");
    expect(JSON.stringify(result)).not.toContain("私密");
  });
  it("rejects unsafe URLs and invalid browser payloads", () => {
    expect(safeGithubUrl("javascript:alert(1)")).toBe("");
    expect(safeGithubUrl("https://github.com.evil.test/x")).toBe("");
    expect(
      isWishlistData({
        title: "x",
        projectUrl: "https://github.com/x",
        fetchedAt: "bad",
        items: [],
      }),
    ).toBe(false);
  });
});
