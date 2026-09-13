import { meetsFloor } from "./floors";

/** Why the route comparison marks no hour as a reliable lead. Shown beside the hourly advantage. */
export const NO_LEAD_REASON =
  "No hour is marked as a reliable lead, because no valid interval exists: an interval that resamples single calls treats calls from the same day and week as independent, and in simulation it showed a “lead” between two identical routes in 10–20% of hours.";

/**
 * What the advantage at one hour is.
 *   no_calls: neither corridor has a pooled call at the hour.
 *   insufficient: either corridor is below the p95 floor. Not a tie.
 *   unpublished: both meet the floor but no value was published.
 *   published: the signed point advantage. It is not classified as a lead, a
 *     tie or anything else, because no valid interval exists to support that.
 */
export type AdvantageKind = "no_calls" | "insufficient" | "unpublished" | "published";

export interface AdvantageReading {
  kind: AdvantageKind;
  /** The published advantage, or null wherever it may not be shown. */
  value: number | null;
}

export function readAdvantage(value: number | null, primaryN: number | null, alternateN: number | null, floor: number): AdvantageReading {
  if (!((primaryN ?? 0) > 0) && !((alternateN ?? 0) > 0)) return { kind: "no_calls", value: null };
  if (!meetsFloor(primaryN, floor) || !meetsFloor(alternateN, floor)) return { kind: "insufficient", value: null };
  if (value == null || !Number.isFinite(value)) return { kind: "unpublished", value: null };
  return { kind: "published", value };
}

export function byHour<T>(hours: number[], values: (T | null)[]): (T | null)[] {
  const out: (T | null)[] = Array.from({ length: 24 }, () => null);
  hours.forEach((h, i) => {
    if (h >= 0 && h < 24) out[h] = values[i] ?? null;
  });
  return out;
}
