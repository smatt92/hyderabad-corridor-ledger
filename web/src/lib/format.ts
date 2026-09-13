import { utcFormat } from "d3-time-format";
import { EM_DASH } from "./route";

export const MINUS = "−";
const IST_OFFSET_MS = 330 * 60_000;

const dayMonthYear = utcFormat("%-d %b %Y");
const dayMonth = utcFormat("%-d %b");
const weekdayShort = utcFormat("%a");
const dayMonthTime = utcFormat("%-d %b %H:%M");

/** A local calendar day from the API ("2026-09-12") as a UTC-midnight Date. */
export function parseDay(day: string): Date {
  return new Date(`${day}T00:00:00Z`);
}

export function fmtDay(day: string, short = false): string {
  return (short ? dayMonth : dayMonthYear)(parseDay(day));
}

export function fmtWeekday(day: string): string {
  return weekdayShort(parseDay(day));
}

export function fmtHour(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

export function addDays(day: string, n: number): string {
  return new Date(parseDay(day).getTime() + n * 86_400_000).toISOString().slice(0, 10);
}

/** Every local day from start to end, inclusive. */
export function daysBetween(start: string, end: string): string[] {
  const out: string[] = [];
  for (let d = start; d <= end; d = addDays(d, 1)) out.push(d);
  return out;
}

function present(v: number | null | undefined): v is number {
  return v != null && Number.isFinite(v);
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  return present(v) ? v.toFixed(digits) : EM_DASH;
}

export function fmtSigned(v: number | null | undefined, digits = 2): string {
  if (!present(v)) return EM_DASH;
  const text = Math.abs(v).toFixed(digits);
  return (v < 0 && Number(text) !== 0 ? MINUS : "+") + text;
}

export function fmtPercent(v: number | null | undefined, digits = 0): string {
  return present(v) ? `${fmtSigned(v, digits)}%` : EM_DASH;
}

export function fmtCoverage(missingRate: number | null | undefined): string {
  return present(missingRate) ? `${Math.round((1 - missingRate) * 100)}%` : EM_DASH;
}

export function fmtMinutes(seconds: number | null | undefined, digits = 0): string {
  return present(seconds) ? (seconds / 60).toFixed(digits) : EM_DASH;
}

type Num = number | null | undefined;

const grouped = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** A count with thousands separators: "1,530". An em dash when absent. */
export function fmtInt(n: Num): string {
  return present(n) ? grouped.format(Math.round(n)) : EM_DASH;
}

/**
 * A pooled point value with the calls it pools and, when known, the window's
 * length: "0.42 · 1,530 pooled peak-hour calls, 90 days". No interval is
 * published for it; callers show it only once the value is published.
 */
export function fmtPooled(value: string, n: Num, calls: string, days?: number | null): string {
  return `${value} · ${fmtInt(n)} ${calls}${days ? `, ${days} days` : ""}`;
}

/** A pooled call count against its publication floor: "n = 180 / 200". */
export function fmtCount(n: Num, floor: number): string {
  return `n = ${present(n) ? Math.round(n) : EM_DASH} / ${floor}`;
}

/** The explicit withheld state of a statistic below its sample floor. */
export function insufficientText(n: Num, floor: number): string {
  return `${EM_DASH} insufficient samples · ${fmtCount(n, floor)}`;
}

/** A pooling window, inclusive: "15 Jun–12 Sep 2026", with both years when they differ. */
export function fmtWindow(window: { start: string; end: string } | null | undefined): string {
  if (!window?.start || !window.end) return EM_DASH;
  const sameYear = window.start.slice(0, 4) === window.end.slice(0, 4);
  return `${fmtDay(window.start, sameYear)}–${fmtDay(window.end)}`;
}

/** Days in an inclusive window. */
export function windowDays(window: { start: string; end: string } | null | undefined): number | null {
  if (!window?.start || !window.end) return null;
  return Math.round((parseDay(window.end).getTime() - parseDay(window.start).getTime()) / 86_400_000) + 1;
}

/** The Hyderabad local calendar day of an instant, as the API's days are. */
export function istDay(iso: string): string {
  return new Date(new Date(iso).getTime() + IST_OFFSET_MS).toISOString().slice(0, 10);
}

/** An API timestamp shown in Hyderabad local time. */
export function fmtIst(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  return `${dayMonthTime(new Date(new Date(iso).getTime() + IST_OFFSET_MS))} IST`;
}

export const STALE_AFTER_HOURS = 30;

export function ageHours(iso: string | null | undefined, now: Date): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? (now.getTime() - t) / 3_600_000 : null;
}

/** Metrics are recomputed daily, so older than STALE_AFTER_HOURS means a missed run. */
export function isStale(iso: string | null | undefined, now: Date): boolean {
  const age = ageHours(iso, now);
  return age === null || age > STALE_AFTER_HOURS;
}
