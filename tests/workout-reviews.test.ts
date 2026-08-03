import { describe, expect, it } from "vitest";

import { classifyIssues } from "@/domain/content-policy";
import type { SourceIssue } from "@/domain/types";
import { indexWorkoutReviews } from "@/domain/workout-reviews";

function issue(overrides: Partial<SourceIssue> = {}): SourceIssue {
  return {
    number: 202,
    title: "运动复盘｜2026-07-31｜舞蹈健身",
    body: [
      "<!-- workout-review:v1 -->",
      "<!-- workout-id: 622983356 -->",
      "",
      "## 这次完成得怎么样",
      "",
      "整体不错。",
    ].join("\n"),
    url: "https://github.com/kazoottt/issues-blog/issues/202",
    author: "kazoottt",
    state: "OPEN",
    createdAt: "2026-08-01T08:00:00Z",
    updatedAt: "2026-08-02T08:00:00Z",
    labels: ["workout:review"],
    labelEvents: [],
    reactions: [],
    comments: [],
    ...overrides,
  };
}

describe("workout review publication policy", () => {
  it("classifies an owner-authored workout review without publishing it as an article", () => {
    const result = classifyIssues([issue()], "kazoottt");

    expect(result.posts).toEqual([]);
    expect(result.workoutReviews).toMatchObject([
      { number: 202, workoutId: "622983356" },
    ]);
  });

  it("ignores reviews written by another GitHub user", () => {
    const result = classifyIssues(
      [issue({ author: "reader" })],
      "kazoottt",
    );

    expect(result.workoutReviews).toEqual([]);
  });

  it("rejects a labeled review without the stable metadata markers", () => {
    expect(() =>
      classifyIssues([issue({ body: "只有正文" })], "kazoottt"),
    ).toThrow("missing <!-- workout-review:v1 -->");

    expect(() =>
      classifyIssues(
        [issue({ body: "<!-- workout-review:v1 -->" })],
        "kazoottt",
      ),
    ).toThrow("missing <!-- workout-id: ... -->");
  });

  it("rejects multiple reviews for the same workout", () => {
    expect(() =>
      classifyIssues(
        [issue(), issue({ number: 203, url: "https://example.com/203" })],
        "kazoottt",
      ),
    ).toThrow("Issues #202 and #203");
  });

  it("indexes reviews by workout ID and rejects unknown workout references", () => {
    const { workoutReviews } = classifyIssues([issue()], "kazoottt");

    expect(
      indexWorkoutReviews(workoutReviews, ["622983356"]).get("622983356")
        ?.number,
    ).toBe(202);
    expect(() => indexWorkoutReviews(workoutReviews, ["another-id"])).toThrow(
      "references unknown workout 622983356",
    );
  });
});
