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
