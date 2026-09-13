import type { Floors, Profile, Window } from "../api/types";

/**
 * The API is the authority on publication floors and bootstrap resamples, and
 * every response that publishes a pooled statistic carries them. This fallback
 * is used only when a response carries floors: null, and it is the one place
 * those numbers are written in the frontend.
 */
export const FALLBACK_FLOORS: Readonly<Floors> = {
  p95_min_samples: 200,
  central_min_samples: 30,
  bootstrap_resamples: 2000,
};

export function resolveFloors(floors: Floors | null | undefined): Floors {
  return floors ?? FALLBACK_FLOORS;
}

export function meetsFloor(n: number | null | undefined, floor: number): boolean {
  return n != null && Number.isFinite(n) && n >= floor;
}

/** A value only where its pooled count meets the floor. */
export function gateOne<T>(value: T | null | undefined, n: number | null | undefined, floor: number): T | null {
  return value != null && meetsFloor(n, floor) ? value : null;
}

/**
 * Values only where their pooled count meets the floor, null (a gap) elsewhere.
 * This removes what may not be published; it never fills anything in. Without
 * counts the values pass through as the API sent them.
 */
export function gate<T>(values: readonly (T | null)[], counts: readonly (number | null)[] | undefined, floor: number): (T | null)[] {
  if (!counts) return [...values];
  return values.map((v, i) => gateOne(v, counts[i], floor));
}

export function gateMatrix<T>(matrix: readonly (readonly (T | null)[])[], counts: readonly (readonly (number | null)[])[] | undefined, floor: number): (T | null)[][] {
  if (!counts) return matrix.map((row) => [...row]);
  return matrix.map((row, i) => gate(row, counts[i] ?? row.map(() => null), floor));
}

/**
 * Why a pooled statistic is or is not shown. "insufficient": fewer pooled calls
 * than the floor. "unavailable": enough calls, but nothing published (for
 * example, no observed-p5 reference yet).
 */
export type Publication = "published" | "insufficient" | "unavailable";

export function publication(value: number | null | undefined, n: number | null | undefined, floor: number): Publication {
  if (!meetsFloor(n, floor)) return "insufficient";
  return value == null || !Number.isFinite(value) ? "unavailable" : "published";
}

/** Among hours with scheduled slots, how many fall below the floor. */
export function floorSummary(nExpected: readonly number[], nOk: readonly (number | null)[], floor: number): {
  scheduled: number;
  below: number;
  unscheduled: number;
} {
  let scheduled = 0;
  let below = 0;
  nExpected.forEach((expected, i) => {
    if (!(expected > 0)) return;
    scheduled++;
    if (!meetsFloor(nOk[i], floor)) below++;
  });
  return { scheduled, below, unscheduled: nExpected.length - scheduled };
}

/** The pooling window and hours every item shares, or null when they differ or none has one. */
export function sharedPooling(items: readonly ({ window: Window; hours: string } | null | undefined)[]): { window: Window; hours: string } | null {
  const present = items.filter((x): x is { window: Window; hours: string } => x != null);
  const first = present[0];
  if (!first) return null;
  const same = present.every((x) => x.window.start === first.window.start && x.window.end === first.window.end && x.hours === first.hours);
  return same ? { window: first.window, hours: first.hours } : null;
}

/**
 * A 24-hour profile with every column gated by its own floor and count: p95
 * columns and BTI by the p95 floor, medians and quartiles by the central
 * floor; travel time and TTI TomTom count n_ok, TTI observed p5 counts n_tti_p5.
 */
export function gateProfile(p: Profile, floors: Floors): Profile {
  const c = floors.central_min_samples;
  const q = floors.p95_min_samples;
  const n = p.n_ok;
  const n5 = p.n_tti_p5;
  return {
    ...p,
    tt_mean_s: gate(p.tt_mean_s, n, c),
    tt_p50_s: gate(p.tt_p50_s, n, c),
    tt_p95_s: gate(p.tt_p95_s, n, q),
    tt_p95_ci_low: gate(p.tt_p95_ci_low, n, q),
    tt_p95_ci_high: gate(p.tt_p95_ci_high, n, q),
    bti: gate(p.bti, n, q),
    bti_ci_low: gate(p.bti_ci_low, n, q),
    bti_ci_high: gate(p.bti_ci_high, n, q),
    tti_tomtom_p25: gate(p.tti_tomtom_p25, n, c),
    tti_tomtom_p50: gate(p.tti_tomtom_p50, n, c),
    tti_tomtom_p75: gate(p.tti_tomtom_p75, n, c),
    tti_tomtom_p95: gate(p.tti_tomtom_p95, n, q),
    tti_tomtom_p95_ci_low: gate(p.tti_tomtom_p95_ci_low, n, q),
    tti_tomtom_p95_ci_high: gate(p.tti_tomtom_p95_ci_high, n, q),
    tti_p5_p25: gate(p.tti_p5_p25, n5, c),
    tti_p5_p50: gate(p.tti_p5_p50, n5, c),
    tti_p5_p75: gate(p.tti_p5_p75, n5, c),
    tti_p5_p95: gate(p.tti_p5_p95, n5, q),
    tti_p5_p95_ci_low: gate(p.tti_p5_p95_ci_low, n5, q),
    tti_p5_p95_ci_high: gate(p.tti_p5_p95_ci_high, n5, q),
  };
}
