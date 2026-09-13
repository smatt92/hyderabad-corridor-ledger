import { fmtHour } from "./format";

/** Below this p95 gap (36 s, 0.6 min) two corridors are indistinguishable at an hour. */
export const TIE_SECONDS = 36;

/** Contiguous runs of hours where the alternate leads by more than the tie threshold. */
export function leadRuns(advantage: (number | null)[], threshold = TIE_SECONDS): [number, number][] {
  const runs: [number, number][] = [];
  advantage.forEach((v, hour) => {
    if (v == null || v <= threshold) return;
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
export function advantagePhrase(advantage: (number | null)[], threshold = TIE_SECONDS): string {
  const measured = advantage.filter((v) => v != null).length;
  if (measured === 0) return "No hour has published p95 travel times for both corridors yet.";
  const runs = leadRuns(advantage, threshold);
  if (runs.length === 0) return "Across the published hours the declared alternate never takes the lead on this pair.";
  const leading = runs.reduce((n, [a, b]) => n + b - a + 1, 0);
  if (leading === 24) return "The declared alternate leads at every hour of the day.";
  const longest = [...runs].sort((x, y) => y[1] - y[0] - (x[1] - x[0]))[0]!;
  const others = runs.length - 1;
  return (
    `The alternate takes the lead between ${fmtHour(longest[0])} and ${fmtHour(longest[1] + 1)}` +
    (others > 0 ? ` (and in ${others} shorter window${others > 1 ? "s" : ""} elsewhere in the day).` : ".")
  );
}

export function byHour<T>(hours: number[], values: (T | null)[]): (T | null)[] {
  const out: (T | null)[] = Array.from({ length: 24 }, () => null);
  hours.forEach((h, i) => {
    if (h >= 0 && h < 24) out[h] = values[i] ?? null;
  });
  return out;
}
