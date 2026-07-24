import { z } from "zod";

import type { SourceIssue } from "@/domain/types";

const pageInfoSchema = z.object({
  hasNextPage: z.boolean(),
  endCursor: z.string().nullable(),
});

const reactionGroupSchema = z.object({
  content: z.string(),
  users: z.object({ totalCount: z.number() }),
});

const commentSchema = z.object({
  id: z.string(),
  body: z.string(),
  url: z.string(),
  createdAt: z.string(),
  updatedAt: z.string(),
  author: z.object({ login: z.string(), avatarUrl: z.string() }),
  reactionGroups: z.array(reactionGroupSchema),
});

const issueSchema = z.object({
  id: z.string(),
  number: z.number(),
  title: z.string(),
  body: z.string(),
  url: z.string(),
  state: z.enum(["OPEN", "CLOSED"]),
  createdAt: z.string(),
  updatedAt: z.string(),
  lastEditedAt: z.string().nullable().optional(),
  author: z.object({ login: z.string() }),
  labels: z.object({
    nodes: z.array(z.object({ name: z.string() })),
  }),
  timelineItems: z.object({
    nodes: z.array(
      z.object({
        createdAt: z.string(),
        label: z.object({ name: z.string() }),
      }),
    ),
  }),
  reactionGroups: z.array(reactionGroupSchema),
  comments: z.object({
    nodes: z.array(commentSchema),
    pageInfo: pageInfoSchema,
  }),
});

const responseSchema = z.object({
  data: z
    .object({
      repository: z.object({
        issues: z.object({
          nodes: z.array(issueSchema),
          pageInfo: pageInfoSchema,
        }),
      }),
    })
    .optional(),
  errors: z.array(z.object({ message: z.string() })).optional(),
});

const ISSUES_QUERY = `
  query BlogIssues($owner: String!, $repo: String!, $after: String) {
    repository(owner: $owner, name: $repo) {
      issues(first: 50, after: $after, orderBy: { field: CREATED_AT, direction: DESC }) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id number title body url state createdAt updatedAt lastEditedAt
          author { login }
          labels(first: 100) { nodes { name } }
          timelineItems(first: 100, itemTypes: [LABELED_EVENT]) {
            nodes {
              ... on LabeledEvent { createdAt label { name } }
            }
          }
          reactionGroups { content users { totalCount } }
          comments(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id body url createdAt updatedAt
              author { login avatarUrl }
              reactionGroups { content users { totalCount } }
            }
          }
        }
      }
    }
  }
`;

const COMMENTS_QUERY = `
  query MoreComments($id: ID!, $after: String!) {
    node(id: $id) {
      ... on Issue {
        comments(first: 100, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id body url createdAt updatedAt
            author { login avatarUrl }
            reactionGroups { content users { totalCount } }
          }
        }
      }
    }
  }
`;

const commentsResponseSchema = z.object({
  data: z.object({
    node: z.object({
      comments: z.object({
        nodes: z.array(commentSchema),
        pageInfo: pageInfoSchema,
      }),
    }),
  }),
});

export interface GitHubLoaderOptions {
  owner: string;
  repo: string;
  token: string;
  fetcher?: typeof fetch;
}

function mapReactionGroups(
  groups: z.infer<typeof reactionGroupSchema>[],
) {
  return groups
    .filter((group) => group.users.totalCount > 0)
    .map((group) => ({
      content: group.content,
      count: group.users.totalCount,
    }));
}

function mapIssue(issue: z.infer<typeof issueSchema>): SourceIssue {
  return {
    number: issue.number,
    title: issue.title,
    body: issue.body,
    url: issue.url,
    state: issue.state,
    createdAt: issue.createdAt,
    updatedAt: issue.lastEditedAt ?? issue.createdAt,
    author: issue.author.login,
    labels: issue.labels.nodes.map((label) => label.name),
    labelEvents: issue.timelineItems.nodes.map((event) => ({
      label: event.label.name,
      createdAt: event.createdAt,
    })),
    reactions: mapReactionGroups(issue.reactionGroups),
    comments: issue.comments.nodes.map((comment) => ({
      id: comment.id,
      body: comment.body,
      url: comment.url,
      author: comment.author.login,
      avatarUrl: comment.author.avatarUrl,
      createdAt: comment.createdAt,
      updatedAt: comment.updatedAt,
      reactions: mapReactionGroups(comment.reactionGroups),
    })),
  };
}

export async function loadGitHubIssues({
  owner,
  repo,
  token,
  fetcher = fetch,
}: GitHubLoaderOptions): Promise<SourceIssue[]> {
  const issues: SourceIssue[] = [];
  let after: string | null = null;

  do {
    const response = await fetcher("https://api.github.com/graphql", {
      method: "POST",
      headers: {
        accept: "application/vnd.github+json",
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        query: ISSUES_QUERY,
        variables: { owner, repo, after },
      }),
    });

    if (!response.ok) {
      throw new Error(`GitHub GraphQL request failed (${response.status})`);
    }

    const rawPayload: unknown = await response.json();
    const errorPayload = z
      .object({ errors: z.array(z.object({ message: z.string() })) })
      .safeParse(rawPayload);
    if (errorPayload.success && errorPayload.data.errors.length) {
      throw new Error(
        `GitHub GraphQL: ${errorPayload.data.errors
          .map((error) => error.message)
          .join("; ")}`,
      );
    }
    const payload = responseSchema.parse(rawPayload);
    if (!payload.data) {
      throw new Error("GitHub GraphQL returned no data");
    }

    const page = payload.data.repository.issues;
    for (const issue of page.nodes) {
      let commentsAfter = issue.comments.pageInfo.hasNextPage
        ? issue.comments.pageInfo.endCursor
        : null;
      while (commentsAfter) {
        const commentsResponse = await fetcher(
          "https://api.github.com/graphql",
          {
            method: "POST",
            headers: {
              accept: "application/vnd.github+json",
              authorization: `Bearer ${token}`,
              "content-type": "application/json",
            },
            body: JSON.stringify({
              query: COMMENTS_QUERY,
              variables: { id: issue.id, after: commentsAfter },
            }),
          },
        );
        if (!commentsResponse.ok) {
          throw new Error(
            `GitHub GraphQL request failed (${commentsResponse.status})`,
          );
        }
        const commentsPayload = commentsResponseSchema.parse(
          await commentsResponse.json(),
        );
        const commentsPage = commentsPayload.data.node.comments;
        issue.comments.nodes.push(...commentsPage.nodes);
        commentsAfter = commentsPage.pageInfo.hasNextPage
          ? commentsPage.pageInfo.endCursor
          : null;
      }
    }
    issues.push(...page.nodes.map(mapIssue));
    after = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (after);

  return issues;
}
