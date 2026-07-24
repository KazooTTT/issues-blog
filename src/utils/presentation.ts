import type { Post } from "@/domain/types";

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

export function featuredPosts(posts: Post[]): Post[] {
  return posts.filter((post) => post.featured).slice(0, 5);
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

