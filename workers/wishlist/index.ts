import type { Wish, WishlistData } from "../../src/wishlist/types";

export interface Env {
  GITHUB_TOKEN: string;
  GITHUB_OWNER: string;
  PROJECT_NUMBER: string;
  ALLOWED_ORIGINS: string;
}
interface FieldValue {
  field?: { name: string };
  name?: string;
  text?: string;
  number?: number;
  date?: string;
}
export interface ProjectItem {
  id: string;
  isArchived: boolean;
  content: {
    __typename: string;
    title: string;
    body?: string;
    url?: string;
    repository?: { isPrivate: boolean };
  } | null;
  fieldValues: { nodes: FieldValue[] };
}
interface Project {
  title: string;
  url: string;
  public: boolean;
  items: {
    nodes: ProjectItem[];
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
  };
}
const query = `query Wishlist($owner: String!, $number: Int!, $after: String) {
  user(login: $owner) {
    projectV2(number: $number) {
      title url public
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isArchived
          content {
            __typename
            ... on DraftIssue { title body }
            ... on Issue { title body url repository { isPrivate } }
          }
          fieldValues(first: 100) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2SingleSelectField { name } } }
              ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2Field { name } } }
              ... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2Field { name } } }
              ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2Field { name } } }
            }
          }
        }
      }
    }
  }
}`;

export function toWish(item: ProjectItem): Wish | null {
  const content = item.content;
  if (
    item.isArchived ||
    !content?.title ||
    !["DraftIssue", "Issue"].includes(content.__typename) ||
    content.repository?.isPrivate
  )
    return null;
  const fields = new Map(
    item.fieldValues.nodes
      .filter(Boolean)
      .map((value) => [
        value.field?.name.toLowerCase(),
        String(value.name ?? value.text ?? value.number ?? value.date ?? ""),
      ]),
  );
  const field = (...names: string[]) =>
    names.map((name) => fields.get(name.toLowerCase())).find(Boolean) ?? "";
  const kind = field("类型", "Type", "Kind").toLowerCase();
  const status = field("Status", "状态").toLowerCase();
  return {
    id: item.id,
    title: content.title,
    description: content.body ?? "",
    kind: ["想买", "buy"].includes(kind)
      ? "buy"
      : ["想做", "do"].includes(kind)
        ? "do"
        : "other",
    status: ["已实现", "done", "已完成"].includes(status)
      ? "done"
      : ["进行中", "in progress"].includes(status)
        ? "doing"
        : "todo",
    category: field("分类", "Category"),
    priority: field("优先级", "Priority"),
    budget: field("预算", "Budget"),
    targetDate: field("目标日期", "Target date"),
    url: content.url ?? "",
  };
}

export async function loadWishlist(
  env: Env,
  fetcher: typeof fetch = fetch,
): Promise<WishlistData> {
  if (
    !env.GITHUB_TOKEN ||
    !env.GITHUB_OWNER ||
    !/^[1-9]\d*$/.test(env.PROJECT_NUMBER ?? "")
  )
    throw new Error("configuration");
  const items: Wish[] = [];
  let project: Project | null = null;
  let after: string | null = null;
  const seen = new Set<string>();
  // A bounded paginated fetch; never return an incomplete list silently.
  for (let page = 0; page < 20; page++) {
    const response = await fetcher("https://api.github.com/graphql", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "issues-blog-wishlist",
      },
      body: JSON.stringify({
        query,
        variables: {
          owner: env.GITHUB_OWNER,
          number: Number(env.PROJECT_NUMBER),
          after,
        },
      }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw new Error("upstream");
    const result = (await response.json()) as {
      data?: { user?: { projectV2?: Project } };
      errors?: unknown[];
    };
    const current = result.data?.user?.projectV2;
    if (result.errors?.length || !current || !current.public)
      throw new Error("unavailable");
    project = current;
    items.push(
      ...current.items.nodes
        .map(toWish)
        .filter((wish): wish is Wish => wish !== null),
    );
    if (!current.items.pageInfo.hasNextPage)
      return {
        title: project.title,
        projectUrl: project.url,
        fetchedAt: new Date().toISOString(),
        items,
      };
    after = current.items.pageInfo.endCursor;
    if (!after || seen.has(after)) throw new Error("pagination");
    seen.add(after);
  }
  throw new Error("pagination");
}

interface EdgeCache {
  match(request: Request): Promise<Response | undefined>;
  put(request: Request, response: Response): Promise<void>;
}
interface Context {
  waitUntil(promise: Promise<unknown>): void;
}
export default {
  async fetch(request: Request, env: Env, ctx: Context): Promise<Response> {
    const origin = request.headers.get("Origin");
    const allowed = (env.ALLOWED_ORIGINS ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    const headers = new Headers({
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      Vary: "Origin",
      "X-Content-Type-Options": "nosniff",
    });
    if (origin && !allowed.includes(origin))
      return new Response(JSON.stringify({ error: "origin_not_allowed" }), {
        status: 403,
        headers,
      });
    if (origin) headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
    const url = new URL(request.url);
    if (url.pathname !== "/api/wishlist")
      return new Response(JSON.stringify({ error: "not_found" }), {
        status: 404,
        headers,
      });
    if (request.method === "OPTIONS")
      return new Response(null, { status: 204, headers });
    if (request.method !== "GET") {
      headers.set("Allow", "GET, OPTIONS");
      return new Response(JSON.stringify({ error: "method_not_allowed" }), {
        status: 405,
        headers,
      });
    }
    try {
      // Include the project identity so a configuration change cannot reuse another project's data.
      const key = new Request(
        `${url.origin}/cache/wishlist/${encodeURIComponent(env.GITHUB_OWNER)}/${env.PROJECT_NUMBER}`,
      );
      const cache = (
        globalThis as unknown as { caches?: { default?: EdgeCache } }
      ).caches?.default;
      const cached = await cache?.match(key);
      if (cached) return new Response(cached.body, { headers });
      const data = await loadWishlist(env);
      const body = JSON.stringify(data);
      if (cache)
        ctx.waitUntil(
          cache.put(
            key,
            new Response(body, {
              headers: {
                "Content-Type": "application/json",
                "Cache-Control": "public, max-age=60",
              },
            }),
          ),
        );
      return new Response(body, { headers });
    } catch {
      // Never send upstream responses or credentials to visitors.
      return new Response(JSON.stringify({ error: "wishlist_unavailable" }), {
        status: 503,
        headers,
      });
    }
  },
};
