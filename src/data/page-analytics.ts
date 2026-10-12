import { createSign } from "node:crypto";
import { z } from "zod";

export interface PageAnalytics {
  generatedAt: string;
  throughDate: string;
  pages: Record<string, { views: number; users: number }>;
}

const credentialsSchema = z.object({
  client_email: z.email(),
  private_key: z.string().min(1),
});
const countSchema = z.string().regex(/^\d+$/).transform(Number).pipe(z.number().int().nonnegative());
const reportSchema = z.object({
  rowCount: z.number().int().nonnegative().optional(),
  metadata: z.object({ timeZone: z.string() }).optional(),
  rows: z.array(z.object({
    dimensionValues: z.tuple([z.object({ value: z.string() })]),
    metricValues: z.tuple([z.object({ value: countSchema }), z.object({ value: countSchema })]),
  })).default([]),
});

/** Server-only: credentials and access tokens never enter the generated pages. */
export async function loadPageAnalytics(
  env: Record<string, string | undefined> = process.env,
  request: typeof fetch = fetch,
): Promise<PageAnalytics | undefined> {
  if (!env.GA4_SERVICE_ACCOUNT_JSON || !env.GA4_PROPERTY_ID) return undefined;
  try {
    if (!/^\d+$/.test(env.GA4_PROPERTY_ID)) throw new Error("Invalid property ID");
    const credentials = credentialsSchema.parse(JSON.parse(env.GA4_SERVICE_ACCOUNT_JSON));
    const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString("base64url");
    const now = Math.floor(Date.now() / 1000);
    const payload = `${encode({ alg: "RS256", typ: "JWT" })}.${encode({
      iss: credentials.client_email,
      scope: "https://www.googleapis.com/auth/analytics.readonly",
      aud: "https://oauth2.googleapis.com/token",
      iat: now,
      exp: now + 3600,
    })}`;
    const signer = createSign("RSA-SHA256");
    signer.update(payload);
    const assertion = `${payload}.${signer.sign(credentials.private_key, "base64url")}`;
    const auth = await request("https://oauth2.googleapis.com/token", {
      method: "POST",
      signal: AbortSignal.timeout(15_000),
      body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }),
    });
    if (!auth.ok) throw new Error("Authentication failed");
    const { access_token: token } = z.object({ access_token: z.string().min(1) }).parse(await auth.json());
    const pages: PageAnalytics["pages"] = {};
    let timeZone = "UTC";
    let offset = 0;
    const limit = 10_000;
    while (true) {
      const response = await request(`https://analyticsdata.googleapis.com/v1beta/properties/${env.GA4_PROPERTY_ID}:runReport`, {
        method: "POST",
        signal: AbortSignal.timeout(20_000),
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          dateRanges: [{ startDate: "30daysAgo", endDate: "yesterday" }],
          dimensions: [{ name: "pagePath" }],
          metrics: [{ name: "screenPageViews" }, { name: "totalUsers" }],
          dimensionFilter: { filter: { fieldName: "hostName", stringFilter: {
            matchType: "EXACT",
            value: new URL(env.SITE_URL ?? "https://kazoottt.github.io/issues-blog").hostname,
          } } },
          orderBys: [{ dimension: { dimensionName: "pagePath" } }],
          limit,
          offset,
        }),
      });
      if (!response.ok) throw new Error("Report request failed");
      const report = reportSchema.parse(await response.json());
      timeZone = report.metadata?.timeZone ?? timeZone;
      for (const row of report.rows) {
        pages[row.dimensionValues[0].value] = {
          views: row.metricValues[0].value,
          users: row.metricValues[1].value,
        };
      }
      offset += report.rows.length;
      if (offset >= (report.rowCount ?? offset) || report.rows.length === 0) break;
      if (offset >= 100_000) throw new Error("Report exceeds supported page count");
    }
    const dateParts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
      timeZone, year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date()).map(({ type, value }) => [type, value]));
    const yesterday = new Date(`${dateParts.year}-${dateParts.month}-${dateParts.day}T00:00:00Z`);
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    return { generatedAt: new Date().toISOString(), throughDate: yesterday.toISOString().slice(0, 10), pages };
  } catch {
    // Avoid logging API payloads or exceptions that might contain credentials.
    console.warn("[analytics] GA4 unavailable; page statistics omitted from this build.");
    return undefined;
  }
}

let analyticsPromise: Promise<PageAnalytics | undefined> | undefined;
export function getPageAnalytics(): Promise<PageAnalytics | undefined> {
  analyticsPromise ??= loadPageAnalytics();
  return analyticsPromise;
}

export function statisticsForPath(analytics: PageAnalytics, path: string) {
  // Do not add users across URL aliases: the same visitor may occur in both.
  return analytics.pages[path] ?? analytics.pages[path.replace(/\/$/, "")] ?? { views: 0, users: 0 };
}
