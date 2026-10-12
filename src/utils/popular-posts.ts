import type { Post } from "@/domain/types";
import { statisticsForPath, type PageAnalytics } from "@/data/page-analytics";
import { sitePath } from "@/utils/presentation";

export function popularPosts(posts: Post[], analytics: PageAnalytics): Post[] {
  return posts
    .map((post) => ({ post, views: statisticsForPath(analytics, sitePath(post.permalink)).views }))
    .filter(({ views }) => views > 0)
    .sort((left, right) =>
      right.views - left.views ||
      right.post.publishedAt.localeCompare(left.post.publishedAt) ||
      left.post.number - right.post.number,
    )
    .slice(0, 20)
    .map(({ post }) => post);
}
