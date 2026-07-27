import { describe, expect, it } from "vitest";

import {
  mergeWorkouts,
  normalizeGarminActivities,
} from "../src/data/garmin-workouts";

describe("Garmin workout synchronization", () => {
  it("normalizes Garmin activities for the static workout snapshot", () => {
    expect(
      normalizeGarminActivities([
        {
          activityId: 101,
          activityName: "Easy Run",
          activityType: { typeKey: "running" },
          startTimeLocal: "2026-07-08 07:30:00",
          duration: 1800.4,
          calories: 359.6,
        },
      ]),
    ).toEqual([
      {
        externalId: "101",
        name: "Easy Run",
        activityDate: "2026-07-08",
        durationSeconds: 1800,
        caloriesKcal: 360,
      },
    ]);
  });

  it("uses a readable activity type when Garmin omits the activity name", () => {
    expect(
      normalizeGarminActivities([
        {
          activityId: "102",
          activityType: { typeKey: "strength_training" },
          startTimeLocal: "2026-07-09 18:00:00",
          duration: 1200,
          calories: 180,
        },
      ])[0]?.name,
    ).toBe("力量训练");
  });

  it("accepts archived Garmin payload wrappers", () => {
    expect(
      normalizeGarminActivities({
        payload: [
          {
            activityId: "103",
            activityName: "舞蹈健身",
            startTimeLocal: "2026-07-10 20:00:00",
            duration: 2400,
            calories: 260,
          },
        ],
      })[0]?.externalId,
    ).toBe("103");
  });

  it("updates matching activities while preserving older history", () => {
    const merged = mergeWorkouts(
      [
        {
          externalId: "100",
          name: "旧活动",
          activityDate: "2026-07-01",
          durationSeconds: 600,
          caloriesKcal: 100,
        },
        {
          externalId: "101",
          name: "Before edit",
          activityDate: "2026-07-08",
          durationSeconds: 1800,
          caloriesKcal: 300,
        },
      ],
      [
        {
          externalId: "101",
          name: "After edit",
          activityDate: "2026-07-08",
          durationSeconds: 1810,
          caloriesKcal: 360,
        },
      ],
    );

    expect(merged).toHaveLength(2);
    expect(merged[0]?.name).toBe("After edit");
    expect(merged[1]?.externalId).toBe("100");
  });
});
