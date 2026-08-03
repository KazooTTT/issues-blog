import { z } from "zod";

import workoutSnapshot from "./workouts.json";

export const workoutSchema = z.object({
  externalId: z.string().trim().min(1),
  name: z.string().trim().min(1),
  activityDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  startTimeLocal: z.string().trim().min(1).optional(),
  startTimeGmt: z.string().trim().min(1).optional(),
  activityType: z.string().trim().min(1).optional(),
  durationSeconds: z.number().int().nonnegative(),
  movingDurationSeconds: z.number().nonnegative().optional(),
  elapsedDurationSeconds: z.number().nonnegative().optional(),
  distanceMeters: z.number().nonnegative().optional(),
  elevationGainMeters: z.number().nonnegative().optional(),
  elevationLossMeters: z.number().nonnegative().optional(),
  averageSpeedMps: z.number().nonnegative().optional(),
  maxSpeedMps: z.number().nonnegative().optional(),
  averageHeartRateBpm: z.number().nonnegative().optional(),
  maxHeartRateBpm: z.number().nonnegative().optional(),
  caloriesKcal: z.number().int().nonnegative(),
  bmrCaloriesKcal: z.number().nonnegative().optional(),
  averagePowerWatts: z.number().nonnegative().optional(),
  maxPowerWatts: z.number().nonnegative().optional(),
  normalizedPowerWatts: z.number().nonnegative().optional(),
  aerobicTrainingEffect: z.number().nonnegative().optional(),
  anaerobicTrainingEffect: z.number().nonnegative().optional(),
  trainingLoad: z.number().nonnegative().optional(),
  trainingEffectLabel: z.string().trim().min(1).optional(),
  averageRunningCadenceSpm: z.number().nonnegative().optional(),
  maxRunningCadenceSpm: z.number().nonnegative().optional(),
  totalSets: z.number().int().nonnegative().optional(),
  activeSets: z.number().int().nonnegative().optional(),
  totalReps: z.number().int().nonnegative().optional(),
  totalVolume: z.number().nonnegative().optional(),
  trainingDetails: z.record(z.string(), z.unknown()).optional(),
});

export type Workout = z.infer<typeof workoutSchema>;

function workoutStartKey(workout: Workout): string {
  return workout.startTimeLocal ?? `${workout.activityDate} 00:00:00`;
}

export function normalizeWorkouts(input: unknown): Workout[] {
  const payload =
    input && typeof input === "object" && "workouts" in input
      ? (input as { workouts: unknown }).workouts
      : input;
  const parsed = z.array(workoutSchema).parse(payload);
  const unique = new Map(parsed.map((workout) => [workout.externalId, workout]));

  return [...unique.values()].sort(
    (left, right) =>
      right.activityDate.localeCompare(left.activityDate) ||
      workoutStartKey(left).localeCompare(workoutStartKey(right)) ||
      left.externalId.localeCompare(right.externalId),
  );
}

export const workouts = normalizeWorkouts(workoutSnapshot);
