import type { Post } from "@/domain/types";
import { siteConfig } from "@/config";

const archiveDateFormatter = new Intl.DateTimeFormat("en-CA", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: "Asia/Shanghai",
});

export function archiveDateParts(value: string): {
  year: string;
  month: string;
  day: string;
} {
  const parts = Object.fromEntries(
    archiveDateFormatter
      .formatToParts(new Date(value))
      .map(({ type, value: partValue }) => [type, partValue]),
  );

  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
  };
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

export function featuredPosts(posts: Post[]): Post[] {
  return posts
    .filter((post) => post.featured)
    .slice(0, siteConfig.featuredLimit);
}

export function regularPosts(posts: Post[]): Post[] {
  return posts.filter((post) => !post.featured);
}

export function reactionEmoji(content: string): string {
  return (
    {
      THUMBS_UP: "👍",
      THUMBS_DOWN: "👎",
      LAUGH: "😄",
      HOORAY: "🎉",
      CONFUSED: "😕",
      HEART: "❤️",
      ROCKET: "🚀",
      EYES: "👀",
    }[content] ?? "•"
  );
}

// base 必须是构建期常量：预渲染页面在 Node 里构建，能读到 SITE_URL；
// 而 SSR 路由（workouts）在 Worker 运行时没有 process.env.SITE_URL，
// 会退回 GitHub Pages 的 /issues-blog 前缀，让站内链接全部叠成
// /issues-blog/xxx 而 404。__SITE_BASE__ 由 astro.config.mjs 注入，
// 预渲染和 SSR 两边拿到同一个值。
declare const __SITE_BASE__: string;

const buildBase = (
  typeof __SITE_BASE__ === "string" ? __SITE_BASE__ : ""
).replace(/\/$/, "");

export function sitePath(path = "/"): string {
  const base = buildBase;
  const baseWithSlash = base ? `${base}/` : "/";

  if (path === "/") {
    return baseWithSlash;
  }
  if (base && (path === base || path.startsWith(baseWithSlash))) {
    return path;
  }
  return `${baseWithSlash}${path.replace(/^\/+/, "")}`;
}
