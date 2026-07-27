import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import rehypeStringify from "rehype-stringify";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { codeToHast } from "shiki";
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

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: {
    className?: string[];
    href?: string;
  };
  children?: HastNode[];
}

function textContent(node: MarkdownNode): string {
  if (node.type === "text" || node.type === "inlineCode") {
    return node.value ?? "";
  }
  return (node.children ?? []).map(textContent).join("");
}

function highlightCodeBlocks() {
  return async (tree: HastNode) => {
    async function visit(node: HastNode): Promise<void> {
      if (
        node.tagName === "pre" &&
        node.children?.length === 1 &&
        node.children[0].tagName === "code"
      ) {
        const code = node.children[0];
        const languageClass = code.properties?.className?.find((className) =>
          className.startsWith("language-"),
        );
        const language = languageClass?.slice("language-".length);

        if (language) {
          try {
            const highlighted = (await codeToHast(textContent(code), {
              lang: language,
              theme: "github-dark-default",
            })) as HastNode;
            const highlightedPre = highlighted.children?.[0];

            if (highlightedPre) {
              Object.assign(node, highlightedPre);
              return;
            }
          } catch {
            // Unsupported language labels remain readable as plain code.
          }
        }
      }

      await Promise.all((node.children ?? []).map(visit));
    }

    await visit(tree);
  };
}

export async function renderMarkdown(markdown: string): Promise<string> {
  return (await renderMarkdownDocument(markdown)).html;
}

export interface MarkdownReference {
  href: string;
  label: string;
}

function collectExternalReferences(
  references: MarkdownReference[],
  siteOrigin: string,
) {
  return (tree: HastNode) => {
    const seen = new Set<string>();

    function visit(node: HastNode): void {
      const href = node.tagName === "a" ? node.properties?.href : undefined;

      if (href) {
        try {
          const url = new URL(href, siteOrigin);
          if (
            /^https?:$/.test(url.protocol) &&
            url.origin !== siteOrigin &&
            !seen.has(url.href)
          ) {
            seen.add(url.href);
            references.push({
              href: url.href,
              label: textContent(node).trim() || url.href,
            });
          }
        } catch {
          // Invalid links are already handled by the sanitized renderer.
        }
      }

      node.children?.forEach(visit);
    }

    visit(tree);
  };
}

export async function renderMarkdownDocument(
  markdown: string,
  siteUrl: string | URL = "http://localhost",
): Promise<{ html: string; references: MarkdownReference[] }> {
  const references: MarkdownReference[] = [];
  const siteOrigin = new URL(siteUrl).origin;
  const output = await unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeSanitize, githubStyleSchema)
    .use(() => collectExternalReferences(references, siteOrigin))
    .use(highlightCodeBlocks)
    .use(rehypeStringify)
    .process(markdown);

  return { html: String(output), references };
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
