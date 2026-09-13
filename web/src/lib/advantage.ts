import { meetsFloor } from "./floors";
import { fmtHour } from "./format";

/** Below this p95 gap (36 s, 0.6 min) two corridors are indistinguishable at an hour. */
export const TIE_SECONDS = 36;

function aboveZero(v: number | null | undefined): boolean {
  return v != null && Number.isFinite(v) && v > 0;
}

/**
 * Contiguous runs of hours where the alternate leads by more than the tie
 * threshold. With ciLow, a lead counts only where its interval is above zero.
 */
export function leadRuns(advantage: (number | null)[], threshold = TIE_SECONDS, ciLow?: readonly (number | null)[]): [number, number][] {
  const runs: [number, number][] = [];
  advantage.forEach((v, hour) => {
    if (v == null || v <= threshold) return;
    if (ciLow && !aboveZero(ciLow[hour])) return;
    const last = runs.at(-1);
    if (last && last[1] === hour - 1) last[1] = hour;
    else runs.push([hour, hour]);
  });
  return runs;
}

/**
 * One sentence on whether the winner changes with the hour. advantage is the
 * published primary p95 minus alternate p95, per hour; positive favours the
 * alternate.
 */
export function advantagePhrase(advantage: (number | null)[], threshold = TIE_SECONDS, ciLow?: readonly (number | null)[]): string {
  const measured = advantage.filter((v) => v != null).length;
  if (measured === 0) return "No hour has published p95 travel times for both corridors yet.";
  const runs = leadRuns(advantage, threshold, ciLow);
  const clearly = ciLow ? ", with an interval above zero," : "";
  if (runs.length === 0) {
    return ciLow
      ? "At no published hour does the declared alternate lead with an interval above zero."
      : "Across the published hours the declared alternate never takes the lead on this pair.";
  }
  const leading = runs.reduce((n, [a, b]) => n + b - a + 1, 0);
  if (leading === 24) return `The declared alternate leads${clearly} at every hour of the day.`;
  const longest = [...runs].sort((x, y) => y[1] - y[0] - (x[1] - x[0]))[0]!;
  const others = runs.length - 1;
  return (
    `The alternate takes the lead${clearly} between ${fmtHour(longest[0])} and ${fmtHour(longest[1] + 1)}` +
    (others > 0 ? ` (and in ${others} shorter window${others > 1 ? "s" : ""} elsewhere in the day).` : ".")
  );
}

/**
 * What the advantage at one hour says.
 *   no_calls: neither corridor has a pooled call at the hour.
 *   insufficient: either corridor is below the p95 floor. Not a tie.
 *   unpublished: both meet the floor but no value was published.
 *   tie: the gap is inside the tie band.
 *   alternate / primary: who leads; uncertain when the interval includes zero.
 */
export type AdvantageKind = "no_calls" | "insufficient" | "unpublished" | "tie" | "alternate" | "primary";

export interface AdvantageReading {
  kind: AdvantageKind;
  /** The published advantage, or null wherever it may not be shown. */
  value: number | null;
  uncertain: boolean;
}

export function readAdvantage(
  value: number | null,
  ciLow: number | null,
  ciHigh: number | null,
  primaryN: number | null,
  alternateN: number | null,
  floor: number,
  threshold = TIE_SECONDS,
): AdvantageReading {
  if (!((primaryN ?? 0) > 0) && !((alternateN ?? 0) > 0)) return { kind: "no_calls", value: null, uncertain: false };
  if (!meetsFloor(primaryN, floor) || !meetsFloor(alternateN, floor)) return { kind: "insufficient", value: null, uncertain: false };
  if (value == null || !Number.isFinite(value)) return { kind: "unpublished", value: null, uncertain: false };
  if (Math.abs(value) < threshold) return { kind: "tie", value, uncertain: false };
  const excludesZero = value > 0 ? aboveZero(ciLow) : ciHigh != null && Number.isFinite(ciHigh) && ciHigh < 0;
  return { kind: value > 0 ? "alternate" : "primary", value, uncertain: !excludesZero };
}

export function byHour<T>(hours: number[], values: (T | null)[]): (T | null)[] {
  const out: (T | null)[] = Array.from({ length: 24 }, () => null);
  hours.forEach((h, i) => {
    if (h >= 0 && h < 24) out[h] = values[i] ?? null;
  });
  return out;
}
