/**
 * One owner for every timer and in-flight request in a layout tree.
 *
 * Wall mode runs unattended for weeks. Repeating work is a setTimeout chain
 * scheduled after each run finishes, so runs never overlap or pile up behind a
 * slow network, and stop() cancels every pending timer and aborts every
 * request. No setInterval anywhere.
 */

type Job = (signal: AbortSignal) => void | Promise<void>;

export class Scheduler {
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();
  private controller = new AbortController();
  private stopped = false;

  get signal(): AbortSignal {
    return this.controller.signal;
  }

  /** Number of pending timers. Stays flat however long the scheduler runs. */
  get pending(): number {
    return this.timers.size;
  }

  after(ms: number, job: Job): () => void {
    if (this.stopped) return () => {};
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      if (!this.stopped) void job(this.signal);
    }, ms);
    this.timers.add(timer);
    return () => {
      clearTimeout(timer);
      this.timers.delete(timer);
    };
  }

  /** Run now, then again `ms` after each run completes. */
  every(ms: number, job: Job): () => void {
    let cancelled = false;
    let cancelTimer = () => {};
    const run = async () => {
      if (cancelled || this.stopped) return;
      try {
        await job(this.signal);
      } catch {
        // a failed run is reported by the job itself; the chain must survive it
      }
      if (!cancelled && !this.stopped) cancelTimer = this.after(ms, run);
    };
    void run();
    return () => {
      cancelled = true;
      cancelTimer();
    };
  }

  stop(): void {
    this.stopped = true;
    for (const timer of this.timers) clearTimeout(timer);
    this.timers.clear();
    this.controller.abort();
  }
}

const IST_OFFSET_MINUTES = 330;

/** Milliseconds from `now` until the next `hour`:00 in Asia/Kolkata. */
export function msUntilIstHour(now: Date, hour: number): number {
  const istNow = new Date(now.getTime() + IST_OFFSET_MINUTES * 60_000);
  const target = Date.UTC(istNow.getUTCFullYear(), istNow.getUTCMonth(), istNow.getUTCDate(), hour);
  let ms = target - istNow.getTime();
  if (ms <= 0) ms += 24 * 3_600_000;
  return ms;
}
