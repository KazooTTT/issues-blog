# KazooTTT 声控烤箱 — MVP

## Identity

- Title: `KazooTTT 声控烤箱`
- Tagline: `浅尝辄止，技艺不精。`
- Chinese is the default interface and document language; individual articles may be written in English.
- The theme is an original, restrained reading experience. The reference projects inform behavior only, not visual design.

## Content model

- A GitHub Issue created by the repository owner is the authoritative article record.
- An article is published only while it has the `blog:publish` system label.
- Removing `blog:publish` withdraws the article from every public output without deleting it.
- Open and closed Issue states do not affect publication.
- Draft Issues in the public repository are not private.
- Non-`blog:*` labels are multi-select content tags. MVP has no separate category model.
- The first `blog:publish` label event is the publication time. Re-publishing does not change it.
- Title or body edits change the article update time. Comments do not.
- Article permalinks use `/posts/{issue-number}/`.

## Featured content and fixed pages

- `blog:featured` marks homepage featured articles.
- The homepage shows at most five featured articles, newest publication first.
- More than five produces a build warning and displays only the newest five.
- Featured cards have an automatically derived excerpt; regular article lists do not.
- One owner-authored Issue with `blog:about` supplies `/about/`.
- Multiple `blog:about` Issues are a build error.
- About does not appear in article listings, tags, archives, RSS, comments, or Reactions.

## Public pages

- Homepage: identity, featured articles, and recent articles.
- Article page: metadata, sanitized body, tags, Reaction counts, source Issue link, and read-only discussion.
- Tag page: published articles sharing a content tag.
- Archive page: all published articles grouped by year.
- About page.
- Regular article lists contain 20 articles per page at `/`, `/page/2/`, and so on.
- Featured articles are not repeated in the homepage regular list.

## Discussion

- All Issue comments appear chronologically as read-only discussion.
- With more than ten comments, older comments are collapsed and the latest ten remain visible.
- Author comments receive a subtle author marker.
- Each comment links to its GitHub permalink.
- Readers comment or react on GitHub; the blog has no account system or editor.
- Discussion is not article body and is excluded from full-text RSS.

## Rendering and feeds

- Render GitHub Flavored Markdown.
- Allow a sanitized GitHub-style HTML subset such as `details`, `summary`, and `kbd`.
- Remove scripts, inline event handlers, dangerous URLs, iframes, and unsafe embeds.
- Provide a reusable table-of-contents component, disabled by default until evaluated with the finished theme.
- Full-text RSS contains the latest 20 published articles and excludes comments.
- Withdrawing an article removes it from the next feed build.
- Sitemap, canonical URLs, and standard social metadata are part of the static output.
- MVP uses one site-wide branded social sharing image.

## Architecture

- Own implementation; do not fork or depend on the `gitblog` or `isite` generators.
- One repository contains Astro source, Issues, Actions, and Pages configuration.
- Astro and TypeScript generate a static site, primarily with native Astro components.
- GitHub GraphQL is the primary read API, with explicit pagination and runtime response validation.
- Actions use the repository-scoped `GITHUB_TOKEN`, not a long-lived personal token.
- GitHub Actions automatically rebuilds on relevant Issue, label, and comment events.
- A complete successful build atomically deploys to GitHub Pages; failures preserve the previous deployment.
- Initial launch uses the default GitHub Pages address while keeping the canonical site URL configurable.

## Recovery

- An independent `archive` branch stores generated article Markdown plus metadata and discussion JSON.
- The archive is recovery material, never an editing source.
- MVP preserves GitHub-hosted image URLs but does not copy image binaries.

## Explicitly deferred

- Hosted or local draft preview workflow.
- Search.
- Multilingual routes and translation relationships.
- Per-article social image generation.
- Related-article recommendations.
- Friends, projects, and photography sections.
- In-site authentication, commenting, or reactions.
- Automatic activation and placement of the table of contents.
