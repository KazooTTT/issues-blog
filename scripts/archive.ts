import { mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { loadGitHubIssues } from "../src/github/load-issues";

function argument(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function yamlString(value: string): string {
  return JSON.stringify(value);
}

const output = argument("--output");
const repository = process.env.GITHUB_REPOSITORY;
const token = process.env.GITHUB_TOKEN;

if (!output) {
  throw new Error("--output is required");
}
if (!repository || !repository.includes("/")) {
  throw new Error("GITHUB_REPOSITORY must use owner/repo format");
}
if (!token) {
  throw new Error("GITHUB_TOKEN is required");
}

const [owner, repo] = repository.split("/") as [string, string];
const issues = await loadGitHubIssues({ owner, repo, token });

await rm(output, { recursive: true, force: true });
await mkdir(join(output, "articles"), { recursive: true });
await mkdir(join(output, "metadata"), { recursive: true });

for (const issue of issues) {
  const frontmatter = [
    "---",
    `number: ${issue.number}`,
    `title: ${yamlString(issue.title)}`,
    `source: ${yamlString(issue.url)}`,
    `author: ${yamlString(issue.author)}`,
    `createdAt: ${yamlString(issue.createdAt)}`,
    `updatedAt: ${yamlString(issue.updatedAt)}`,
    `labels: ${JSON.stringify(issue.labels)}`,
    "---",
    "",
  ].join("\n");

  await writeFile(
    join(output, "articles", `${issue.number}.md`),
    `${frontmatter}${issue.body}\n`,
    "utf8",
  );
  await writeFile(
    join(output, "metadata", `${issue.number}.json`),
    `${JSON.stringify(issue, null, 2)}\n`,
    "utf8",
  );
}

await writeFile(
  join(output, "README.md"),
  [
    "# Issues Blog Archive",
    "",
    "Generated recovery snapshots. GitHub Issues remain the source of truth.",
    "",
    `Last generated: ${new Date().toISOString()}`,
    `Issue count: ${issues.length}`,
    "",
  ].join("\n"),
  "utf8",
);

