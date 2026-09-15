/** Response shapes of the read API (api/app.py). */

export type Maybe<T> = T | null;

/**
 * Why a null missingness_rate is null: nothing collected yet, no way to tell
 * whether collection has started, collected but not computed yet, or not
 * applicable to this response (an error, or a database that could not be read).
 */
export type MissingnessNote = "collection_not_started" | "collection_unknown" | "not_yet_computed" | "not_applicable";

/**
 * Whether collection has started, from published metrics or else the latest walk
 * of the samples chain. The walk runs nightly, so not_started holds as of as_of.
 */
export interface Collection {
  status: "not_started" | "collecting" | "unknown";
  basis: string;
  as_of: Maybe<string>;
}

export interface Envelope {
  as_of: Maybe<string>;
  missingness_rate: Maybe<number>;
  /** Why missingness_rate is null; null when it is not. */
  missingness_note?: Maybe<MissingnessNote>;
  /** Whether collection has started. Null on errors, where nothing was read. */
  collection?: Maybe<Collection>;
  /** Present only when the API serves local fixture data. */
  sample?: true;
  status?: string;
  error?: unknown;
}

export interface Window {
  start: string;
  end: string;
}

/**
 * Publication floors, set by the API. A p95 or anything derived from one needs
 * p95_min_samples pooled calls; a mean, median or quartile needs
 * central_min_samples. Below a floor the API sends null. A pooled statistic is
 * published as a point value with its count and no interval.
 */
export interface Floors {
  p95_min_samples: number;
  central_min_samples: number;
}

export interface Place {
  name: Maybe<string>;
  lat: number;
  lon: number;
}

export interface Ranking {
  n: number;
  raw: Maybe<number>;
  shrunk: Maybe<number>;
  city_mean: Maybe<number>;
  rank: Maybe<number>;
}

export type RankingKey = "tti_tomtom" | "tti_p5" | "congested_share_tomtom" | "congested_share_p5";

/**
 * Peak-hour reliability, pooled over a trailing window. Computed once on the
 * pooled distribution of calls, never per day or per hour.
 */
export interface CorridorLedger {
  window: Window;
  /** The peak hours pooled, e.g. "06:30-10:30, 16:30-21:00 IST". */
  hours: string;
  /** Pooled successful peak-hour calls. */
  n: number;
  /** Null below the central floor. */
  tt_mean_s: Maybe<number>;
  /** Point values pooled over n calls, with no interval. Null below the p95 floor. */
  tt_p95_s: Maybe<number>;
  bti: Maybe<number>;
  /** p95 / TomTom free flow. */
  pti_tomtom: Maybe<number>;
  /** p95 / observed p5 free flow; also null when that reference is unknown. */
  pti_p5: Maybe<number>;
}

/**
 * The road TomTom routes through a corridor's declared points, fetched once when the
 * corridor was verified and simplified for drawing. Absent until then.
 */
export interface CorridorPath {
  /** [lat, lon] pairs, in the direction of travel. */
  points: [number, number][];
  fetched_at: string;
  source: string;
}

export interface CorridorView {
  id: string;
  code: Maybe<string>;
  name: string;
  pair_id: Maybe<string>;
  role: Maybe<"primary" | "alternate">;
  origin: Place;
  destination: Place;
  /** Measured by TomTom, passed through. Never derived from coordinates. */
  length_meters: Maybe<number>;
  free_flow: { tomtom_s: Maybe<number>; p5_s: Maybe<number> };
  missingness_rate: Maybe<number>;
  low_confidence: Maybe<boolean>;
  ledger: Maybe<CorridorLedger>;
  /** A stored road, or null: the map then draws a straight connector and labels it one. */
  path?: Maybe<CorridorPath>;
}

export interface Corridor extends CorridorView {
  rankings: Partial<Record<RankingKey, Ranking>>;
}

export interface CorridorsResponse extends Envelope {
  window: Maybe<Window>;
  low_confidence: Maybe<boolean>;
  method_version: Maybe<string>;
  floors: Maybe<Floors>;
  corridors: Corridor[];
}

type Col<T> = Maybe<T>[];

/** Per corridor, per local day and hour. No percentile-derived column: a cell holds 2-4 calls. */
export interface HourlySeries {
  day: string[];
  hour: number[];
  n_expected: number[];
  n_ok: number[];
  missing_rate: Col<number>;
  low_confidence: boolean[];
  tt_mean_s: Col<number>;
  tti_tomtom: Col<number>;
  tti_p5: Col<number>;
  tti_tomtom_delta_wk: Col<number>;
  tti_p5_delta_wk: Col<number>;
  tt_ratio_own_median: Col<number>;
}

export interface DailySeries {
  day: string[];
  n_expected: number[];
  n_ok: number[];
  missing_rate: Col<number>;
  low_confidence: boolean[];
  tt_mean_s: Col<number>;
  tti_tomtom: Col<number>;
  tti_p5: Col<number>;
}

export interface SeriesResponse extends Envelope {
  corridor_id: string;
  granularity: "hour";
  from?: string;
  to?: string;
  series: Maybe<HourlySeries>;
}

export interface DailySeriesResponse extends Envelope {
  corridor_id: string;
  granularity: "day";
  from?: string;
  to?: string;
  series: Maybe<DailySeries>;
}

/** Every column is indexed like hour. Hours with no schedule slots have n_ok 0 and null values. */
export interface Profile {
  hour: number[];
  n_expected: number[];
  /** Pooled calls for travel time and TTI TomTom at the hour. */
  n_ok: number[];
  missing_rate: Col<number>;
  low_confidence: boolean[];
  /** Pooled calls with an observed-p5 reference: the count for the tti_p5_* floors. */
  n_tti_p5: number[];
  tt_mean_s: Col<number>;
  tt_p50_s: Col<number>;
  tt_p95_s: Col<number>;
  bti: Col<number>;
  tti_tomtom_p25: Col<number>;
  tti_tomtom_p50: Col<number>;
  tti_tomtom_p75: Col<number>;
  tti_tomtom_p95: Col<number>;
  tti_p5_p25: Col<number>;
  tti_p5_p50: Col<number>;
  tti_p5_p75: Col<number>;
  tti_p5_p95: Col<number>;
}

export interface ProfileResponse extends Envelope {
  corridor_id: string;
  /** The profile pooling window. */
  window: Maybe<Window>;
  /** What was pooled, in words. */
  pooling: string;
  floors: Maybe<Floors>;
  profile: Profile;
}

export interface HeatmapResponse extends Envelope {
  corridor_id?: string;
  scope?: "network";
  days: string[];
  window: Maybe<Window> | Record<string, never>;
  /** Medians of pooled calls; null below the central floor. */
  tti_tomtom_p50: Maybe<number>[][];
  tti_p5_p50: Maybe<number>[][];
  /** Pooled successful calls, 7 x 24. */
  n_ok: Maybe<number>[][];
  n_days: Maybe<number>[][];
  missing_rate: Maybe<number>[][];
  low_confidence: Maybe<boolean>[][];
  floors: Maybe<Floors>;
}

export interface CompareSide extends CorridorView {
  profile: {
    hour: number[];
    n_ok: number[];
    tt_p50_s: Col<number>;
    tt_p95_s: Col<number>;
    bti: Col<number>;
    missing_rate: Col<number>;
    low_confidence: boolean[];
  };
}

export interface CompareAdvantage {
  hour: number[];
  primary_n: number[];
  alternate_n: number[];
  primary_tt_p95_s: Col<number>;
  alternate_tt_p95_s: Col<number>;
  /**
   * Primary p95 minus alternate p95, a point estimate: positive means the
   * alternate's p95 is lower. Published only where both sides reach the p95 floor.
   */
  advantage_p95_s: Col<number>;
  low_confidence: boolean[];
}

export interface CompareResponse extends Envelope {
  pair_id: string;
  hour: Maybe<number>;
  /** The profile pooling window. */
  window: Maybe<Window>;
  floors: Maybe<Floors>;
  primary: CompareSide;
  /** Null when the pair declares one corridor. That is a valid answer, not an error. */
  alternate: Maybe<CompareSide>;
  advantage: Maybe<CompareAdvantage>;
}

export interface NetworkStateResponse extends Envelope {
  status: "ok" | "no_data";
  day?: string;
  hour?: number;
  value: Maybe<number>;
  unit?: string;
  state?: Maybe<"worse" | "normal" | "better">;
  n_corridors?: number;
  low_confidence?: boolean;
  tti?: { tomtom_p50: Maybe<number>; p5_p50: Maybe<number> };
}

export interface Intervention {
  id: string;
  corridor_id: string;
  effective_at: string;
  description: string;
}

export interface InterventionsResponse extends Envelope {
  interventions: (Intervention & { audit_status: Maybe<string> })[];
}

export type AuditStatus = "ok" | "insufficient_pre" | "post_pending" | "post_partial" | "insufficient_post" | "no_controls" | "too_few_donors" | "too_few_placebos";

/**
 * A synthetic-control audit of one intervention on pooled buffer time index.
 * Periods are whole blocks of block_days; every boundary is recorded by the
 * pipeline, settling included, and the frontend never infers one.
 */
export interface Audit {
  status: AuditStatus;
  effective_day: string;
  settle_days: number;
  /** Recorded when the intervention is declared; always present. */
  pre_start: string;
  pre_end: string;
  /**
   * The excluded settling period as recorded. Where either is null or absent the
   * view derives it from pre_end + 1 .. post_start - 1 and labels that date INFERRED.
   */
  settle_start?: Maybe<string>;
  settle_end?: Maybe<string>;
  post_start: string;
  post_end: string;
  block_days: number;
  pre_blocks: number;
  post_blocks: number;
  post_blocks_complete: number;
  /** Pooled peak-hour calls on the treated corridor in each period. */
  n_pre: number;
  n_post: number;
  /** Donors in the synthetic control after exclusions. */
  n_donors: number;
  /** The fewest usable donors from which the audit publishes a verdict; below it the status is too_few_donors. */
  min_donors?: Maybe<number>;
  /** Each BTI is pooled once over its whole period. treated_pre may be set before status is "ok". */
  treated_pre: Maybe<number>;
  treated_post: Maybe<number>;
  synthetic_pre: Maybe<number>;
  synthetic_post: Maybe<number>;
  /** (treated_post - synthetic_post) - (treated_pre - synthetic_pre), in BTI units. Null until "ok". */
  effect: Maybe<number>;
  pre_rmspe: Maybe<number>;
  post_rmspe: Maybe<number>;
  /** Post RMSPE ÷ in-sample pre RMSPE. Describes fit; it is not the tested statistic. */
  rmspe_ratio: Maybe<number>;
  /** Pre RMSPE with each pre block predicted by weights fitted on the others. */
  cv_pre_rmspe?: Maybe<number>;
  /** pre_rmspe / cv_pre_rmspe. */
  overfit_ratio?: Maybe<number>;
  /** True when the in-sample pre fit is much tighter than the held-out one: the weights may fit noise. */
  pre_fit_overfit?: Maybe<boolean>;
  /** Donors with a nonzero weight. */
  n_active_donors?: Maybe<number>;
  /**
   * |effect| ÷ cv_pre_rmspe: the statistic the placebo test ranks. Null when the
   * held-out pre error is zero or missing, and placebo_rank is then null too.
   */
  std_effect?: Maybe<number>;
  /** Placebo runs with a standardised effect. */
  /** Ranked placebos: runs whose standardised effect could be computed. Compare with n_donors; 0 when none was run. */
  n_placebos: number;
  /** (1 + placebos with a standardised effect at least as large) / (1 + placebos). */
  placebo_p_value: Maybe<number>;
  placebo_extreme: boolean;
  /** Plain sentences written by the pipeline, ending with the chance expectation when the floor is at most alpha. Shown verbatim. */
  placebo_verdict: Maybe<string>;
  /** Treated rank by std_effect among treated + placebos; 1 is largest, ties count against the treated corridor. Null when std_effect is null. */
  placebo_rank?: Maybe<number>;
  /** The smallest attainable p: 1 / (n_placebos + 1). */
  placebo_p_floor?: Maybe<number>;
  /** Donors dropped for a pre block below the floor, and how they differ from the donors kept. */
  n_excluded_incomplete_pre?: Maybe<number>;
  included_pre_missing_rate?: Maybe<number>;
  excluded_pre_missing_rate?: Maybe<number>;
  included_pre_bti?: Maybe<number>;
  excluded_pre_bti?: Maybe<number>;
  /** Range of the effect across completeness-threshold variants. */
  sensitivity_min_effect?: Maybe<number>;
  sensitivity_max_effect?: Maybe<number>;
  /** True when a variant's effect has the opposite sign, or its placebo verdict (p <= alpha) differs from the headline's. */
  sensitivity_material?: Maybe<boolean>;
  /** Cross-check: the equal-weight mean of the same donors over the same periods. */
  equal_control_pre: Maybe<number>;
  equal_control_post: Maybe<number>;
  equal_effect: Maybe<number>;
  /** effect - equal_effect. */
  estimator_gap: Maybe<number>;
  /** True only when effect and equal_effect have opposite signs. */
  estimators_disagree: Maybe<boolean>;
  /** The placebo test's threshold: the effect is extreme when placebo_p_value <= alpha. */
  alpha: number;
  low_confidence: boolean;
  method_version: string;
}

/** Why a corridor is not in the donor pool. */
export type DonorExclusion = "treated" | "under_works" | "same_pair" | "incomplete_pre" | "insufficient_post";

export interface AuditDonor {
  corridor_id: string;
  code: Maybe<string>;
  included: boolean;
  /** Non-negative, summing to one over included donors. Null when excluded. */
  weight: Maybe<number>;
  exclusion: Maybe<DonorExclusion>;
  n_pre: Maybe<number>;
  n_post: Maybe<number>;
  pre_bti: Maybe<number>;
  post_bti: Maybe<number>;
  /** Mean pre-period missing rate. */
  pre_missing_rate?: Maybe<number>;
  /** Pre blocks below the floor. */
  short_pre_blocks?: Maybe<number>;
  /** Pooled peak-hour calls in the donor's thinnest pre block. */
  min_pre_block_n?: Maybe<number>;
}

export type SensitivityVariant = "base" | "strict_125" | "strict_150" | "relaxed_one_block";

/** The audit rerun at another completeness threshold for donor pre blocks. */
export interface AuditSensitivity {
  variant: SensitivityVariant | string;
  block_floor: Maybe<number>;
  max_short_blocks: Maybe<number>;
  status: "ok" | "no_controls" | "too_few_donors" | "too_few_placebos" | "too_few_blocks" | string;
  n_donors: Maybe<number>;
  n_fit_blocks: Maybe<number>;
  effect: Maybe<number>;
  equal_effect: Maybe<number>;
  placebo_rank: Maybe<number>;
  n_placebos: Maybe<number>;
  placebo_p_value: Maybe<number>;
  /** The smallest attainable p for this variant: 1 / (n_placebos + 1). */
  placebo_p_floor: Maybe<number>;
}

export interface AuditPlacebo {
  corridor_id: string;
  effect: Maybe<number>;
  pre_rmspe: Maybe<number>;
  cv_pre_rmspe?: Maybe<number>;
  /** |effect| ÷ cv_pre_rmspe for this run; null is unranked. */
  std_effect?: Maybe<number>;
  post_rmspe: Maybe<number>;
  /** Describes fit; not the tested statistic. */
  rmspe_ratio: Maybe<number>;
  poor_pre_fit: boolean;
  weights: Record<string, number>;
}

/** Columnar: every key is an array indexed by block position. */
export interface AuditBlocks {
  block: number[];
  block_start: string[];
  block_end: string[];
  complete: boolean[];
  n_treated: Col<number>;
  treated_bti: Col<number>;
  synthetic_bti: Col<number>;
  gap: Col<number>;
}

export interface AuditResponse extends Envelope {
  intervention: Intervention;
  corridor: { id: string; code: Maybe<string>; name: string };
  metric: "bti";
  floors: Maybe<Floors>;
  audit: Maybe<Audit>;
  donors: AuditDonor[];
  placebos: AuditPlacebo[];
  blocks: { pre: AuditBlocks; post: AuditBlocks };
  sensitivity?: AuditSensitivity[];
}

export interface ChainVerification {
  verified_at: string;
  ok: boolean;
  rows_checked: number;
  first_seq: Maybe<number>;
  head_seq: Maybe<number>;
  head_row_hash: Maybe<string>;
  breaks: number;
  first_break_seq: Maybe<number>;
  first_break_problem: Maybe<string>;
}

export interface VerifyResponse extends Envelope {
  status: "ok" | "broken" | "never_verified";
  verification: Maybe<ChainVerification>;
  chains: { samples: Maybe<ChainVerification>; failed_samples: Maybe<ChainVerification> };
  method: string;
  reproduce: string;
}

export interface HealthResponse extends Envelope {
  status: "ok" | "degraded";
  api: "up";
  database: "reachable" | "unreachable";
  data?: "present" | "none";
}
