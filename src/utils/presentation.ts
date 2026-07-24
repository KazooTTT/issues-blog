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

export function sitePath(path = "/"): string {
  const siteUrl = new URL(
    process.env.SITE_URL ?? "https://kazoottt.github.io/issues-blog",
  );
  const base = siteUrl.pathname.replace(/\/$/, "");
  const baseWithSlash = base ? `${base}/` : "/";

  if (path === "/") {
    return baseWithSlash;
  }
  if (base && (path === base || path.startsWith(baseWithSlash))) {
    return path;
  }
  return `${baseWithSlash}${path.replace(/^\/+/, "")}`;
}
