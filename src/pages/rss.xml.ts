import rss from "@astrojs/rss";

import { siteConfig } from "@/config";
import { getSiteContent } from "@/data/site-content";
import { renderMarkdown } from "@/rendering/content";

export async function GET(context: { site: URL | undefined }) {
  if (!context.site) {
    throw new Error("Astro site URL is required to generate RSS");
  }
  const { posts } = await getSiteContent();
  const items = await Promise.all(
    posts.slice(0, siteConfig.feedLimit).map(async (post) => ({
      title: post.title,
      link: post.permalink,
      pubDate: new Date(post.publishedAt),
      description: post.body,
      content: await renderMarkdown(post.body),
      categories: post.tags,
      customData: `<guid isPermaLink="false">issue-${post.number}</guid><updated>${post.updatedAt}</updated>`,
    })),
  );

  return rss({
    title: siteConfig.title,
    description: siteConfig.description,
    site: context.site,
    items,
    trailingSlash: true,
  });
}

