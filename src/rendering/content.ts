import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import rehypeShiki from "@shikijs/rehype";
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

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: {
    className?: string[];
    dataLanguage?: string;
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

function prepareMermaidDiagrams() {
  return (tree: HastNode) => {
    function visit(node: HastNode): void {
      if (
        node.tagName === "pre" &&
        node.children?.length === 1 &&
        node.children[0].tagName === "code" &&
        node.children[0].properties?.className?.includes("language-mermaid")
      ) {
        const source = textContent(node.children[0]);
        node.tagName = "div";
        node.properties = { className: ["mermaid-diagram"] };
        node.children = [{ type: "text", value: source }];
        return;
      }

      node.children?.forEach(visit);
    }

    visit(tree);
  };
}

const languageLabels: Record<string, string> = {
  bash: "Shell",
  css: "CSS",
  html: "HTML",
  js: "JavaScript",
  javascript: "JavaScript",
  json: "JSON",
  jsx: "JSX",
  markdown: "Markdown",
  md: "Markdown",
  sh: "Shell",
  shell: "Shell",
  ts: "TypeScript",
  tsx: "TSX",
  yaml: "YAML",
  yml: "YAML",
};

function labelCodeLanguages() {
  return (tree: HastNode) => {
    function visit(node: HastNode): void {
      if (node.tagName === "pre") {
        const code = node.children?.find((child) => child.tagName === "code");
        const languageClass = code?.properties?.className?.find((className) =>
          className.startsWith("language-"),
        );
        const language = languageClass?.slice("language-".length);

        if (language) {
          node.properties ??= {};
          node.properties.dataLanguage = languageLabels[language] ?? language;
        }
      }

      node.children?.forEach(visit);
    }

    visit(tree);
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
    .use(prepareMermaidDiagrams)
    .use(rehypeShiki, {
      addLanguageClass: true,
      lazy: true,
      onError() {
        // Unknown language labels remain readable as plain code blocks.
      },
      theme: "github-dark-default",
      transformers: [
        {
          name: "issues-blog:code-language-label",
          pre(node) {
            const language = String(this.options.lang);
            node.properties.dataLanguage =
              languageLabels[language] ?? language;
          },
        },
      ],
    })
    .use(labelCodeLanguages)
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
