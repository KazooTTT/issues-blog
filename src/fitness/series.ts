/**
 * 训练负荷模型：CTL（长期体能）、ATL（短期疲劳）、TSB（状态）。
 *
 * 口径移植自 fitness-dashboard 仓库的 sync.py，数值必须与那边一致：
 * 每天先记录「吸收当天负荷之前」的状态，再把当天负荷并入指数平滑。
 */

export const HISTORY_DAYS = 730;
export const CTL_DAYS = 42;
export const ATL_DAYS = 7;

export interface ActivityLoad {
  date: string;
  load: number;
}

export interface SeriesPoint {
  date: string;
  load: number;
  ctl: number;
  atl: number;
  tsb: number;
}

export interface FitnessSummary {
  ctl: number;
  atl: number;
  tsb: number;
  ratio: number;
  label: string;
  advice: string;
  weekLoad: number;
  prevWeekLoad: number;
  ctlDelta: number;
}

/** 与 Python round(x, 1) 对齐的取整。 */
function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function shiftDate(date: string, offsetDays: number): string {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() + offsetDays);
  return value.toISOString().slice(0, 10);
}

export function buildSeries(
  activities: readonly ActivityLoad[],
  today: string,
): SeriesPoint[] {
  const byDay = new Map<string, number>();
  for (const activity of activities) {
    if (!activity.load) continue;
    byDay.set(activity.date, (byDay.get(activity.date) ?? 0) + activity.load);
  }

  const start = shiftDate(today, -HISTORY_DAYS);
  const end = new Date(`${today}T00:00:00Z`);
  let ctl = 0;
  let atl = 0;
  const rows: SeriesPoint[] = [];

  for (
    let cursor = new Date(`${start}T00:00:00Z`);
    cursor <= end;
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  ) {
    const key = cursor.toISOString().slice(0, 10);
    const load = byDay.get(key) ?? 0;
    // 先记录当天开始时的状态，再吸收当天负荷。
    rows.push({
      date: key,
      load: round1(load),
      ctl: round1(ctl),
      atl: round1(atl),
      tsb: round1(ctl - atl),
    });
    ctl += (load - ctl) / CTL_DAYS;
    atl += (load - atl) / ATL_DAYS;
  }

  return rows;
}

export function statusLabel(
  tsb: number,
  atl: number,
  ctl: number,
): { label: string; advice: string; ratio: number } {
  const ratio = ctl ? atl / ctl : 0;
  if (tsb >= 20) {
    return {
      label: "充沛",
      advice: "近期负荷低于长期积累，身体有余量，可以安排强度课。",
      ratio,
    };
  }
  if (tsb >= 5) {
    return {
      label: "良好",
      advice: "负荷与恢复比较平衡，适合正常训练。",
      ratio,
    };
  }
  if (tsb >= -10) {
    return {
      label: "正常",
      advice: "略有疲劳，保持节奏，注意睡眠。",
      ratio,
    };
  }
  if (tsb >= -30) {
    return {
      label: "偏疲劳",
      advice: "短期负荷明显高于体能水平，建议减量或安排恢复日。",
      ratio,
    };
  }
  return {
    label: "疲劳较高",
    advice: "负荷堆积较多，优先恢复，避免再加高强度。",
    ratio,
  };
}

export function summarise(series: readonly SeriesPoint[]): FitnessSummary | null {
  const latest = series.at(-1);
  if (!latest) return null;

  const { label, advice, ratio } = statusLabel(latest.tsb, latest.atl, latest.ctl);
  const weekAgo = series.length >= 8 ? series[series.length - 8] : series[0];
  const weekLoad = series.slice(-7).reduce((sum, row) => sum + row.load, 0);
  const prevWeekLoad =
    series.length >= 14
      ? series.slice(-14, -7).reduce((sum, row) => sum + row.load, 0)
      : 0;

  return {
    ctl: latest.ctl,
    atl: latest.atl,
    tsb: latest.tsb,
    ratio: Math.round(ratio * 100) / 100,
    label,
    advice,
    weekLoad: round1(weekLoad),
    prevWeekLoad: round1(prevWeekLoad),
    ctlDelta: round1(latest.ctl - weekAgo.ctl),
  };
}
