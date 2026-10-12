const sourceLabels = ["人工写作为主", "AI 写作为主"] as const;

export function writingSource(tags: string[]) {
  const sources = sourceLabels.filter((label) => tags.includes(label));
  return sources.length === 1 ? sources[0] : undefined;
}

export function topicTags(tags: string[]): string[] {
  return tags.filter((tag) => !sourceLabels.some((label) => label === tag));
}
