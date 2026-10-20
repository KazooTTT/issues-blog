import { describe, expect, it } from "vitest";

import {
  ATL_DAYS,
  buildSeries,
  CTL_DAYS,
  HISTORY_DAYS,
  statusLabel,
  summarise,
} from "@/fitness/series";

const TODAY = "2026-10-20";

describe("buildSeries", () => {
  it("覆盖 730 天历史并在末位落在今天", () => {
    const series = buildSeries([], TODAY);
    expect(series).toHaveLength(HISTORY_DAYS + 1);
    expect(series[0].date).toBe("2024-10-20");
    expect(series.at(-1)?.date).toBe(TODAY);
  });

  it("先记录当日状态再吸收当天负荷", () => {
    // 只有今天一条负荷：今天那行仍是吸收前的 0，曲线从明天才抬起来。
    const series = buildSeries([{ date: TODAY, load: 42 }], TODAY);
    const todayRow = series.at(-1)!;
    expect(todayRow.load).toBe(42);
    expect(todayRow.ctl).toBe(0);
    expect(todayRow.atl).toBe(0);
    expect(todayRow.tsb).toBe(0);
  });

  it("按指数平滑推进，且 42 天比 7 天慢", () => {
    const series = buildSeries([{ date: "2026-10-01", load: 100 }], TODAY);
    const dayAfter = series.find((row) => row.date === "2026-10-02")!;
    expect(dayAfter.ctl).toBeCloseTo(100 / CTL_DAYS, 1);
    expect(dayAfter.atl).toBeCloseTo(100 / ATL_DAYS, 1);
    expect(dayAfter.atl).toBeGreaterThan(dayAfter.ctl);
  });

  it("同一天多条运动累加负荷", () => {
    const series = buildSeries(
      [
        { date: "2026-10-10", load: 20 },
        { date: "2026-10-10", load: 25 },
      ],
      TODAY,
    );
    expect(series.find((row) => row.date === "2026-10-10")?.load).toBe(45);
  });

  it("空数据得到全零序列", () => {
    const series = buildSeries([], TODAY);
    expect(series.every((row) => row.load === 0 && row.ctl === 0 && row.atl === 0)).toBe(true);
  });

  it("忽略负荷为零或被清空的记录", () => {
    const series = buildSeries(
      [
        { date: "2026-10-12", load: 0 },
        { date: "2026-10-13", load: Number.NaN },
      ],
      TODAY,
    );
    const summed = series.reduce((sum, row) => sum + row.load, 0);
    expect(summed).toBe(0);
  });

  it("状态等于体能减疲劳", () => {
    const series = buildSeries([{ date: TODAY, load: 60 }], TODAY);
    for (const row of series.slice(-5)) {
      expect(row.tsb).toBeCloseTo(row.ctl - row.atl, 1);
    }
  });
});

describe("statusLabel", () => {
  it("按状态值分档", () => {
    expect(statusLabel(20, 10, 30).label).toBe("充沛");
    expect(statusLabel(5, 20, 40).label).toBe("良好");
    expect(statusLabel(-10, 30, 40).label).toBe("正常");
    expect(statusLabel(-30, 50, 40).label).toBe("偏疲劳");
    expect(statusLabel(-31, 60, 40).label).toBe("疲劳较高");
  });

  it("体能为零时比值不除零", () => {
    const { ratio, label } = statusLabel(0, 5, 0);
    expect(ratio).toBe(0);
    expect(label).toBe("正常");
  });
});

describe("summarise", () => {
  it("空序列返回 null", () => {
    expect(summarise([])).toBeNull();
  });

  it("汇总最近七天与前七天的负荷", () => {
    const series = buildSeries(
      [
        { date: "2026-10-14", load: 30 },
        { date: "2026-10-18", load: 40 },
        { date: "2026-10-07", load: 50 },
      ],
      TODAY,
    );
    const summary = summarise(series)!;
    expect(summary.weekLoad).toBe(70);
    expect(summary.prevWeekLoad).toBe(50);
    expect(summary.label).toBe("正常");
    expect(typeof summary.ratio).toBe("number");
  });

  it("体能较上周的变化可为负", () => {
    const series = buildSeries([{ date: "2026-10-01", load: 120 }], TODAY);
    const summary = summarise(series)!;
    expect(summary.ctlDelta).toBeLessThanOrEqual(0.1);
  });
});
