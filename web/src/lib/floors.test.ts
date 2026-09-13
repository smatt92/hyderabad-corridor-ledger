import { describe, expect, it } from "vitest";
import type { Profile } from "../api/types";
import {
  FALLBACK_FLOORS, NO_INTERVAL_REASON, floorSummary, gate, gateMatrix, gateOne, gateProfile, meetsFloor, publication, resolveFloors,
  sharedPooling,
} from "./floors";

describe("floors", () => {
  it("prefers the API's floors and falls back only on null", () => {
    const api = { p95_min_samples: 250, central_min_samples: 40 };
    expect(resolveFloors(api)).toBe(api);
    expect(resolveFloors(null)).toBe(FALLBACK_FLOORS);
    expect(FALLBACK_FLOORS).not.toHaveProperty("bootstrap_resamples");
  });

  it("states plainly why a pooled statistic carries no interval", () => {
    expect(NO_INTERVAL_REASON).toBe(
      "No interval is published. An interval that resamples single calls treats calls from the same day and week as independent: in simulation the p95 travel time interval covered the true value in only 68–84% of cases under ordinary day-to-day and week-to-week variation, and in 41–58% when corridors drift more from week to week. Each value is shown with the number of calls it pools.",
    );
  });

  it("a count meets the floor only when present and at least the floor", () => {
    expect(meetsFloor(200, 200)).toBe(true);
    expect(meetsFloor(199, 200)).toBe(false);
    expect(meetsFloor(null, 200)).toBe(false);
    expect(meetsFloor(Number.NaN, 200)).toBe(false);
  });
});

describe("gate", () => {
  it("leaves a gap below the floor and never fills one", () => {
    expect(gate([1.2, 1.4, null, 1.9], [250, 180, 300, 200], 200)).toEqual([1.2, null, null, 1.9]);
    expect(gateOne(0.42, 199, 200)).toBe(null);
    expect(gateOne(0.42, 200, 200)).toBe(0.42);
  });

  it("passes values through when no counts were sent", () => {
    expect(gate([1, null, 3], undefined, 200)).toEqual([1, null, 3]);
    expect(gateMatrix([[1, 2]], undefined, 30)).toEqual([[1, 2]]);
  });

  it("gates a weekday-by-hour matrix cell by cell", () => {
    expect(gateMatrix([[1.1, 1.2], [1.3, 1.4]], [[30, 29], [null]], 30)).toEqual([[1.1, null], [null, null]]);
  });
});

describe("publication", () => {
  it("separates too few calls from a missing reference", () => {
    expect(publication(null, 180, 200)).toBe("insufficient");
    expect(publication(0.5, 180, 200)).toBe("insufficient");
    expect(publication(null, 1240, 200)).toBe("unavailable");
    expect(publication(0.5, 1240, 200)).toBe("published");
  });
});

describe("floorSummary", () => {
  it("counts below-floor hours among scheduled hours only", () => {
    expect(floorSummary([0, 40, 40, 40, 0], [0, 250, 120, 0, 0], 200)).toEqual({ scheduled: 3, below: 2, unscheduled: 2 });
  });
});

describe("sharedPooling", () => {
  const a = { window: { start: "2026-06-16", end: "2026-09-13" }, hours: "06:30-10:30 IST" };
  it("returns the common window, or null when corridors differ", () => {
    expect(sharedPooling([a, null, { ...a }])).toEqual(a);
    expect(sharedPooling([a, { ...a, window: { start: "2026-06-17", end: "2026-09-13" } }])).toBe(null);
    expect(sharedPooling([null, undefined])).toBe(null);
  });
});

describe("gateProfile", () => {
  it("gates p95 by the p95 floor, medians by the central floor, each against its own count", () => {
    const col = (a: number, b: number, c: number) => [a, b, c];
    const p: Profile = {
      hour: [7, 8, 13], n_expected: [40, 40, 0], n_ok: [250, 60, 0], missing_rate: [0, 0, null], low_confidence: [false, false, true],
      n_tti_p5: [150, 20, 0],
      tt_mean_s: col(900, 800, 700), tt_p50_s: col(880, 790, 700), tt_p95_s: col(1300, 1100, 900),
      bti: col(0.44, 0.38, 0.3),
      tti_tomtom_p25: col(1.2, 1.1, 1), tti_tomtom_p50: col(1.3, 1.2, 1), tti_tomtom_p75: col(1.5, 1.3, 1),
      tti_tomtom_p95: col(1.9, 1.6, 1.1),
      tti_p5_p25: col(1.1, 1, 1), tti_p5_p50: col(1.2, 1.1, 1), tti_p5_p75: col(1.4, 1.2, 1),
      tti_p5_p95: col(1.8, 1.5, 1),
    };
    const g = gateProfile(p, { p95_min_samples: 200, central_min_samples: 30 });
    expect(g.tti_tomtom_p95).toEqual([1.9, null, null]);
    expect(g.bti).toEqual([0.44, null, null]);
    expect(g.tti_tomtom_p50).toEqual([1.3, 1.2, null]);
    expect(g.tti_p5_p50).toEqual([1.2, null, null]);
    expect(g.tti_p5_p95).toEqual([null, null, null]);
    expect(g.n_ok).toEqual(p.n_ok);
  });
});
