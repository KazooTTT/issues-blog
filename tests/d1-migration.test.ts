import { describe, expect, it } from "vitest";

import {
  importedPublicationTime,
  issueBody,
  labelsFor,
  normalizePublicationTime,
  sourceIdsFromBodies,
} from "@/migration/d1-post";

const post = {
  id: "post-1",
  title: "标题",
  content: "正文",
  date: "2021-03-04",
  tags_json: '["随笔"," 生活 ","随笔"]',
};

describe("D1 post migration", () => {
  it("plans an Issue with stable source and publication metadata", () => {
    const body = issueBody(post);

    expect(body).toContain("<!-- issues-blog:source=d1:post-1 -->");
    expect(importedPublicationTime(body)).toBe("2021-03-04T00:00:00.000Z");
    expect(labelsFor(post)).toEqual(["blog:publish", "随笔", "生活"]);
  });

  it("detects migrated sources across nullable Issue bodies", () => {
    expect(
      sourceIdsFromBodies([
        null,
        "<!-- issues-blog:source=d1:post-1 -->",
        "<!-- issues-blog:source=d1:post-2 -->",
      ]),
    ).toEqual(new Set(["post-1", "post-2"]));
  });

  it("rejects ambiguous timestamps without a timezone", () => {
    expect(() => normalizePublicationTime("2021-03-04 09:00:00")).toThrow(
      "must include a timezone",
    );
  });

  it("does not honor historical dates without a D1 source marker", () => {
    expect(
      importedPublicationTime(
        "<!-- issues-blog:published-at=2021-03-04T00:00:00.000Z -->",
      ),
    ).toBeUndefined();
  });
});
