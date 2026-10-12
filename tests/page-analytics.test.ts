import { generateKeyPairSync } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { loadPageAnalytics, statisticsForPath } from "../src/data/page-analytics";

const { privateKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
  publicKeyEncoding: { type: "spki", format: "pem" },
});
const env = {
  GA4_SERVICE_ACCOUNT_JSON: JSON.stringify({ client_email: "reader@example.com", private_key: privateKey }),
  GA4_PROPERTY_ID: "123",
  SITE_URL: "https://example.com/blog",
};
const row = (path: string, views: string, users: string) => ({
  dimensionValues: [{ value: path }], metricValues: [{ value: views }, { value: users }],
});

describe("GA4 page statistics", () => {
  it("does not make requests without configuration", async () => {
    const request = vi.fn();
    expect(await loadPageAnalytics({}, request)).toBeUndefined();
    expect(request).not.toHaveBeenCalled();
  });

  it("reads all report pages and scopes the report to the current host and 30 complete days", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(Response.json({ access_token: "test-token" }))
      .mockResolvedValueOnce(Response.json({ rowCount: 2, metadata: { timeZone: "Asia/Shanghai" }, rows: [row("/blog/posts/1/", "15", "7")] }))
      .mockResolvedValueOnce(Response.json({ rowCount: 2, rows: [row("/blog/posts/2/", "8", "4")] }));
    const analytics = await loadPageAnalytics(env, request);
    expect(analytics?.pages).toEqual({ "/blog/posts/1/": { views: 15, users: 7 }, "/blog/posts/2/": { views: 8, users: 4 } });
    const body = JSON.parse(request.mock.calls[1][1].body);
    expect(body.dateRanges).toEqual([{ startDate: "30daysAgo", endDate: "yesterday" }]);
    expect(body.dimensionFilter.filter).toEqual({ fieldName: "hostName", stringFilter: { matchType: "EXACT", value: "example.com" } });
    expect(JSON.parse(request.mock.calls[2][1].body).offset).toBe(1);
    expect(JSON.stringify(analytics)).not.toContain("test-token");
    expect(JSON.stringify(analytics)).not.toContain("PRIVATE KEY");
    expect(analytics?.throughDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("omits statistics on authentication, report, or malformed data failures", async () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      for (const response of [new Response("denied", { status: 403 }), Response.json({ rows: [row("/posts/1/", "bad", "5")] })]) {
        const request = vi.fn().mockResolvedValueOnce(Response.json({ access_token: "test-token" })).mockResolvedValueOnce(response);
        expect(await loadPageAnalytics(env, request)).toBeUndefined();
      }
      expect(await loadPageAnalytics(env, vi.fn().mockRejectedValue(new Error("secret")))).toBeUndefined();
      expect(warning.mock.calls.flat().join(" ")).not.toContain("secret");
    } finally { warning.mockRestore(); }
  });

  it("matches the deployed base path and never adds UV across URL aliases", () => {
    const analytics = { generatedAt: "", throughDate: "", pages: {
      "/blog/posts/1/": { views: 10, users: 5 },
      "/blog/posts/1": { views: 8, users: 5 },
      "/blog/posts/2": { views: 3, users: 2 },
    } };
    expect(statisticsForPath(analytics, "/blog/posts/1/")).toEqual({ views: 10, users: 5 });
    expect(statisticsForPath(analytics, "/blog/posts/2/")).toEqual({ views: 3, users: 2 });
    expect(statisticsForPath(analytics, "/posts/1/")).toEqual({ views: 0, users: 0 });
  });
});
