import { workoutSchema, workouts as snapshotWorkouts, type Workout } from "./workouts";

/**
 * 只读的 D1 binding 最小接口。避免为了几个查询引入 workers-types。
 */
interface D1Statement {
  bind(...values: unknown[]): D1Statement;
  all<T = unknown>(): Promise<{ results?: T[] }>;
}

export interface D1Binding {
  prepare(sql: string): D1Statement;
}

/**
 * Astro v6 起 `Astro.locals.runtime.env` 已被移除，Cloudflare 绑定只能通过
 * `cloudflare:workers` 模块读取。该模块只在 Workers 运行时存在，非 Workers
 * 环境（例如本地 Node 预渲染）下退化为 undefined，让调用方回落到构建快照。
 */
export async function loadRuntimeDb(): Promise<D1Binding | undefined> {
  try {
    const mod = await import("cloudflare:workers");
    const env = (mod as { env?: { DB?: D1Binding } }).env;
    return env?.DB;
  } catch {
    return undefined;
  }
}

interface ActivityRow {
  activity_id: string;
  activity_date: string;
  name: string | null;
  activity_type: string | null;
  start_time_local: string | null;
  duration_seconds: number | null;
  calories_kcal: number | null;
  raw: string | null;
  training_details: string | null;
}

const COLUMNS = `activity_id, activity_date, name, activity_type, start_time_local,
  duration_seconds, calories_kcal, raw, training_details`;

const VALUE_PATHS = {
  startTimeLocal: "startTimeLocal",
  startTimeGmt: "startTimeGMT",
  activityType: "activityType.typeKey",
  movingDurationSeconds: "movingDuration",
  elapsedDurationSeconds: "elapsedDuration",
  distanceMeters: "distance",
  elevationGainMeters: "elevationGain",
  elevationLossMeters: "elevationLoss",
  averageSpeedMps: "averageSpeed",
  maxSpeedMps: "maxSpeed",
  averageHeartRateBpm: "averageHR",
  maxHeartRateBpm: "maxHR",
  bmrCaloriesKcal: "bmrCalories",
  averagePowerWatts: "avgPower",
  maxPowerWatts: "maxPower",
  normalizedPowerWatts: "normPower",
  aerobicTrainingEffect: "aerobicTrainingEffect",
  anaerobicTrainingEffect: "anaerobicTrainingEffect",
  trainingLoad: "activityTrainingLoad",
  trainingEffectLabel: "trainingEffectLabel",
  averageRunningCadenceSpm: "averageRunningCadenceInStepsPerMinute",
  maxRunningCadenceSpm: "maxRunningCadenceInStepsPerMinute",
} as const;

const INTEGER_FIELDS = new Set([
  "totalSets",
  "activeSets",
  "totalReps",
  "movingDurationSeconds",
  "elapsedDurationSeconds",
]);

function parseJson(value: string | null): Record<string, unknown> | undefined {
  if (!value) return undefined;
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
}

function nested(source: Record<string, unknown>, path: string): unknown {
  let current: unknown = source;
  for (const part of path.split(".")) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function nonNegative(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

function rowToWorkout(row: ActivityRow): Workout {
  const raw = parseJson(row.raw) ?? {};
  const details = parseJson(row.training_details);
  const candidate: Record<string, unknown> = {
    externalId: row.activity_id,
    name: (raw.activityName as string | undefined) ?? row.name ?? "运动",
    activityDate: row.activity_date,
    durationSeconds: Math.round(
      nonNegative(raw.duration) ?? nonNegative(row.duration_seconds) ?? 0,
    ),
    caloriesKcal: Math.round(
      nonNegative(raw.calories) ?? nonNegative(row.calories_kcal) ?? 0,
    ),
  };

  for (const [field, path] of Object.entries(VALUE_PATHS)) {
    const value = nested(raw, path);
    const number = nonNegative(value);
    if (number !== undefined) {
      candidate[field] = INTEGER_FIELDS.has(field) ? Math.round(number) : number;
    } else if (typeof value === "string" && value.trim()) {
      candidate[field] = value.trim();
    }
  }
  for (const field of ["totalSets", "activeSets", "totalReps", "totalVolume"]) {
    const number = nonNegative(raw[field]);
    if (number !== undefined) {
      candidate[field] = INTEGER_FIELDS.has(field) ? Math.round(number) : number;
    }
  }
  if (details) candidate.trainingDetails = details;

  return workoutSchema.parse(candidate);
}

const QUERY = `SELECT ${COLUMNS} FROM activities
  ORDER BY activity_date DESC, start_time_local DESC, activity_id DESC`;

/** D1 不可用时回落到构建时的快照，保证页面不会因为数据库故障整页挂掉。 */
export async function loadWorkouts(db?: D1Binding): Promise<Workout[]> {
  if (!db) return snapshotWorkouts;
  try {
    const { results } = await db.prepare(QUERY).all<ActivityRow>();
    if (!results?.length) return snapshotWorkouts;
    return results.map(rowToWorkout);
  } catch {
    return snapshotWorkouts;
  }
}

export interface WorkoutPageData {
  workout: Workout;
  previousWorkout?: Workout;
  nextWorkout?: Workout;
}

/** `workouts` 按时间倒序，因此下标 +1 是更早的一条，-1 是更新的一条。 */
export async function loadWorkoutPage(
  id: string,
  db?: D1Binding,
): Promise<WorkoutPageData | undefined> {
  const all = await loadWorkouts(db);
  const index = all.findIndex((workout) => workout.externalId === id);
  if (index === -1) return undefined;
  return {
    workout: all[index],
    previousWorkout: all[index + 1],
    nextWorkout: all[index - 1],
  };
}
