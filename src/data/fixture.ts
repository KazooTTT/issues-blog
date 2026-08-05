import type { SourceIssue } from "@/domain/types";

const topics = ["技术", "生活", "摄影", "随笔"];

export const fixtureIssues: SourceIssue[] = [
  ...Array.from({ length: 26 }, (_, index): SourceIssue => {
    const number = 101 - index;
    const day = String((index % 27) + 1).padStart(2, "0");
    const publishedAt = `2026-06-${day}T08:00:00Z`;
    return {
      number,
      title:
        index === 0
          ? "欢迎来到我的博客"
          : `第 ${number} 次记录`,
      body:
        index === 0
          ? `这里是 **KazooTTT 声控烤箱**。\n\n我会在这里记录技术、生活，以及那些还没有完全想明白的事情。\n\n## 为什么写作\n\n写作不一定要得出结论，能够准确记录当时的判断就已经足够。\n\n<details><summary>这里会记录什么</summary>\n\n代码、照片和一些不太成熟的想法。\n\n</details>`
          : `这是第 ${number} 次记录。写作不一定要得出结论，能够准确记录当时的判断就已经足够。\n\n## 这次记录什么\n\n一点 ${topics[index % topics.length]}，再加一点没有完成的想法。`,
      url: `https://github.com/kazoottt/issues-blog/issues/${number}`,
      author: "kazoottt",
      state: index % 3 === 0 ? "CLOSED" : "OPEN",
      createdAt: `2026-06-${day}T00:00:00Z`,
      updatedAt: publishedAt,
      labels: [
        "blog:publish",
        ...(index < 2 ? ["blog:featured"] : []),
        topics[index % topics.length]!,
        ...(index === 0 ? ["周报"] : []),
        ...(index === 1 ? ["月报"] : []),
        ...(index === 2 ? ["季报"] : []),
        ...(index === 3 ? ["总结"] : []),
      ],
      labelEvents: [{ label: "blog:publish", createdAt: publishedAt }],
      reactions:
        index < 4 ? [{ content: "THUMBS_UP", count: 8 - index }] : [],
      comments:
        index === 0
          ? [
              {
                id: "comment-1",
                body: "第一篇看起来不错。",
                url: "https://github.com/kazoottt/issues-blog/issues/101#issuecomment-1",
                author: "reader",
                avatarUrl: "https://github.com/identicons/reader.png",
                createdAt: "2026-06-02T09:00:00Z",
                updatedAt: "2026-06-02T09:00:00Z",
                reactions: [{ content: "HEART", count: 1 }],
              },
            ]
          : [],
    };
  }),
  {
    number: 301,
    title: "issues-blog：以 GitHub Issues 为源的博客",
    body: `把 GitHub Issues 当作写作后台，用 Astro 做展示层，发布资格、永久链接和讨论都围绕 Issue 工作流定义。

## 想解决的问题

不想再维护一套独立的 CMS 或数据库，又能保留发布控制、评论讨论和可迁移的内容快照。

## 当前状态

文章源、构建产物和归档已经跑通，导航入口按随笔 / 笔记 / 总结分好类。`,
    url: "https://github.com/kazoottt/issues-blog/issues/301",
    author: "kazoottt",
    state: "OPEN",
    createdAt: "2026-05-20T08:00:00Z",
    updatedAt: "2026-06-10T08:00:00Z",
    labels: ["blog:publish", "项目", "技术"],
    labelEvents: [{ label: "blog:publish", createdAt: "2026-05-20T08:00:00Z" }],
    reactions: [{ content: "THUMBS_UP", count: 5 }],
    comments: [],
  },
  {
    number: 302,
    title: "声控烤箱：把日常记录变成长期资产",
    body: `一个想把零散记录沉淀为可回看、可检索内容的长期实验。

## 做了什么

从随手的跑步复盘、工具清单，到阶段性总结，都收拢到同一个写作空间里，避免分散在多处最后找不到。

## 下一步

继续完善项目入口，让不同性质的记录各有归处，而不是全部塞进时间线。`,
    url: "https://github.com/kazoottt/issues-blog/issues/302",
    author: "kazoottt",
    state: "OPEN",
    createdAt: "2026-04-02T08:00:00Z",
    updatedAt: "2026-05-01T08:00:00Z",
    labels: ["blog:publish", "项目", "生活"],
    labelEvents: [{ label: "blog:publish", createdAt: "2026-04-02T08:00:00Z" }],
    reactions: [],
    comments: [],
  },
  {
    number: 202,
    title: "运动复盘｜2026-07-31｜舞蹈健身",
    body: `<!-- workout-review:v1 -->
<!-- workout-id: 622983356 -->

## 这次完成得怎么样

整体状态不错，后半段体力有所下降，但完成度比上次更稳定。

## 做得好的地方

- 动作衔接更流畅
- 高心率阶段仍保持了节奏

## 下次调整

热身增加 5 分钟，前半段稍微控制强度。`,
    url: "https://github.com/kazoottt/issues-blog/issues/202",
    author: "kazoottt",
    state: "OPEN",
    createdAt: "2026-08-01T08:00:00Z",
    updatedAt: "2026-08-02T08:00:00Z",
    labels: ["workout:review"],
    labelEvents: [
      { label: "workout:review", createdAt: "2026-08-01T08:00:00Z" },
    ],
    reactions: [],
    comments: [],
  },
  {
    number: 1,
    title: "关于 KazooTTT",
    body: `我喜欢把复杂的东西拆开看看，也喜欢记录那些还没有答案的问题。\n\n这个博客以 GitHub Issues 为内容源，但最终想成为的是一个安静、耐读的个人空间。`,
    url: "https://github.com/kazoottt/issues-blog/issues/1",
    author: "kazoottt",
    state: "OPEN",
    createdAt: "2026-05-01T00:00:00Z",
    updatedAt: "2026-05-01T00:00:00Z",
    labels: ["blog:about"],
    labelEvents: [],
    reactions: [],
    comments: [],
  },
];
