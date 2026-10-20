import type { SeriesPoint } from "./series";

/** 图表固定几何参数；服务端渲染和浏览器里切换时间范围共用同一套计算。 */
export const CHART_WIDTH = 760;
export const CHART_HEIGHT = 260;
export const CHART_PAD_X = 8;
export const CHART_PAD_Y = 18;
/** 中间隔了这么久没有记录，就当成两段数据，不要把中间连成一条假线。 */
export const CHART_GAP_DAYS = 30;

export interface ChartGeometry {
  ctlPath: string;
  atlPath: string;
  tsbPath: string;
  zeroY: number;
  firstDate: string;
  lastDate: string;
  pointCount: number;
  hasData: boolean;
}

const round1 = (value: number) => Math.round(value * 10) / 10;

function dayGap(from: string, to: string): number {
  const a = Date.parse(`${from}T00:00:00Z`);
  const b = Date.parse(`${to}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) return 0;
  return Math.round((b - a) / 86_400_000);
}

/** 从未有过记录的日子（负荷、体能、疲劳都是 0）不算数据。 */
function hasData(point: SeriesPoint): boolean {
  return point.load > 0 || point.ctl > 0 || point.atl > 0;
}

export function chartGeometry(
  series: readonly SeriesPoint[],
  width = CHART_WIDTH,
  height = CHART_HEIGHT,
  padX = CHART_PAD_X,
  padY = CHART_PAD_Y,
): ChartGeometry {
  const empty: ChartGeometry = {
    ctlPath: "",
    atlPath: "",
    tsbPath: "",
    zeroY: 0,
    firstDate: "",
    lastDate: "",
    pointCount: 0,
    hasData: false,
  };

  const firstIndex = series.findIndex(hasData);
  if (firstIndex === -1) {
    // 整个窗口都没有记录：不画线，交给页面显示空状态。
    const zeroY = padY + (height - padY * 2) / 2;
    return { ...empty, zeroY: round1(zeroY) };
  }

  const points = series.slice(firstIndex);
  const values = points.flatMap((point) => [point.ctl, point.atl, point.tsb]);
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values, 0);
  const span = maxValue - minValue || 1;

  const x = (index: number) =>
    points.length > 1
      ? padX + (index * (width - padX * 2)) / (points.length - 1)
      : width / 2;
  const y = (value: number) =>
    padY + ((maxValue - value) / span) * (height - padY * 2);

  const line = (pick: (point: SeriesPoint) => number) => {
    const parts: string[] = [];
    points.forEach((point, index) => {
      const previous = points[index - 1];
      const isBreak =
        index === 0 || !previous || dayGap(previous.date, point.date) > CHART_GAP_DAYS;
      parts.push(
        `${isBreak ? "M" : "L"}${round1(x(index))} ${round1(y(pick(point)))}`,
      );
    });
    return parts.join(" ");
  };

  return {
    ctlPath: line((point) => point.ctl),
    atlPath: line((point) => point.atl),
    tsbPath: line((point) => point.tsb),
    zeroY: round1(y(0)),
    firstDate: points[0].date,
    lastDate: points.at(-1)!.date,
    pointCount: points.length,
    hasData: true,
  };
}
