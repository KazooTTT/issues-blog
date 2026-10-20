import { describe, expect, it } from "vitest";

import { CHART_GAP_DAYS, chartGeometry } from "@/fitness/chart";
import type { SeriesPoint } from "@/fitness/series";

function point(date: string, value: number): SeriesPoint {
  return { date, load: value, ctl: value, atl: value / 2, tsb: value / 2 };
}

function blank(date: string): SeriesPoint {
  return { date, load: 0, ctl: 0, atl: 0, tsb: 0 };
}

describe("chartGeometry", () => {
  it("空序列不画线", () => {
    const geometry = chartGeometry([]);
    expect(geometry.hasData).toBe(false);
    expect(geometry.ctlPath).toBe("");
    expect(geometry.firstDate).toBe("");
  });

  it("全零序列（从未有记录）不算数据", () => {
    const geometry = chartGeometry([
      blank("2026-01-01"),
      blank("2026-01-02"),
      blank("2026-01-03"),
    ]);
    expect(geometry.hasData).toBe(false);
    expect(geometry.ctlPath).toBe("");
  });

  it("前段没有记录的日子被裁掉，曲线不写成横线", () => {
    const series = [
      blank("2026-01-01"),
      blank("2026-01-02"),
      point("2026-01-03", 40),
      point("2026-01-04", 30),
    ];
    const geometry = chartGeometry(series);
    expect(geometry.hasData).toBe(true);
    expect(geometry.firstDate).toBe("2026-01-03");
    expect(geometry.pointCount).toBe(2);
    // 曲线从裁掉之后的第一个真实点开始。
    expect(geometry.ctlPath.startsWith("M")).toBe(true);
    expect(geometry.ctlPath.split("M")).toHaveLength(2);
  });

  it("休息日（体能不为零）不算断档", () => {
    const series = [
      point("2026-01-01", 40),
      { date: "2026-01-05", load: 0, ctl: 39, atl: 30, tsb: 9 },
      point("2026-01-08", 20),
    ];
    const geometry = chartGeometry(series);
    expect(geometry.ctlPath.split("M")).toHaveLength(2);
    expect(geometry.pointCount).toBe(3);
  });

  it("超过 30 天空档拆成两段，中间不连线", () => {
    const series = [
      point("2026-01-01", 40),
      point("2026-01-05", 35),
      point("2026-03-20", 50),
      point("2026-03-24", 45),
    ];
    const geometry = chartGeometry(series);
    expect(geometry.ctlPath.split("M")).toHaveLength(3);
    expect(geometry.firstDate).toBe("2026-01-01");
    expect(geometry.lastDate).toBe("2026-03-24");
    expect(CHART_GAP_DAYS).toBe(30);
  });

  it("零线落在画布范围内", () => {
    const geometry = chartGeometry([
      { date: "2026-01-01", load: 10, ctl: 120, atl: 180, tsb: -60 },
      { date: "2026-01-02", load: 10, ctl: 121, atl: 175, tsb: -54 },
    ]);
    expect(geometry.zeroY).toBeGreaterThan(0);
    expect(geometry.zeroY).toBeLessThan(260);
    expect(geometry.hasData).toBe(true);
  });

  it("只有一天记录也能画点", () => {
    const geometry = chartGeometry([point("2026-01-01", 40)]);
    expect(geometry.pointCount).toBe(1);
    expect(geometry.ctlPath).toContain("M");
  });
});
