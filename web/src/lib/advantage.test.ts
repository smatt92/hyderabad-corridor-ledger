import { describe, expect, it } from "vitest";
import { advantagePhrase, byHour, leadRuns, readAdvantage } from "./advantage";

const hours = (lead: number[], value = 120) => Array.from({ length: 24 }, (_, h) => (lead.includes(h) ? value : -60));

describe("leadRuns", () => {
  it("groups consecutive leading hours and ignores ties", () => {
    const adv = hours([7, 8, 9, 18]);
    adv[12] = 30; // inside the 36 s tie band
    expect(leadRuns(adv)).toEqual([[7, 9], [18, 18]]);
  });
});

describe("advantagePhrase", () => {
  it("names the longest window and counts the rest", () => {
    expect(advantagePhrase(hours([7, 8, 9, 18]))).toBe(
      "The alternate takes the lead between 07:00 and 10:00 (and in 1 shorter window elsewhere in the day).",
    );
  });

  it("covers never, always, and nothing published", () => {
    expect(advantagePhrase(hours([]))).toBe(
      "Across the published hours the declared alternate never takes the lead on this pair.",
    );
    expect(advantagePhrase(hours(Array.from({ length: 24 }, (_, h) => h)))).toBe(
      "The declared alternate leads at every hour of the day.",
    );
    expect(advantagePhrase(Array(24).fill(null))).toBe("No hour has published p95 travel times for both corridors yet.");
  });
});

describe("with intervals", () => {
  it("counts a lead only where its interval is above zero", () => {
    const adv = hours([7, 8, 9]);
    const lo = adv.map((v) => v - 60);
    lo[8] = -5; // point lead, interval includes zero
    expect(leadRuns(adv, 36, lo)).toEqual([[7, 7], [9, 9]]);
    expect(advantagePhrase(adv, 36, lo)).toBe(
      "The alternate takes the lead, with an interval above zero, between 07:00 and 08:00 (and in 1 shorter window elsewhere in the day).",
    );
    expect(advantagePhrase(adv, 36, adv.map(() => -1))).toBe(
      "At no published hour does the declared alternate lead with an interval above zero.",
    );
  });
});

describe("readAdvantage", () => {
  it("calls a floor gap insufficient samples, never a tie", () => {
    expect(readAdvantage(null, null, null, 180, 400, 200)).toEqual({ kind: "insufficient", value: null, uncertain: false });
    expect(readAdvantage(10, 5, 15, 400, 199, 200)).toEqual({ kind: "insufficient", value: null, uncertain: false });
    expect(readAdvantage(null, null, null, 0, 0, 200).kind).toBe("no_calls");
    expect(readAdvantage(null, null, null, 300, 400, 200).kind).toBe("unpublished");
  });

  it("separates ties, clear leads and leads whose interval includes zero", () => {
    expect(readAdvantage(20, -10, 50, 300, 300, 200).kind).toBe("tie");
    expect(readAdvantage(120, 60, 180, 300, 300, 200)).toEqual({ kind: "alternate", value: 120, uncertain: false });
    expect(readAdvantage(-120, -180, 30, 300, 300, 200)).toEqual({ kind: "primary", value: -120, uncertain: true });
    expect(readAdvantage(-120, -180, -40, 300, 300, 200)).toEqual({ kind: "primary", value: -120, uncertain: false });
    expect(readAdvantage(120, null, null, 300, 300, 200).uncertain).toBe(true);
  });
});

describe("byHour", () => {
  it("places sparse hours and leaves the rest null", () => {
    const out = byHour([0, 8, 23], [1, 2, 3]);
    expect(out).toHaveLength(24);
    expect([out[0], out[8], out[23], out[9]]).toEqual([1, 2, 3, null]);
  });
});
