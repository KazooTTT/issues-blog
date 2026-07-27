import { describe, expect, it } from "vitest";

import {
  deriveExcerpt,
  renderMarkdown,
  renderMarkdownDocument,
  splitDiscussion,
} from "@/rendering/content";
import type { SourceComment } from "@/domain/types";

describe("content rendering", () => {
  it("renders GFM and safe GitHub-style HTML while removing executable content", async () => {
    const html = await renderMarkdown(`
| A | B |
| - | - |
| 1 | 2 |

<details><summary>展开</summary><kbd>⌘</kbd></details>

<script>alert("x")</script>
<a href="javascript:alert(1)" onclick="alert(2)">unsafe</a>
`);

    expect(html).toContain("<table>");
    expect(html).toContain("<details>");
    expect(html).toContain("<summary>展开</summary>");
    expect(html).toContain("<kbd>⌘</kbd>");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("onclick");
  });

  it("syntax-highlights fenced code while keeping unknown languages readable", async () => {
    const html = await renderMarkdown(`
\`\`\`ts
const answer: number = 42;
\`\`\`

\`\`\`made-up-language
still readable
\`\`\`
`);

    expect(html).toContain('class="shiki github-dark-default"');
    expect(html).toContain("<span");
    expect(html).toContain("const");
    expect(html).toContain('class="language-made-up-language"');
    expect(html).toContain("still readable");
  });

  it("derives a featured excerpt from the first prose paragraph", () => {
    expect(
      deriveExcerpt(`
![cover](https://example.com/cover.jpg)

## 开始

这是第一段真正适合展示在首页的正文，它应该成为文章摘要。
`),
    ).toBe("这是第一段真正适合展示在首页的正文，它应该成为文章摘要。");
  });

  it("extracts rendered external references in their first-seen order", async () => {
    const { references } = await renderMarkdownDocument(`
[项目主页](https://example.com/project)

再次引用 [同一页面](https://example.com/project)，以及 <https://github.com/KazooTTT/issues-blog>。

[站内页面](/about/)
[绝对站内页面](https://blog.example.com/about/)

![外部图片](https://images.example.com/cover.jpg)

<a href="https://source.example.net/article">原始 HTML 来源</a>
`, "https://blog.example.com");

    expect(references).toEqual([
      { href: "https://example.com/project", label: "项目主页" },
      {
        href: "https://github.com/KazooTTT/issues-blog",
        label: "https://github.com/KazooTTT/issues-blog",
      },
      {
        href: "https://source.example.net/article",
        label: "原始 HTML 来源",
      },
    ]);
  });

  it("keeps the latest ten comments visible and collapses older discussion", () => {
    const comments = Array.from({ length: 13 }, (_, index) => ({
      id: String(index + 1),
      body: `Comment ${index + 1}`,
    })) as SourceComment[];

    const result = splitDiscussion(comments);

    expect(result.older.map((comment) => comment.id)).toEqual(["1", "2", "3"]);
    expect(result.latest.map((comment) => comment.id)).toEqual([
      "4",
      "5",
      "6",
      "7",
      "8",
      "9",
      "10",
      "11",
      "12",
      "13",
    ]);
  });
});
