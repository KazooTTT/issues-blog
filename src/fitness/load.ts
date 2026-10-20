import { loadRuntimeDb } from "@/data/workout-store";
import { buildSeries, HISTORY_DAYS, type SeriesPoint } from "./series";

/**
 * 体能看板的数据来自 D1 的 activities 表，和 /workouts/ 同一个 binding。
 * 读不到时返回 null，由页面降级展示，绝不回落到仓库里的任何快照文件。
 */
export interface FitnessSnapshot {
  today: string;
  series: SeriesPoint[];
}

function shanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

interface LoadRow {
  date: string;
  load: number | null;
}

export async function loadFitnessSnapshot(): Promise<FitnessSnapshot | null> {
  const today = shanghaiToday();
  const db = await loadRuntimeDb();
  if (!db) return null;

  const start = new Date(`${today}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - HISTORY_DAYS);
  const from = start.toISOString().slice(0, 10);

  try {
    const result = await db
      .prepare(
        `SELECT activity_date AS date, training_load AS load
         FROM activities
         WHERE activity_date >= ? AND activity_date <= ?`,
      )
      .bind(from, today)
      .all<LoadRow>();

    const rows = result.results ?? [];
    const activities = rows
      .filter((row): row is { date: string; load: number } =>
        Boolean(row.date) && Boolean(row.load),
      )
      .map((row) => ({ date: row.date, load: Number(row.load) }));

    return { today, series: buildSeries(activities, today) };
  } catch {
    return null;
  }
}
