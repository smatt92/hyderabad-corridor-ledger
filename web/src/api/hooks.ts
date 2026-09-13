import { useEffect, useRef, useState } from "preact/hooks";
import { type Cache, type Result, pooled } from "./client";
import type { Envelope, SeriesResponse } from "./types";

/** A cached GET. null while loading; a Result once settled. */
export function useApi<T extends Envelope>(cache: Cache, path: string | null): Result<T> | null {
  const [state, setState] = useState<{ path: string | null; result: Result<T> | null }>({
    path: null,
    result: null,
  });
  useEffect(() => {
    if (!path) return;
    let live = true;
    void cache.get<T>(path).then((result) => {
      if (live) setState({ path, result });
    });
    return () => {
      live = false;
    };
  }, [cache, path]);
  return state.path === path ? state.result : null;
}

export interface SeriesSet {
  byId: Map<string, SeriesResponse>;
  failed: string[];
  total: number;
}

/** Hourly series for every corridor over the read window, fetched once, six at a time. */
export function useAllSeries(cache: Cache, ids: string[], enabled: boolean): SeriesSet | null {
  const [state, setState] = useState<SeriesSet | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (!enabled || started.current || ids.length === 0) return;
    started.current = true;
    let live = true;
    const byId = new Map<string, SeriesResponse>();
    const failed: string[] = [];
    setState({ byId, failed, total: ids.length });
    void pooled(ids, 6, async (id) => {
      const result = await cache.get<SeriesResponse>(`/api/corridors/${encodeURIComponent(id)}/series`);
      if (result.ok) byId.set(id, result.data);
      else failed.push(id);
      if (live) setState({ byId: new Map(byId), failed: [...failed], total: ids.length });
    });
    return () => {
      live = false;
    };
  }, [cache, ids, enabled]);
  return state;
}

export function useWidth(): number {
  const [width, setWidth] = useState(() => window.innerWidth);
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return width;
}
