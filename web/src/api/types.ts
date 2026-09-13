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
}

export interface Corridor extends CorridorView {
  rankings: Record<string, Ranking>;
}

export interface CorridorsResponse extends Envelope {
  window: Maybe<Window>;
  low_confidence: Maybe<boolean>;
  method_version: Maybe<string>;
  corridors: Corridor[];
}

type Col<T> = Maybe<T>[];

export interface HourlySeries {
  day: string[];
  hour: number[];
  n_expected: number[];
  n_ok: number[];
  missing_rate: Col<number>;
  low_confidence: boolean[];
  tt_mean_s: Col<number>;
  tt_p95_s: Col<number>;
  tti_tomtom: Col<number>;
  tti_p5: Col<number>;
  bti: Col<number>;
  pti_tomtom: Col<number>;
  pti_p5: Col<number>;
  tti_tomtom_delta_wk: Col<number>;
  tti_p5_delta_wk: Col<number>;
  tt_ratio_own_median: Col<number>;
}

export interface SeriesResponse extends Envelope {
  corridor_id: string;
  granularity: "hour" | "day";
  from?: string;
  to?: string;
  series: Maybe<HourlySeries>;
}

export interface Profile {
  hour: number[];
  n_expected: number[];
  n_ok: number[];
  missing_rate: Col<number>;
  low_confidence: boolean[];
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
  window: Maybe<Window>;
  profile: Profile;
}

export interface HeatmapResponse extends Envelope {
  corridor_id?: string;
  scope?: "network";
  days: string[];
  window: Maybe<Window> | Record<string, never>;
  tti_tomtom_p50: Maybe<number>[][];
  tti_p5_p50: Maybe<number>[][];
  n_days: Maybe<number>[][];
  missing_rate: Maybe<number>[][];
  low_confidence: Maybe<boolean>[][];
}

export interface CompareSide extends CorridorView {
  profile: {
    hour: number[];
    tt_p50_s: Col<number>;
    tt_p95_s: Col<number>;
    bti: Col<number>;
    missing_rate: Col<number>;
    low_confidence: boolean[];
  };
}

export interface CompareResponse extends Envelope {
  pair_id: string;
  hour: Maybe<number>;
  primary: CompareSide;
  /** Null when the pair declares one corridor. That is a valid answer, not an error. */
  alternate: Maybe<CompareSide>;
  advantage: Maybe<{
    hour: number[];
    primary_tt_p95_s: Col<number>;
    alternate_tt_p95_s: Col<number>;
    advantage_p95_s: Col<number>;
    low_confidence: boolean[];
  }>;
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

export interface Audit {
  status: "ok" | "insufficient_pre" | "no_controls" | "no_post";
  effective_day: string;
  settle_days: number;
  pre_start: Maybe<string>;
  pre_end: Maybe<string>;
  post_start: Maybe<string>;
  post_end: Maybe<string>;
  n_pre: number;
  n_post: number;
  n_controls: number;
  treated_pre: Maybe<number>;
  treated_post: Maybe<number>;
  synthetic_pre: Maybe<number>;
  synthetic_post: Maybe<number>;
  effect: Maybe<number>;
  cs_low: Maybe<number>;
  cs_high: Maybe<number>;
  alpha: number;
  pre_rmse: Maybe<number>;
  weights: Record<string, number>;
  low_confidence: boolean;
  method_version: string;
}

export interface AuditResponse extends Envelope {
  intervention: Intervention;
  corridor: { id: string; code: Maybe<string>; name: string };
  metric: "bti";
  audit: Maybe<Audit>;
}

export interface VerifyResponse extends Envelope {
  status: "ok" | "broken" | "never_verified";
  verification: Maybe<{
    verified_at: string;
    ok: boolean;
    rows_checked: number;
    first_seq: Maybe<number>;
    head_seq: Maybe<number>;
    head_row_hash: Maybe<string>;
    breaks: number;
    first_break_seq: Maybe<number>;
  }>;
  method: string;
  reproduce: string;
}

export interface HealthResponse extends Envelope {
  status: "ok" | "degraded";
  api: "up";
  database: "reachable" | "unreachable";
  data?: "present" | "none";
}
