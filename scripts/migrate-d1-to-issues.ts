import { execFileSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

import { z } from "zod";
import {
  d1PostSchema,
  issueBody,
  labelsFor,
  sourceIdsFromBodies,
  type D1Post,
} from "@/migration/d1-post";

const d1ResultSchema = z.array(
  z.object({
    results: z.array(d1PostSchema),
    success: z.literal(true),
  }),
);

const issueSchema = z.object({
  body: z.string().nullable(),
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

function loadPosts(source: string): D1Post[] {
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

function existingSourceIds(repository: string): Set<string> {
  const output = run("gh", [
    "api",
    "--paginate",
    "--slurp",
    `repos/${repository}/issues?state=all&per_page=100`,
  ]);
  const pages = z.array(z.array(issueSchema)).parse(JSON.parse(output));
  return sourceIdsFromBodies(pages.flat().map((issue) => issue.body));
}

function ensureLabels(repository: string, posts: D1Post[]): void {
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
