import { describe, expect, it } from "vitest";

import { normalizeWorkouts } from "@/data/workouts";

describe("workout snapshots", () => {
  it("accepts the sync payload shape, deduplicates, and sorts newest first", () => {
    const workouts = normalizeWorkouts({
      workouts: [
        {
          externalId: "1",
          name: "跑步",
          activityDate: "2026-07-01",
          durationSeconds: 600,
          caloriesKcal: 80,
        },
        {
          externalId: "2",
          name: "步行",
          activityDate: "2026-07-02",
          durationSeconds: 300,
          caloriesKcal: 20,
        },
        {
          externalId: "1",
          name: "跑步（已更新）",
          activityDate: "2026-07-01",
          durationSeconds: 660,
          caloriesKcal: 85,
        },
      ],
    });

    expect(workouts.map((workout) => workout.externalId)).toEqual(["2", "1"]);
    expect(workouts[1]?.name).toBe("跑步（已更新）");
  });

  it("rejects malformed records before they reach the static build", () => {
    expect(() =>
      normalizeWorkouts([
        {
          externalId: "1",
          name: "跑步",
          activityDate: "July 1",
          durationSeconds: -1,
          caloriesKcal: 80,
        },
      ]),
    ).toThrow();
  });
});
