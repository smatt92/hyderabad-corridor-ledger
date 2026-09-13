import { describe, expect, it } from "vitest";
import { advantagePhrase, byHour, leadRuns } from "./advantage";

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

describe("byHour", () => {
  it("places sparse hours and leaves the rest null", () => {
    const out = byHour([0, 8, 23], [1, 2, 3]);
    expect(out).toHaveLength(24);
    expect([out[0], out[8], out[23], out[9]]).toEqual([1, 2, 3, null]);
  });
});
