import { execFileSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

import { z } from "zod";

const rowSchema = z.object({
  id: z.string(),
  title: z.string(),
  content: z.string(),
  date: z.string(),
  tags_json: z.string(),
});

const d1ResultSchema = z.array(
  z.object({
    results: z.array(rowSchema),
    success: z.literal(true),
  }),
);

const issueSchema = z.object({
  number: z.number(),
  body: z.string(),
});

interface Options {
  source: string;
  repository: string;
  apply: boolean;
}

function optionValue(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function readOptions(): Options {
  const source = optionValue("--source");
  const repository = optionValue("--repo");
  if (!source || !repository) {
    throw new Error(
      "Usage: pnpm migrate:d1 --source /path/to/kazoottt-blog-v2 --repo owner/repo [--apply]",
    );
  }
  if (!/^[^/]+\/[^/]+$/.test(repository)) {
    throw new Error("--repo must use owner/repo format");
  }

  return {
    source: resolve(source),
    repository,
    apply: process.argv.includes("--apply"),
  };
}

function run(command: string, args: string[], cwd?: string): string {
  return execFileSync(command, args, {
    cwd,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    stdio: ["ignore", "pipe", "inherit"],
  });
}

function loadPosts(source: string): z.infer<typeof rowSchema>[] {
  const query = [
    "SELECT id, title, content,",
    "COALESCE(date, date_created, created_at) AS date, tags_json",
    "FROM posts",
    "WHERE draft = 0 AND hidden = 0 AND lang = 'cn'",
    "ORDER BY date ASC, id ASC",
  ].join(" ");
  const output = run(
    "pnpm",
    [
      "exec",
      "wrangler",
      "d1",
      "execute",
      "blog-pageviews",
      "--remote",
      "--command",
      query,
      "--json",
    ],
    source,
  );

  return d1ResultSchema.parse(JSON.parse(output)).flatMap(
    (result) => result.results,
  );
}

function normalizePublicationTime(value: string): string {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = new Date(dateOnly ? `${value}T00:00:00.000Z` : value);
  if (Number.isNaN(date.valueOf())) {
    throw new Error(`Invalid publication date: ${value}`);
  }
  return date.toISOString();
}

function sourceMarker(id: string): string {
  return `<!-- issues-blog:source=d1:${id} -->`;
}

function issueBody(post: z.infer<typeof rowSchema>): string {
  const content = post.content.trimEnd();
  return [
    content,
    "",
    sourceMarker(post.id),
    `<!-- issues-blog:published-at=${normalizePublicationTime(post.date)} -->`,
    "",
  ].join("\n");
}

function existingSourceIds(repository: string): Set<string> {
  const output = run("gh", [
    "issue",
    "list",
    "--repo",
    repository,
    "--state",
    "all",
    "--limit",
    "1000",
    "--json",
    "number,body",
  ]);
  const issues = z.array(issueSchema).parse(JSON.parse(output));
  const ids = new Set<string>();

  for (const issue of issues) {
    const id = issue.body.match(/<!--\s*issues-blog:source=d1:([^\s]+)\s*-->/)?.[1];
    if (id) ids.add(id);
  }
  return ids;
}

function labelsFor(post: z.infer<typeof rowSchema>): string[] {
  const tags = z.array(z.string()).parse(JSON.parse(post.tags_json));
  return ["blog:publish", ...new Set(tags.map((tag) => tag.trim()).filter(Boolean))];
}

function ensureLabels(repository: string, posts: z.infer<typeof rowSchema>[]): void {
  const labels = new Set(posts.flatMap(labelsFor));
  for (const label of labels) {
    run("gh", [
      "label",
      "create",
      label,
      "--repo",
      repository,
      "--color",
      label === "blog:publish" ? "2da44e" : "d4c5f9",
      "--force",
    ]);
  }
}

async function main(): Promise<void> {
  const options = readOptions();
  const posts = loadPosts(options.source);
  const existingIds = existingSourceIds(options.repository);
  const pending = posts.filter((post) => !existingIds.has(post.id));

  console.log(
    `${posts.length} D1 posts found; ${posts.length - pending.length} already migrated; ${pending.length} pending.`,
  );
  if (!options.apply) {
    console.log("Dry run only. Add --apply to create labels and Issues.");
    return;
  }

  ensureLabels(options.repository, pending);
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "issues-blog-migrate-"));
  try {
    for (const [index, post] of pending.entries()) {
      const bodyPath = join(temporaryDirectory, `${post.id}.md`);
      await writeFile(bodyPath, issueBody(post), "utf8");
      const args = [
        "issue",
        "create",
        "--repo",
        options.repository,
        "--title",
        post.title,
        "--body-file",
        bodyPath,
      ];
      for (const label of labelsFor(post)) {
        args.push("--label", label);
      }
      const url = run("gh", args).trim();
      console.log(`[${index + 1}/${pending.length}] ${url}`);
      await delay(750);
    }
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

await main();
