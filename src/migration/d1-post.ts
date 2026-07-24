import { z } from "zod";

export const d1PostSchema = z.object({
  id: z.string(),
  title: z.string(),
  content: z.string(),
  date: z.string(),
  tags_json: z.string(),
});

export type D1Post = z.infer<typeof d1PostSchema>;

const sourcePattern = /<!--\s*issues-blog:source=d1:([^\s]+)\s*-->/;
const publicationPattern =
  /<!--\s*issues-blog:published-at=([^\s]+)\s*-->/;

export function normalizePublicationTime(value: string): string {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  if (!dateOnly && !hasExplicitTimezone) {
    throw new Error(`Publication date must include a timezone: ${value}`);
  }

  const date = new Date(dateOnly ? `${value}T00:00:00.000Z` : value);
  if (Number.isNaN(date.valueOf())) {
    throw new Error(`Invalid publication date: ${value}`);
  }
  return date.toISOString();
}

export function sourceMarker(id: string): string {
  return `<!-- issues-blog:source=d1:${id} -->`;
}

export function issueBody(post: D1Post): string {
  return [
    post.content.trimEnd(),
    "",
    sourceMarker(post.id),
    `<!-- issues-blog:published-at=${normalizePublicationTime(post.date)} -->`,
    "",
  ].join("\n");
}

export function labelsFor(post: D1Post): string[] {
  const tags = z.array(z.string()).parse(JSON.parse(post.tags_json));
  return ["blog:publish", ...new Set(tags.map((tag) => tag.trim()).filter(Boolean))];
}

export function sourceIdsFromBodies(bodies: Array<string | null>): Set<string> {
  return new Set(
    bodies
      .map((body) => body?.match(sourcePattern)?.[1])
      .filter((id): id is string => Boolean(id)),
  );
}

export function importedPublicationTime(body: string): string | undefined {
  if (!sourcePattern.test(body)) return undefined;
  const value = body.match(publicationPattern)?.[1];
  return value ? normalizePublicationTime(value) : undefined;
}
