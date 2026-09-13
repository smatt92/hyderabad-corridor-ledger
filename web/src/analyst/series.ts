import type { HourlySeries } from "../api/types";

type NumericKey = {
  [K in keyof HourlySeries]: HourlySeries[K] extends (number | null)[] ? K : never;
}[keyof HourlySeries];

/** O(1) lookups into a corridor's hourly series by local day and hour. */
export class SeriesView {
  private readonly rows = new Map<string, number>();

  constructor(readonly series: HourlySeries) {
    series.day.forEach((day, i) => this.rows.set(`${day}|${series.hour[i]}`, i));
  }

  row(day: string, hour: number): number | undefined {
    return this.rows.get(`${day}|${hour}`);
  }

  value(key: NumericKey, day: string, hour: number): number | null {
    const i = this.row(day, hour);
    return i === undefined ? null : (this.series[key][i] ?? null);
  }

  /** Low confidence when flagged, and when there is no cell at all. */
  lowConfidence(day: string, hour: number): boolean {
    const i = this.row(day, hour);
    return i === undefined ? true : this.series.low_confidence[i] === true;
  }

  coverage(day: string, hour: number): number | null {
    const i = this.row(day, hour);
    if (i === undefined) return null;
    const expected = this.series.n_expected[i] ?? 0;
    return expected > 0 ? (this.series.n_ok[i] ?? 0) / expected : null;
  }

  /** Values at one hour across a list of days; null where nothing was measured. */
  atHour(key: NumericKey, days: string[], hour: number): (number | null)[] {
    return days.map((day) => this.value(key, day, hour));
  }
}
