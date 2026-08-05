export const siteConfig = {
  title: "KazooTTT 声控烤箱",
  tagline: "记录技术、生活，以及还没有完全想明白的事情。",
  description:
    "KazooTTT 的个人写作空间，记录技术、生活，以及那些还没有完全想明白的事情。",
  owner: "kazoottt",
  homePostLimit: 10,
  featuredLimit: 5,
  feedLimit: 20,
  primaryTags: ["随笔", "笔记"],
  projectTag: "项目",
  tagCollections: [
    {
      slug: "summary",
      label: "总结",
      description: "按时间回顾阶段性的记录、复盘与总结。",
      tags: ["周报", "月报", "季报", "年报", "年度总结", "总结"],
    },
  ],
} as const;
