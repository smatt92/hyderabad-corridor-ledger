import type { Envelope } from "./types";

export type Result<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number | null; error: string };

const TIMEOUT_MS = 15_000;

/** GET a JSON envelope. Never throws: failures come back as { ok: false }. */
export async function getJson<T extends Envelope>(path: string, signal?: AbortSignal): Promise<Result<T>> {
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      headers: { Accept: "application/json" },
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
    const body = (await response.json().catch(() => null)) as T | null;
    if (!response.ok || body === null) {
      const detail = body?.error ? JSON.stringify(body.error) : response.statusText;
      return { ok: false, status: response.status, error: detail || `HTTP ${response.status}` };
    }
    return { ok: true, status: response.status, data: body };
  } catch (error) {
    return { ok: false, status: null, error: error instanceof Error ? error.message : "network error" };
  }
}

/** Session cache for analyst mode. Wall mode refreshes with getJson directly. */
export class Cache {
  private readonly entries = new Map<string, Promise<Result<Envelope>>>();

  get<T extends Envelope>(path: string): Promise<Result<T>> {
    let entry = this.entries.get(path);
    if (!entry) {
      entry = getJson<Envelope>(path).then((result) => {
        if (!result.ok) this.entries.delete(path); // retry failures on next ask
        return result;
      });
      this.entries.set(path, entry);
    }
    return entry as Promise<Result<T>>;
  }
}

/** Run tasks with at most `limit` in flight. */
export async function pooled<T, R>(items: T[], limit: number, task: (item: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await task(items[index]!);
    }
  });
  await Promise.all(workers);
  return results;
}
