import type { Audit, AuditBlocks, AuditDonor, AuditPlacebo, DonorExclusion } from "../api/types";
import { addDays, fmtCount, fmtDay, fmtNum, fmtSigned, fmtSignedInterval, fmtWindow, parseDay } from "./format";
import { EM_DASH } from "./route";

/**
 * Pure helpers for the intervention audit. Every number they print comes from
 * the audit payload, except the placebo floor of a sensitivity variant, which
 * is 1 / (placebos + 1) by definition. A date is the one the pipeline recorded;
 * the only derived dates are settling boundaries the payload omits, and those
 * are always printed with the word INFERRED. Nothing fills in a missing value.
 */

type Num = number | null | undefined;

function finite(v: Num): number | null {
  return v != null && Number.isFinite(v) ? v : null;
}

function plural(n: Num, one: string, many: string): string {
  return n === 1 ? one : many;
}

/** The confidence level of an interval at the payload's alpha. */
export function confidencePercent(alpha: number): number {
  return Math.round((1 - alpha) * 100);
}

/** A rate in [0, 1] as a whole percentage: "21%". An em dash when absent. */
export function fmtRate(v: Num): string {
  const r = finite(v);
  return r === null ? EM_DASH : `${Math.round(r * 100)}%`;
}

// ---------------------------------------------------------------------------
// Settling period

export const INFERRED = "INFERRED";

export interface SettleDay {
  day: string;
  /** True only when the payload did not record this date. */
  inferred: boolean;
}

export interface Settling {
  start: SettleDay;
  end: SettleDay;
}

/**
 * The settling period as recorded. A boundary the payload omits is derived
 * from the neighbouring period (pre_end + 1 day, post_start - 1 day) and marked
 * inferred; a recorded boundary is never marked. Null when no window results.
 */
export function settlingWindow(a: Audit): Settling | null {
  const start: SettleDay = a.settle_start ? { day: a.settle_start, inferred: false } : { day: addDays(a.pre_end, 1), inferred: true };
  const end: SettleDay = a.settle_end ? { day: a.settle_end, inferred: false } : { day: addDays(a.post_start, -1), inferred: true };
  return start.day <= end.day ? { start, end } : null;
}

/** The settling window, with INFERRED written after each derived date in the same text. */
export function fmtSettling(s: Settling | null): string {
  if (!s) return EM_DASH;
  if (!s.start.inferred && !s.end.inferred) return fmtWindow({ start: s.start.day, end: s.end.day });
  const part = (d: SettleDay) => `${fmtDay(d.day)}${d.inferred ? ` ${INFERRED}` : ""}`;
  return `${part(s.start)}–${part(s.end)}`;
}

// ---------------------------------------------------------------------------
// Periods

/** The periods as stated on the page, settling included. */
export function auditPeriods(a: Audit, floor: number): [string, string][] {
  return [
    ["pre period", `${fmtWindow({ start: a.pre_start, end: a.pre_end })} · ${a.pre_blocks} ${plural(a.pre_blocks, "block", "blocks")} of ${a.block_days} d · n = ${a.n_pre}`],
    ["change date", fmtDay(a.effective_day)],
    ["settling, excluded", `${fmtSettling(settlingWindow(a))} · ${a.settle_days} d`],
    [
      "post period",
      `${fmtWindow({ start: a.post_start, end: a.post_end })} · ${a.post_blocks} ${plural(a.post_blocks, "block", "blocks")} of ${a.block_days} d · ${a.post_blocks_complete} of ${a.post_blocks} complete · n = ${a.n_post}`,
    ],
    ["block floor", `${floor} pooled peak-hour calls per block`],
  ];
}

/** True until every post block has completed. */
export function postPeriodOpen(a: Audit): boolean {
  return a.post_blocks_complete < a.post_blocks;
}

/**
 * Stated wherever a reader could look for a reading of a partial post period.
 * There is deliberately no sequential test: in simulation the block confidence
 * sequence excluded zero on 12–18% of no-effect panels (six pre blocks, 28 post
 * days) against a nominal 5%.
 */
export const NO_SEQUENTIAL_TEST =
  "The audit reports once, after the post period closes. There is no sequential test: the block confidence sequence was removed because it rejected no-effect panels far more often than its nominal 5%.";

// ---------------------------------------------------------------------------
// Blocks

export interface BlockRow {
  period: "pre" | "post";
  block: number | null;
  start: string | null;
  end: string | null;
  complete: boolean;
  n: number | null;
  treated: number | null;
  synthetic: number | null;
  gap: number | null;
}

/** Columnar blocks as rows. A value the payload does not carry stays null. */
export function blockRows(blocks: AuditBlocks | null | undefined, period: "pre" | "post"): BlockRow[] {
  if (!blocks) return [];
  const length = blocks.block?.length ?? 0;
  const at = <T,>(col: readonly (T | null)[] | undefined, i: number): T | null => col?.[i] ?? null;
  return Array.from({ length }, (_, i) => ({
    period,
    block: at(blocks.block, i),
    start: at(blocks.block_start, i),
    end: at(blocks.block_end, i),
    complete: blocks.complete?.[i] === true,
    n: finite(at(blocks.n_treated, i)),
    treated: finite(at(blocks.treated_bti, i)),
    synthetic: finite(at(blocks.synthetic_bti, i)),
    gap: finite(at(blocks.gap, i)),
  }));
}

/** The block with the fewest treated calls. A block with no recorded count counts as thinnest. */
export function thinnestBlock(rows: readonly BlockRow[]): BlockRow | null {
  let best: BlockRow | null = null;
  for (const row of rows) {
    if (best === null) best = row;
    else if (best.n !== null && (row.n === null || row.n < best.n)) best = row;
  }
  return best;
}

/** A day as a position on a linear axis, for drawing only. */
export function dayNumber(day: string): number {
  return parseDay(day).getTime() / 86_400_000;
}

export interface Segment {
  /** Start of the block's first recorded day. */
  x0: number;
  /** End of the block's last recorded day. */
  x1: number;
  value: number;
}

/**
 * One flat segment per block that has a value, spanning the block's recorded
 * days. A block without a value is a gap: nothing is drawn across it and no
 * neighbouring value is carried into it.
 */
export function blockSegments(rows: readonly BlockRow[], pick: (row: BlockRow) => number | null): Segment[] {
  const out: Segment[] = [];
  for (const row of rows) {
    const value = finite(pick(row));
    if (value === null || !row.start || !row.end) continue;
    out.push({ x0: dayNumber(row.start), x1: dayNumber(row.end) + 1, value });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Donors

/** Plain words for why a corridor is not in the donor pool. */
export function exclusionText(exclusion: DonorExclusion, floor: number): string {
  switch (exclusion) {
    case "treated":
      return "Excluded: treated by a declared intervention, so not a control.";
    case "same_pair":
      return "Excluded: on the treated corridor’s own pair. Traffic diverting onto the paired alternate is a consequence of the intervention, so this corridor is contaminated, not a control.";
    case "incomplete_pre":
      return `Excluded: a pre block has fewer than ${floor} pooled peak-hour calls, below the p95 floor.`;
    case "insufficient_post":
      return "Excluded: too few pooled peak-hour calls in the post period, which has closed.";
  }
}

/** A donor row's place in the pool, in plain words. */
export function donorStatusText(donor: AuditDonor, floor: number): string {
  if (donor.included) return "Included";
  return donor.exclusion ? exclusionText(donor.exclusion, floor) : "Excluded: no reason was recorded.";
}

/** A published donor weight; an em dash for an excluded donor or an unpublished weight. */
export function donorWeightText(donor: AuditDonor, digits = 3): string {
  const w = finite(donor.weight);
  return donor.included && w !== null ? w.toFixed(digits) : EM_DASH;
}

const EXCLUSION_ORDER: Record<DonorExclusion, number> = { treated: 0, same_pair: 1, incomplete_pre: 2, insufficient_post: 3 };

/**
 * Every donor row, none dropped: included donors first, heaviest weight first,
 * then excluded corridors grouped by reason, each group by code.
 */
export function orderDonors(donors: readonly AuditDonor[] | null | undefined): AuditDonor[] {
  const label = (d: AuditDonor) => d.code ?? d.corridor_id;
  return [...(donors ?? [])].sort((a, b) => {
    if (a.included !== b.included) return a.included ? -1 : 1;
    if (a.included) {
      const wa = finite(a.weight);
      const wb = finite(b.weight);
      if (wa !== wb) {
        if (wa === null) return 1;
        if (wb === null) return -1;
        return wb - wa;
      }
    } else {
      const ra = a.exclusion ? EXCLUSION_ORDER[a.exclusion] : 4;
      const rb = b.exclusion ? EXCLUSION_ORDER[b.exclusion] : 4;
      if (ra !== rb) return ra - rb;
    }
    return label(a).localeCompare(label(b));
  });
}

/**
 * How the corridors dropped for incomplete pre blocks differ from the donors
 * kept: "Excluded for incomplete pre blocks: 9 corridors, missing 21% of pre
 * calls vs 6% for donors; pre BTI 0.52 vs 0.38."
 */
export function incompletePreComparison(a: Audit): string {
  const n = finite(a.n_excluded_incomplete_pre);
  return (
    `Excluded for incomplete pre blocks: ${n ?? EM_DASH} ${plural(n, "corridor", "corridors")}, ` +
    `missing ${fmtRate(a.excluded_pre_missing_rate)} of pre calls vs ${fmtRate(a.included_pre_missing_rate)} for donors; ` +
    `pre BTI ${fmtNum(a.excluded_pre_bti)} vs ${fmtNum(a.included_pre_bti)}.`
  );
}

/** Why that comparison matters: the dropped corridors are not dropped at random. */
export function selectionBiasText(floor: number): string {
  return (
    `A corridor with any pre block below ${floor} pooled peak-hour calls is dropped from the donor pool. ` +
    "Failed calls cluster at peak hours, so the most congested corridors are the most likely to be dropped, and the donor pool is not a random sample of the network."
  );
}

// ---------------------------------------------------------------------------
// Placebos

/** The smallest attainable permutation p with this many placebos: 1 / (placebos + 1). */
export function placeboFloor(nPlacebos: Num): number | null {
  const n = finite(nPlacebos);
  return n === null ? null : 1 / (n + 1);
}

/**
 * A permutation p-value is never shown bare: "p = 0.08 · rank 2 of 26 · 25
 * placebos, floor 1/26 = 0.038". Rank is among the treated corridor and its
 * placebos, so out of placebos + 1.
 */
export function placeboResolutionText(p: Num, rank: Num, nPlacebos: Num, pFloor: Num): string {
  const n = finite(nPlacebos);
  const r = finite(rank);
  const f = finite(pFloor);
  const of = n === null ? EM_DASH : String(n + 1);
  return `p = ${fmtNum(p, 2)} · rank ${r ?? EM_DASH} of ${of} · ${n ?? EM_DASH} ${plural(n, "placebo", "placebos")}, floor 1/${of} = ${f === null ? EM_DASH : f.toFixed(3)}`;
}

export interface RankedRatio {
  corridor_id: string;
  /** Post/pre RMSPE ratio; null is drawn as a gap. */
  ratio: number | null;
  treated: boolean;
  poorPreFit: boolean;
  /** A placebo whose ratio is at least the treated corridor's: it counts against the treated effect. */
  atLeastTreated: boolean;
  /** 0 is the largest ratio. */
  position: number;
}

/**
 * The treated corridor and every placebo, largest post/pre RMSPE ratio first.
 * A placebo tied with the treated corridor ranks above it, because ties count
 * against the treated corridor. Unpublished ratios come last and keep their row.
 */
export function rankRatios(treated: { corridor_id: string; ratio: number | null }, placebos: readonly AuditPlacebo[] | null | undefined): RankedRatio[] {
  const t = finite(treated.ratio);
  const entries = [
    { corridor_id: treated.corridor_id, ratio: t, treated: true, poorPreFit: false },
    ...(placebos ?? []).map((p) => ({ corridor_id: p.corridor_id, ratio: finite(p.rmspe_ratio), treated: false, poorPreFit: p.poor_pre_fit === true })),
  ];
  entries.sort((a, b) => {
    if (a.ratio === null || b.ratio === null) {
      if (a.ratio !== b.ratio) return a.ratio === null ? 1 : -1;
      // both unpublished: nothing to rank, so the treated row leads the gaps
      if (a.treated !== b.treated) return a.treated ? -1 : 1;
      return a.corridor_id.localeCompare(b.corridor_id);
    }
    if (a.ratio !== b.ratio) return b.ratio - a.ratio;
    if (a.treated !== b.treated) return a.treated ? 1 : -1;
    return a.corridor_id.localeCompare(b.corridor_id);
  });
  return entries.map((e, position) => ({
    ...e,
    atLeastTreated: !e.treated && e.ratio !== null && t !== null && e.ratio >= t,
    position,
  }));
}

// ---------------------------------------------------------------------------
// Statements

export interface Statement<Tone extends string> {
  tone: Tone;
  headline: string;
  detail: string;
}

/** The synthetic control against the equal-weight cross-check, both numbers always stated. */
export function estimatorStatement(a: Audit): Statement<"disagree" | "agree" | "unassessed"> {
  const numbers =
    `Synthetic control: ${fmtSignedInterval(a.effect, a.ci_low, a.ci_high)} BTI. ` +
    `Equal-weight mean of the same donors: ${fmtSignedInterval(a.equal_effect, a.equal_ci_low, a.equal_ci_high)} BTI. ` +
    `Synthetic minus equal-weight: ${fmtSigned(a.estimator_gap)} BTI.`;
  if (a.estimators_disagree === true) {
    return {
      tone: "disagree",
      headline: "The two estimators disagree.",
      detail: `${numbers} The estimate depends on how the donors are weighted, so neither number should be read without the other.`,
    };
  }
  if (a.estimators_disagree === false) {
    return { tone: "agree", headline: "The two estimators agree.", detail: numbers };
  }
  return { tone: "unassessed", headline: "Agreement between the two estimators was not assessed.", detail: numbers };
}

/** Whether the effect survives other completeness thresholds for donor pre blocks. */
export function sensitivityStatement(a: Audit): Statement<"material" | "stable" | "unassessed"> {
  const range =
    `Across the completeness-threshold variants the synthetic-control effect ranges from ${fmtSigned(a.sensitivity_min_effect)} to ${fmtSigned(a.sensitivity_max_effect)} BTI; ` +
    `the headline is ${fmtSignedInterval(a.effect, a.ci_low, a.ci_high)} BTI.`;
  if (a.sensitivity_material === true) {
    return {
      tone: "material",
      headline: "The estimate depends on the completeness threshold.",
      detail: `${range} At least one variant’s effect falls outside the headline interval or has the opposite sign.`,
    };
  }
  if (a.sensitivity_material === false) {
    return {
      tone: "stable",
      headline: "No completeness-threshold variant moves the effect outside the headline interval or flips its sign.",
      detail: range,
    };
  }
  return { tone: "unassessed", headline: "Sensitivity to the completeness threshold was not assessed.", detail: range };
}

/** A sensitivity variant in plain words. */
export function variantText(variant: string): string {
  switch (variant) {
    case "base":
      return "Base: every pre block at the floor";
    case "strict_125":
      return "Strict: every pre block at 1.25× the floor";
    case "strict_150":
      return "Strict: every pre block at 1.5× the floor";
    case "relaxed_one_block":
      return "Relaxed: donors may have one short pre block; weights fit only on blocks every donor has";
    default:
      return variant || EM_DASH;
  }
}

/** A sensitivity variant's outcome in plain words. */
export function sensitivityStatusText(status: string | null | undefined): string {
  switch (status) {
    case "ok":
      return "ok";
    case "no_controls":
      return "no donor qualifies";
    case "too_few_blocks":
      return "too few common pre blocks to fit";
    default:
      return status || EM_DASH;
  }
}

// ---------------------------------------------------------------------------
// Status notices

export interface StatusNotice {
  kicker: string;
  body: string;
}

function thinnestText(rows: readonly BlockRow[], floor: number, which: string): string {
  const thin = thinnestBlock(rows);
  if (!thin) return "";
  const dates = thin.start && thin.end ? `, ${fmtWindow({ start: thin.start, end: thin.end })},` : "";
  return ` Its thinnest ${which} block${dates} holds ${fmtCount(thin.n, floor)}.`;
}

/**
 * Why the headline is not shown, for every status but "ok", with the period
 * dates and counts against the p95 floor. Null for "ok".
 */
export function statusNotice(a: Audit, corridorName: string, floor: number, rows: { pre: readonly BlockRow[]; post: readonly BlockRow[] }): StatusNotice | null {
  const pre = fmtWindow({ start: a.pre_start, end: a.pre_end });
  const post = fmtWindow({ start: a.post_start, end: a.post_end });
  const floorText = `A block’s buffer time index rests on a 95th percentile, so it is used only from ${floor} pooled peak-hour calls.`;
  const fixed = "The blocks were recorded when the intervention was declared and are not widened to reach the floor.";
  switch (a.status) {
    case "ok":
      return null;
    case "insufficient_pre":
      return {
        kicker: "Audit withheld",
        body:
          `${corridorName} does not have enough pooled peak-hour calls in its pre blocks to fit a synthetic control. ` +
          `The pre period runs ${pre}: ${a.pre_blocks} ${plural(a.pre_blocks, "block", "blocks")} of ${a.block_days} days, ${a.n_pre} calls pooled in total.` +
          `${thinnestText(rows.pre, floor, "pre")} ${floorText} ${fixed}`,
      };
    case "insufficient_post":
      return {
        kicker: "Audit withheld",
        body:
          `The post period on ${corridorName} closed on ${fmtDay(a.post_end)} without enough pooled peak-hour calls to compute its buffer time index. ` +
          `The post period runs ${post}: ${a.post_blocks} ${plural(a.post_blocks, "block", "blocks")} of ${a.block_days} days, ${a.n_post} calls pooled in total.` +
          `${thinnestText(rows.post, floor, "post")} ${floorText} ${fixed}`,
      };
    case "post_pending":
      return {
        kicker: "Post period still open",
        body:
          `The change took effect on ${fmtDay(a.effective_day)}. The ${a.settle_days}-day settling period, ${fmtSettling(settlingWindow(a))}, is excluded. ` +
          `The post period runs ${post} in ${a.post_blocks} ${plural(a.post_blocks, "block", "blocks")} of ${a.block_days} days, and ${a.post_blocks_complete} of ${a.post_blocks} have completed, so nothing after the change is published before it closes on ${fmtDay(a.post_end)}. ` +
          NO_SEQUENTIAL_TEST,
      };
    case "post_partial":
      return {
        kicker: "Post period in progress",
        body:
          `${a.post_blocks_complete} of ${a.post_blocks} post blocks have completed (post period ${post}). ` +
          `The headline synthetic-control effect and its equal-weight cross-check stay unpublished until the post period closes on ${fmtDay(a.post_end)}. ` +
          `${NO_SEQUENTIAL_TEST} ` +
          `The gaps between ${corridorName} and its synthetic control in the completed post blocks are descriptive, not a test.`,
      };
    case "no_controls":
      return {
        kicker: "Audit withheld",
        body:
          `No corridor qualifies as a donor, so there is no synthetic control to compare ${corridorName} against, and none is built from thinner data. ` +
          "The treated corridor’s own pair is never a donor: traffic diverting onto the paired alternate is a consequence of the intervention, so that corridor is contaminated, not a control. " +
          `Treated corridors are never donors either, and a donor needs at least ${floor} pooled peak-hour calls in every pre block (${a.pre_blocks} ${plural(a.pre_blocks, "block", "blocks")} of ${a.block_days} days, ${pre}).`,
      };
  }
}
