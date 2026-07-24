import { siteConfig } from "@/config";
import { classifyIssues } from "@/domain/content-policy";
import type { SiteContent } from "@/domain/types";
import { loadGitHubIssues } from "@/github/load-issues";

import { fixtureIssues } from "./fixture";

let contentPromise: Promise<SiteContent> | undefined;

function repositoryCoordinates(): { owner: string; repo: string } {
  const repository = process.env.GITHUB_REPOSITORY;
  if (!repository) {
    throw new Error("GITHUB_REPOSITORY is required in GitHub content mode");
  }
  const [owner, repo] = repository.split("/");
  if (!owner || !repo) {
    throw new Error("GITHUB_REPOSITORY must use owner/repo format");
  }
  return { owner, repo };
}

async function load(): Promise<SiteContent> {
  const mode = process.env.CONTENT_MODE ?? "fixture";
  if (mode === "fixture") {
    return classifyIssues(fixtureIssues, siteConfig.owner);
  }
  if (mode !== "github") {
    throw new Error(`Unsupported CONTENT_MODE: ${mode}`);
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error("GITHUB_TOKEN is required in GitHub content mode");
  }
  const { owner, repo } = repositoryCoordinates();
  const issues = await loadGitHubIssues({ owner, repo, token });
  return classifyIssues(issues, owner);
}

export function getSiteContent(): Promise<SiteContent> {
  contentPromise ??= load();
  return contentPromise;
}

