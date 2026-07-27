import { z } from "zod";

import workoutSnapshot from "./workouts.json";

export const workoutSchema = z.object({
  externalId: z.string().trim().min(1),
  name: z.string().trim().min(1),
  activityDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  durationSeconds: z.number().int().nonnegative(),
  caloriesKcal: z.number().int().nonnegative(),
});

export type Workout = z.infer<typeof workoutSchema>;

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
      right.externalId.localeCompare(left.externalId),
  );
}

export const workouts = normalizeWorkouts(workoutSnapshot);
