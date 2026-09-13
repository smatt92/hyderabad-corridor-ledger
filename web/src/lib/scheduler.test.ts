import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Scheduler, msUntilIstHour } from "./scheduler";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("Scheduler", () => {
  it("keeps a flat timer count across a week of 25 s rotations and 60 s health checks", async () => {
    const scheduler = new Scheduler();
    let rotations = 0;
    let checks = 0;
    scheduler.every(25_000, () => {
      rotations++;
    });
    scheduler.every(60_000, async () => {
      checks++;
    });
    for (let minute = 0; minute < 7 * 24 * 60; minute++) {
      await vi.advanceTimersByTimeAsync(60_000);
      expect(scheduler.pending).toBeLessThanOrEqual(2);
    }
    expect(rotations).toBeGreaterThan(24_000);
    expect(checks).toBeGreaterThan(10_000);
    expect(vi.getTimerCount()).toBe(2);
    scheduler.stop();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("never overlaps a slow async job", async () => {
    const scheduler = new Scheduler();
    let running = 0;
    let maxRunning = 0;
    scheduler.every(1_000, async () => {
      running++;
      maxRunning = Math.max(maxRunning, running);
      await new Promise((resolve) => setTimeout(resolve, 5_000));
      running--;
    });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(maxRunning).toBe(1);
    scheduler.stop();
  });

  it("survives a job that throws", async () => {
    const scheduler = new Scheduler();
    let runs = 0;
    scheduler.every(1_000, () => {
      runs++;
      throw new Error("api unreachable");
    });
    await vi.advanceTimersByTimeAsync(10_500);
    expect(runs).toBe(11);
    scheduler.stop();
  });

  it("stop aborts in-flight work and cancels everything pending", async () => {
    const scheduler = new Scheduler();
    const signal = scheduler.signal;
    scheduler.after(10_000, () => {});
    scheduler.every(1_000, () => {});
    scheduler.stop();
    expect(signal.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    scheduler.every(1_000, () => {});
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("msUntilIstHour", () => {
  it("counts to the next 04:00 IST", () => {
    // 2026-09-13 21:30 UTC = 2026-09-14 03:00 IST -> one hour to 04:00
    expect(msUntilIstHour(new Date("2026-09-13T21:30:00Z"), 4)).toBe(3_600_000);
    // 2026-09-13 23:30 UTC = 05:00 IST -> 23 hours
    expect(msUntilIstHour(new Date("2026-09-13T23:30:00Z"), 4)).toBe(23 * 3_600_000);
  });
});
