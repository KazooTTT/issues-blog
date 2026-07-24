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
  author: z
    .object({ login: z.string(), avatarUrl: z.string() })
    .nullable(),
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
  author: z.object({ login: z.string() }).nullable(),
  labels: z.object({
    nodes: z.array(z.object({ name: z.string() })),
    pageInfo: pageInfoSchema,
  }),
  timelineItems: z.object({
    nodes: z.array(
      z.object({
        createdAt: z.string(),
        label: z.object({ name: z.string() }),
      }),
    ),
    pageInfo: pageInfoSchema,
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
          labels(first: 100) {
            nodes { name }
            pageInfo { hasNextPage endCursor }
          }
          timelineItems(first: 100, itemTypes: [LABELED_EVENT]) {
            pageInfo { hasNextPage endCursor }
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

const LABELS_QUERY = `
  query MoreLabels($id: ID!, $after: String!) {
    node(id: $id) {
      ... on Issue {
        labels(first: 100, after: $after) {
          nodes { name }
          pageInfo { hasNextPage endCursor }
        }
      }
    }
  }
`;

const TIMELINE_QUERY = `
  query MoreLabelEvents($id: ID!, $after: String!) {
    node(id: $id) {
      ... on Issue {
        timelineItems(first: 100, after: $after, itemTypes: [LABELED_EVENT]) {
          pageInfo { hasNextPage endCursor }
          nodes {
            ... on LabeledEvent { createdAt label { name } }
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

const labelsResponseSchema = z.object({
  data: z.object({
    node: z.object({
      labels: z.object({
        nodes: z.array(z.object({ name: z.string() })),
        pageInfo: pageInfoSchema,
      }),
    }),
  }),
});

const timelineResponseSchema = z.object({
  data: z.object({
    node: z.object({
      timelineItems: z.object({
        nodes: z.array(
          z.object({
            createdAt: z.string(),
            label: z.object({ name: z.string() }),
          }),
        ),
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
    author: issue.author?.login ?? "[deleted]",
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
      author: comment.author?.login ?? "[deleted]",
      avatarUrl: comment.author?.avatarUrl ?? "",
      createdAt: comment.createdAt,
      updatedAt: comment.updatedAt,
      reactions: mapReactionGroups(comment.reactionGroups),
    })),
  };
}

async function requestGraphQL(
  fetcher: typeof fetch,
  token: string,
  query: string,
  variables: Record<string, unknown>,
): Promise<unknown> {
  const response = await fetcher("https://api.github.com/graphql", {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });

  if (!response.ok) {
    throw new Error(`GitHub GraphQL request failed (${response.status})`);
  }

  const payload: unknown = await response.json();
  const errorPayload = z
    .object({ errors: z.array(z.object({ message: z.string() })) })
    .safeParse(payload);
  if (errorPayload.success && errorPayload.data.errors.length) {
    throw new Error(
      `GitHub GraphQL: ${errorPayload.data.errors
        .map((error) => error.message)
        .join("; ")}`,
    );
  }
  return payload;
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
    const payload = responseSchema.parse(
      await requestGraphQL(fetcher, token, ISSUES_QUERY, {
        owner,
        repo,
        after,
      }),
    );
    if (!payload.data) {
      throw new Error("GitHub GraphQL returned no data");
    }

    const page = payload.data.repository.issues;
    for (const issue of page.nodes) {
      let commentsAfter = issue.comments.pageInfo.hasNextPage
        ? issue.comments.pageInfo.endCursor
        : null;
      while (commentsAfter) {
        const commentsPayload = commentsResponseSchema.parse(
          await requestGraphQL(fetcher, token, COMMENTS_QUERY, {
            id: issue.id,
            after: commentsAfter,
          }),
        );
        const commentsPage = commentsPayload.data.node.comments;
        issue.comments.nodes.push(...commentsPage.nodes);
        commentsAfter = commentsPage.pageInfo.hasNextPage
          ? commentsPage.pageInfo.endCursor
          : null;
      }

      let labelsAfter = issue.labels.pageInfo.hasNextPage
        ? issue.labels.pageInfo.endCursor
        : null;
      while (labelsAfter) {
        const labelsPayload = labelsResponseSchema.parse(
          await requestGraphQL(fetcher, token, LABELS_QUERY, {
            id: issue.id,
            after: labelsAfter,
          }),
        );
        const labelsPage = labelsPayload.data.node.labels;
        issue.labels.nodes.push(...labelsPage.nodes);
        labelsAfter = labelsPage.pageInfo.hasNextPage
          ? labelsPage.pageInfo.endCursor
          : null;
      }

      let timelineAfter = issue.timelineItems.pageInfo.hasNextPage
        ? issue.timelineItems.pageInfo.endCursor
        : null;
      while (timelineAfter) {
        const timelinePayload = timelineResponseSchema.parse(
          await requestGraphQL(fetcher, token, TIMELINE_QUERY, {
            id: issue.id,
            after: timelineAfter,
          }),
        );
        const timelinePage = timelinePayload.data.node.timelineItems;
        issue.timelineItems.nodes.push(...timelinePage.nodes);
        timelineAfter = timelinePage.pageInfo.hasNextPage
          ? timelinePage.pageInfo.endCursor
          : null;
      }
    }
    issues.push(...page.nodes.map(mapIssue));
    after = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (after);

  return issues;
}
