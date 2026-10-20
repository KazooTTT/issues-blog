import type { Wish } from "./types";

/** Import only Markdown task lines; frontmatter and wikilinks are never published. */
export function parseWishlistNote(markdown: string): Wish[] {
  const body = markdown.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, "");
  return body.split(/\r?\n/).flatMap((line, index) => {
    const match = line.match(/^\s*-\s+\[([ xX])\]\s+(.+)$/);
    if (!match) return [];
    const text = match[2];
    const date = text.match(/^(\d{4}-\d{2}-\d{2})\s+/)?.[1] ?? "";
    const category = [...text.matchAll(/(?:^|\s)#([^\s#]+)/g)]
      .map((tag) => tag[1])
      .join("、");
    const title = text
      .replace(/^\d{4}-\d{2}-\d{2}\s+/, "")
      .replace(/(?:^|\s)#[^\s#]+/g, "")
      .trim();
    if (!title) return [];
    const kind = /买|换|微波炉|MacBook|iPhone/i.test(title)
      ? "buy"
      : /学会|旅行|trip|理财|收益|剪头发/i.test(title)
        ? "do"
        : "other";
    return [
      {
        id: `import-${index}`,
        title,
        description: date ? `记录于 ${date}` : "",
        kind,
        category,
        status: match[1].toLowerCase() === "x" ? "done" : "todo",
        priority: "",
        budget: "",
        targetDate: "",
        url: "",
      },
    ];
  });
}
