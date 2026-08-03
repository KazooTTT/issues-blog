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

  it("sorts dates newest first and same-day workouts chronologically", () => {
    const workouts = normalizeWorkouts([
      {
        externalId: "100",
        name: "晚间训练",
        activityDate: "2026-07-02",
        startTimeLocal: "2026-07-02 20:00:00",
        durationSeconds: 600,
        caloriesKcal: 80,
      },
      {
        externalId: "200",
        name: "早间训练",
        activityDate: "2026-07-02",
        startTimeLocal: "2026-07-02 08:00:00",
        durationSeconds: 600,
        caloriesKcal: 80,
      },
    ]);

    expect(workouts.map((workout) => workout.externalId)).toEqual(["200", "100"]);
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

  it("preserves optional Garmin summaries and training details", () => {
    const [workout] = normalizeWorkouts([
      {
        externalId: "3",
        name: "力量训练",
        activityDate: "2026-07-03",
        startTimeLocal: "2026-07-03 18:30:00",
        durationSeconds: 1800,
        caloriesKcal: 280,
        averageHeartRateBpm: 132,
        totalSets: 12,
        trainingDetails: {
          heartRateZones: {
            zones: [{ zoneNumber: 3, secsInZone: 720 }],
          },
        },
      },
    ]);

    expect(workout?.averageHeartRateBpm).toBe(132);
    expect(workout?.totalSets).toBe(12);
    expect(workout?.trainingDetails).toEqual({
      heartRateZones: {
        zones: [{ zoneNumber: 3, secsInZone: 720 }],
      },
    });
  });
});
