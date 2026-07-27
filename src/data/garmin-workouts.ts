import { z } from "zod";

import type { Workout } from "./workouts";
import { normalizeWorkouts } from "./workouts";

const garminActivitySchema = z.object({
  activityId: z.union([z.string(), z.number()]),
  activityName: z.string().trim().optional(),
  activityType: z.object({ typeKey: z.string().trim().optional() }).optional(),
  startTimeLocal: z.string().trim(),
  duration: z.coerce.number().nonnegative(),
  calories: z.coerce.number().nonnegative().optional().default(0),
});

const activityTypeNames: Record<string, string> = {
  cardio: "有氧运动",
  dance: "舞蹈健身",
  hiit: "HIIT",
  strength_training: "力量训练",
  treadmill_running: "跑步机",
  walking: "步行",
};

function activityName(activity: z.infer<typeof garminActivitySchema>): string {
  if (activity.activityName) return activity.activityName;

  const typeKey = activity.activityType?.typeKey ?? "";
  return (
    activityTypeNames[typeKey] ??
    (typeKey.replaceAll("_", " ") || "Garmin 活动")
  );
}

export function normalizeGarminActivities(input: unknown): Workout[] {
  const payload =
    input && typeof input === "object" && "activities" in input
      ? (input as { activities: unknown }).activities
      : input && typeof input === "object" && "payload" in input
        ? (input as { payload: unknown }).payload
      : input;
  const activities = z.array(garminActivitySchema).parse(payload);

  return normalizeWorkouts(
    activities.map((activity) => ({
      externalId: String(activity.activityId),
      name: activityName(activity),
      activityDate: activity.startTimeLocal.slice(0, 10),
      durationSeconds: Math.round(activity.duration),
      caloriesKcal: Math.round(activity.calories),
    })),
  );
}

export function mergeWorkouts(
  current: Workout[],
  incoming: Workout[],
): Workout[] {
  return normalizeWorkouts([...current, ...incoming]);
}
