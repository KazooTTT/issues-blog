import { describe, expect, it } from "vitest";

import {
  DEFAULT_FITNESS_PERIOD,
  FITNESS_PERIODS,
  resolveFitnessPeriod,
} from "@/fitness/periods";

describe("resolveFitnessPeriod", () => {
  it("支持 7 天范围", () => {
    expect(FITNESS_PERIODS).toContain(7);
    expect(resolveFitnessPeriod("7")).toBe(7);
  });

  it("保留已有的 30/90/180/365 天范围", () => {
    for (const days of [30, 90, 180, 365]) {
      expect(resolveFitnessPeriod(String(days))).toBe(days);
    }
  });

  it("缺省或非法值回落到默认范围", () => {
    expect(resolveFitnessPeriod(null)).toBe(DEFAULT_FITNESS_PERIOD);
    expect(resolveFitnessPeriod("")).toBe(DEFAULT_FITNESS_PERIOD);
    expect(resolveFitnessPeriod("5")).toBe(DEFAULT_FITNESS_PERIOD);
    expect(resolveFitnessPeriod("abc")).toBe(DEFAULT_FITNESS_PERIOD);
  });
});
