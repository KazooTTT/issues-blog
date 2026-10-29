/** 体能看板可切换的时间范围（天）。7 天对应短期疲劳窗口。 */
export const FITNESS_PERIODS = [7, 30, 90, 180, 365] as const;

export const DEFAULT_FITNESS_PERIOD = 90;

/** 只接受上面列出的范围，其余（缺省、非法、负数）一律回落到默认值。 */
export function resolveFitnessPeriod(raw: string | null): number {
  const requested = Number(raw ?? DEFAULT_FITNESS_PERIOD);
  return (FITNESS_PERIODS as readonly number[]).includes(requested)
    ? requested
    : DEFAULT_FITNESS_PERIOD;
}
