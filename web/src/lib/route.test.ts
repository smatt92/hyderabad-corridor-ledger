import { describe, expect, it } from "vitest";
import { EM_DASH, formatLength, mapsHandoffUrl } from "./route";

const MIYAPUR = { lat: 17.497, lon: 78.36 };
const HITEC = { lat: 17.447, lon: 78.377 };

describe("mapsHandoffUrl", () => {
  it("passes origin and destination only", () => {
    expect(mapsHandoffUrl(MIYAPUR, HITEC)).toBe(
      "https://www.google.com/maps/dir/?api=1&origin=17.497,78.36&destination=17.447,78.377&travelmode=driving",
    );
  });

  it("never carries waypoints or any other parameter", () => {
    const url = new URL(mapsHandoffUrl(MIYAPUR, HITEC));
    expect([...url.searchParams.keys()]).toEqual(["api", "origin", "destination", "travelmode"]);
    expect(url.href.toLowerCase()).not.toContain("waypoint");
  });

  it("refuses invalid coordinates rather than guessing", () => {
    expect(() => mapsHandoffUrl({ lat: Number.NaN, lon: 78.36 }, HITEC)).toThrow(RangeError);
    expect(() => mapsHandoffUrl(MIYAPUR, { lat: 17.4, lon: 200 })).toThrow(RangeError);
  });
});

describe("formatLength", () => {
  it("formats the payload's length_meters", () => {
    expect(formatLength(9800)).toBe("9.8 km");
    expect(formatLength(12649)).toBe("12.6 km");
  });

  it("renders an em dash when the payload has no length", () => {
    for (const absent of [null, undefined, Number.NaN, 0, -5]) {
      expect(formatLength(absent)).toBe(EM_DASH);
    }
  });
});
