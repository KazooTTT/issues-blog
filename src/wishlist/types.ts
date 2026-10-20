export type WishKind = "buy" | "do" | "other";
export type WishStatus = "todo" | "doing" | "done";
export interface Wish {
  id: string;
  title: string;
  description: string;
  kind: WishKind;
  status: WishStatus;
  category: string;
  priority: string;
  budget: string;
  targetDate: string;
  url: string;
}
export interface WishlistData {
  title: string;
  projectUrl: string;
  fetchedAt: string;
  items: Wish[];
}
export function safeGithubUrl(value: string): string {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "github.com"
      ? url.href
      : "";
  } catch {
    return "";
  }
}
export function isWishlistData(value: unknown): value is WishlistData {
  if (!value || typeof value !== "object") return false;
  const data = value as WishlistData;
  return (
    typeof data.title === "string" &&
    typeof data.projectUrl === "string" &&
    Boolean(safeGithubUrl(data.projectUrl)) &&
    typeof data.fetchedAt === "string" &&
    Number.isFinite(Date.parse(data.fetchedAt)) &&
    Array.isArray(data.items) &&
    data.items.every(
      (item) =>
        item &&
        typeof item === "object" &&
        [
          "id",
          "title",
          "description",
          "category",
          "priority",
          "budget",
          "targetDate",
          "url",
        ].every((key) => typeof item[key as keyof Wish] === "string") &&
        ["buy", "do", "other"].includes(item.kind) &&
        ["todo", "doing", "done"].includes(item.status),
    )
  );
}
