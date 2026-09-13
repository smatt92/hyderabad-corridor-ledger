/** Response shapes of the read API (api/app.py). */

export type Maybe<T> = T | null;

export interface Envelope {
  as_of: Maybe<string>;
  missingness_rate: Maybe<number>;
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
 * central_min_samples. Below a floor the API sends null.
 */
export interface Floors {
  p95_min_samples: number;
  central_min_samples: number;
  bootstrap_resamples: number;
}

/** A pooled estimate with its bootstrap interval. value is null below the floor. */
export interface Interval {
  value: Maybe<number>;
  ci_low: Maybe<number>;
  ci_high: Maybe<number>;
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
  tt_p95_s: Interval;
  bti: Interval;
  /** p95 / TomTom free flow. */
  pti_tomtom: Interval;
  /** p95 / observed p5 free flow; null when that reference is unknown. */
  pti_p5: Interval;
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
  tt_p95_ci_low: Col<number>;
  tt_p95_ci_high: Col<number>;
  bti: Col<number>;
  bti_ci_low: Col<number>;
  bti_ci_high: Col<number>;
  tti_tomtom_p25: Col<number>;
  tti_tomtom_p50: Col<number>;
  tti_tomtom_p75: Col<number>;
  tti_tomtom_p95: Col<number>;
  tti_tomtom_p95_ci_low: Col<number>;
  tti_tomtom_p95_ci_high: Col<number>;
  tti_p5_p25: Col<number>;
  tti_p5_p50: Col<number>;
  tti_p5_p75: Col<number>;
  tti_p5_p95: Col<number>;
  tti_p5_p95_ci_low: Col<number>;
  tti_p5_p95_ci_high: Col<number>;
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
    tt_p95_ci_low: Col<number>;
    tt_p95_ci_high: Col<number>;
    bti: Col<number>;
    bti_ci_low: Col<number>;
    bti_ci_high: Col<number>;
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
  /** Primary p95 minus alternate p95; positive favours the alternate. */
  advantage_p95_s: Col<number>;
  advantage_ci_low: Col<number>;
  advantage_ci_high: Col<number>;
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

export type AuditStatus = "ok" | "insufficient_pre" | "post_pending" | "insufficient_post" | "no_controls";

export interface Audit {
  status: AuditStatus;
  effective_day: string;
  settle_days: number;
  /** Fixed when the intervention is declared; always present. */
  pre_start: string;
  pre_end: string;
  post_start: string;
  post_end: string;
  /** Pooled peak-hour calls on the treated corridor in each period. */
  n_pre: number;
  n_post: number;
  n_controls: number;
  treated_pre: Maybe<number>;
  treated_post: Maybe<number>;
  /** Equal-weight mean of the untreated corridors' pooled BTIs. */
  control_pre: Maybe<number>;
  control_post: Maybe<number>;
  /** (treated_post - treated_pre) - (control_post - control_pre), in BTI units. */
  effect: Maybe<number>;
  ci_low: Maybe<number>;
  ci_high: Maybe<number>;
  alpha: number;
  resamples: number;
  weights: Record<string, number>;
  low_confidence: boolean;
  method_version: string;
}

export interface AuditResponse extends Envelope {
  intervention: Intervention;
  corridor: { id: string; code: Maybe<string>; name: string };
  metric: "bti";
  floors: Maybe<Floors>;
  audit: Maybe<Audit>;
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
