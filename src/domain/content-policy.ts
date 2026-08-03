import type { Post, SiteContent, SourceIssue } from "./types";
import { siteConfig } from "@/config";
import { importedPublicationTime } from "@/migration/d1-post";
import {
  classifyWorkoutReviews,
  WORKOUT_REVIEW_LABEL,
} from "./workout-reviews";

const SYSTEM_LABEL_PREFIX = "blog:";
const PUBLISH_LABEL = "blog:publish";
const FEATURED_LABEL = "blog:featured";
const ABOUT_LABEL = "blog:about";

function publicationTime(issue: SourceIssue): string {
  const importedTime = importedPublicationTime(issue.body);
  if (importedTime) {
    return importedTime;
  }

  const events = issue.labelEvents
    .filter((event) => event.label === PUBLISH_LABEL)
    .map((event) => event.createdAt)
    .sort();

  if (!events[0]) {
    throw new Error(`Issue #${issue.number} has no publication event`);
  }

  return events[0];
}

function toPost(issue: SourceIssue): Post {
  return {
    ...issue,
    publishedAt: publicationTime(issue),
    tags: issue.labels.filter((label) => !label.startsWith(SYSTEM_LABEL_PREFIX)),
    featured: issue.labels.includes(FEATURED_LABEL),
    permalink: `/posts/${issue.number}/`,
  };
}

export function classifyIssues(
  issues: SourceIssue[],
  owner: string,
): SiteContent {
  const ownedIssues = issues.filter((issue) => issue.author === owner);
  const aboutIssues = ownedIssues.filter((issue) =>
    issue.labels.includes(ABOUT_LABEL),
  );

  if (aboutIssues.length > 1) {
    throw new Error("Exactly one blog:about issue is allowed");
  }

  const posts = ownedIssues
    .filter(
      (issue) =>
        issue.labels.includes(PUBLISH_LABEL) &&
        !issue.labels.includes(ABOUT_LABEL) &&
        !issue.labels.includes(WORKOUT_REVIEW_LABEL),
    )
    .map(toPost)
    .sort((left, right) => right.publishedAt.localeCompare(left.publishedAt));

  const featuredCount = posts.filter((post) => post.featured).length;
  const warnings =
    featuredCount > siteConfig.featuredLimit
      ? [
          `${featuredCount} featured posts found; only the newest ${siteConfig.featuredLimit} are shown`,
        ]
      : [];

  return {
    posts,
    workoutReviews: classifyWorkoutReviews(ownedIssues),
    about: aboutIssues[0],
    warnings,
  };
}
