import { describe, expect, it } from "vitest";

import { archiveDateParts } from "@/utils/presentation";

describe("date presentation", () => {
  it("groups archive dates in the site's Shanghai timezone", () => {
    expect(archiveDateParts("2026-06-30T16:30:00.000Z")).toEqual({
      year: "2026",
      month: "07",
      day: "01",
    });
  });
});
