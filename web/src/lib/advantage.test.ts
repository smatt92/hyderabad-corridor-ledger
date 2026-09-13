import { describe, expect, it } from "vitest";
import { NO_LEAD_REASON, byHour, readAdvantage } from "./advantage";

describe("readAdvantage", () => {
  it("calls a floor gap insufficient samples, never a tie", () => {
    expect(readAdvantage(null, 180, 400, 200)).toEqual({ kind: "insufficient", value: null });
    expect(readAdvantage(10, 400, 199, 200)).toEqual({ kind: "insufficient", value: null });
    expect(readAdvantage(null, 0, 0, 200).kind).toBe("no_calls");
    expect(readAdvantage(null, 300, 400, 200).kind).toBe("unpublished");
    expect(readAdvantage(Number.NaN, 300, 400, 200).kind).toBe("unpublished");
  });

  it("publishes the signed point advantage with no lead, tie or significance classification", () => {
    expect(readAdvantage(120, 300, 300, 200)).toEqual({ kind: "published", value: 120 });
    expect(readAdvantage(-120, 300, 300, 200)).toEqual({ kind: "published", value: -120 });
    expect(readAdvantage(5, 300, 300, 200)).toEqual({ kind: "published", value: 5 });
    expect(readAdvantage(0, 300, 300, 200)).toEqual({ kind: "published", value: 0 });
  });

  it("says plainly why no hour is marked as a reliable lead", () => {
    expect(NO_LEAD_REASON).toBe(
      "No hour is marked as a reliable lead, because no valid interval exists: an interval that resamples single calls treats calls from the same day and week as independent, and in simulation it showed a “lead” between two identical routes in 10–20% of hours.",
    );
  });
});

describe("byHour", () => {
  it("places sparse hours and leaves the rest null", () => {
    const out = byHour([0, 8, 23], [1, 2, 3]);
    expect(out).toHaveLength(24);
    expect([out[0], out[8], out[23], out[9]]).toEqual([1, 2, 3, null]);
  });
});
