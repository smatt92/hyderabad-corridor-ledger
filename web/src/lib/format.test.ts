import { describe, expect, it } from "vitest";
import {
  MINUS, addDays, daysBetween, fmtCount, fmtCoverage, fmtDay, fmtHour, fmtInterval, fmtIst, fmtMinutes,
  fmtMinutesInterval, fmtNum, fmtPercent, fmtSigned, fmtSignedInterval, fmtWeekday, fmtWindow, insufficientText,
  isStale, istDay, windowDays,
} from "./format";
import { EM_DASH } from "./route";

describe("dates", () => {
  it("formats API days without shifting them through local time", () => {
    expect(fmtDay("2026-09-13")).toBe("13 Sep 2026");
    expect(fmtDay("2026-09-13", true)).toBe("13 Sep");
    expect(fmtWeekday("2026-09-13")).toBe("Sun");
    expect(fmtHour(8)).toBe("08:00");
  });

  it("walks days across month ends", () => {
    expect(addDays("2026-08-31", 1)).toBe("2026-09-01");
    expect(daysBetween("2026-08-30", "2026-09-02")).toEqual([
      "2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02",
    ]);
  });

  it("shows API timestamps in IST", () => {
    expect(fmtIst("2026-09-13T21:45:00+00:00")).toBe("14 Sep 03:15 IST");
    expect(istDay("2026-08-01T00:00:00+05:30")).toBe("2026-08-01");
    expect(istDay("2026-08-01T19:00:00Z")).toBe("2026-08-02");
  });
});

describe("numbers", () => {
  it("uses a true minus sign and never prints a negative zero", () => {
    expect(fmtSigned(0.214)).toBe("+0.21");
    expect(fmtSigned(-0.214)).toBe(`${MINUS}0.21`);
    expect(fmtSigned(-0.001)).toBe("+0.00");
    expect(fmtPercent(12.4)).toBe("+12%");
  });

  it("renders absent values as an em dash, never as zero", () => {
    for (const fmt of [fmtNum, fmtSigned, fmtPercent, fmtCoverage, fmtMinutes]) {
      expect(fmt(null)).toBe(EM_DASH);
      expect(fmt(Number.NaN)).toBe(EM_DASH);
    }
  });

  it("coverage and minutes", () => {
    expect(fmtCoverage(0.163)).toBe("84%");
    expect(fmtMinutes(1830)).toBe("31");
  });
});

describe("staleness", () => {
  const now = new Date("2026-09-14T06:00:00Z");
  it("flags data older than 30 hours or with no as_of at all", () => {
    expect(isStale("2026-09-13T21:45:00Z", now)).toBe(false);
    expect(isStale("2026-09-12T21:45:00Z", now)).toBe(true);
    expect(isStale(null, now)).toBe(true);
  });
});

describe("pooled statistics", () => {
  it("formats a point value with its interval", () => {
    expect(fmtInterval(0.42, 0.31, 0.58)).toBe("0.42 [0.31, 0.58]");
    expect(fmtInterval(1.8412, 1.7, 2.019, 3)).toBe("1.841 [1.700, 2.019]");
    expect(fmtSignedInterval(0.12, -0.03, 0.25)).toBe(`+0.12 [${MINUS}0.03, +0.25]`);
    expect(fmtMinutesInterval(1872, 1788, 1980)).toBe("31.2 [29.8, 33.0]");
  });

  it("never prints a number for an unpublished estimate, and marks a missing bound", () => {
    for (const fmt of [fmtInterval, fmtSignedInterval, fmtMinutesInterval]) {
      expect(fmt(null, 0.3, 0.5)).toBe(EM_DASH);
      expect(fmt(Number.NaN, 0.3, 0.5)).toBe(EM_DASH);
    }
    expect(fmtInterval(0.42, null, 0.58)).toBe(`0.42 [${EM_DASH}, 0.58]`);
  });

  it("states the count against the floor", () => {
    expect(fmtCount(180, 200)).toBe("n = 180 / 200");
    expect(fmtCount(null, 30)).toBe(`n = ${EM_DASH} / 30`);
    expect(insufficientText(180, 200)).toBe(`${EM_DASH} insufficient samples · n = 180 / 200`);
    expect(insufficientText(0, 30)).toBe(`${EM_DASH} insufficient samples · n = 0 / 30`);
  });

  it("names a pooling window by its dates", () => {
    expect(fmtWindow({ start: "2026-06-16", end: "2026-09-13" })).toBe("16 Jun–13 Sep 2026");
    expect(fmtWindow({ start: "2025-12-20", end: "2026-03-19" })).toBe("20 Dec 2025–19 Mar 2026");
    expect(fmtWindow(null)).toBe(EM_DASH);
    expect(windowDays({ start: "2026-06-16", end: "2026-09-13" })).toBe(90);
    expect(windowDays(null)).toBe(null);
  });
});
