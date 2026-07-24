import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import rehypeStringify from "rehype-stringify";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified } from "unified";

import type { SourceComment } from "@/domain/types";

const githubStyleSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    "details",
    "summary",
    "kbd",
  ],
};

interface MarkdownNode {
  type: string;
  value?: string;
  children?: MarkdownNode[];
}

function textContent(node: MarkdownNode): string {
  if (node.type === "text" || node.type === "inlineCode") {
    return node.value ?? "";
  }
  return (node.children ?? []).map(textContent).join("");
}

export async function renderMarkdown(markdown: string): Promise<string> {
  const output = await unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeSanitize, githubStyleSchema)
    .use(rehypeStringify)
    .process(markdown);

  return String(output);
}

export function deriveExcerpt(markdown: string, maxLength = 120): string {
  const tree = unified().use(remarkParse).use(remarkGfm).parse(markdown);
  const paragraph = (tree.children as MarkdownNode[]).find(
    (node) => node.type === "paragraph" && textContent(node).trim(),
  );
  const text = paragraph ? textContent(paragraph).replace(/\s+/g, " ").trim() : "";

  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trimEnd()}…`;
}

export function splitDiscussion(comments: SourceComment[]): {
  older: SourceComment[];
  latest: SourceComment[];
} {
  if (comments.length <= 10) {
    return { older: [], latest: comments };
  }
  return {
    older: comments.slice(0, -10),
    latest: comments.slice(-10),
  };
}

