import { useMemo, useState } from "preact/hooks";
import { useAllSeries, useApi, useWidth } from "../api/hooks";
import type { CorridorsResponse, InterventionsResponse, NetworkStateResponse, VerifyResponse } from "../api/types";
import { FAINT, INK, MID, MONO, PAPER, RUST, SOFT, TEXT } from "../lib/color";
import { NO_INTERVAL_REASON } from "../lib/floors";
import { daysBetween, fmtCoverage, fmtDay, fmtHour, fmtIst, fmtWeekday, isStale } from "../lib/format";
import { Audit } from "./Audit";
import { cache } from "./cache";
import { Compare } from "./Compare";
import { Notice } from "./common";
import { Ledger } from "./Ledger";
import { MapView } from "./MapView";
import { Pulse } from "./Pulse";
import { Rhythm } from "./Rhythm";
import { SeriesView } from "./series";

type View = "ledger" | "pulse" | "rhythm" | "compare" | "audit" | "map";
const TABS: [View, string][] = [
  ["ledger", "Corridor ledger"], ["pulse", "Network pulse"], ["rhythm", "Weekly rhythm"],
  ["compare", "Route comparison"], ["audit", "Intervention audit"], ["map", "Map"],
];
const mono = { fontFamily: MONO, fontVariantNumeric: "tabular-nums" } as const;

export function AnalystApp() {
  const corridorsRes = useApi<CorridorsResponse>(cache, "/api/corridors");
  const networkRes = useApi<NetworkStateResponse>(cache, "/api/network/state");
  const interventionsRes = useApi<InterventionsResponse>(cache, "/api/interventions");
  const verifyRes = useApi<VerifyResponse>(cache, "/api/verify");
  const narrow = useWidth() < 768;
  const [view, setView] = useState<View>("ledger");
  const [dayIndex, setDayIndex] = useState<number | null>(null);
  const [hour, setHour] = useState(8);
  const [now] = useState(() => new Date());

  const data = corridorsRes?.ok ? corridorsRes.data : null;
  const network = networkRes?.ok ? networkRes.data : null;
  const corridors = useMemo(() => data?.corridors ?? [], [data]);
  const ids = useMemo(() => corridors.map((c) => c.id), [corridors]);
  const days = useMemo(() => (data?.window ? daysBetween(data.window.start, data.window.end) : []), [data]);
  const seriesSet = useAllSeries(cache, ids, view === "ledger" || view === "pulse" || view === "map");
  const views = useMemo(() => {
    const out = new Map<string, SeriesView>();
    seriesSet?.byId.forEach((res, id) => {
      if (res.series) out.set(id, new SeriesView(res.series));
    });
    return out;
  }, [seriesSet]);

  const index = days.length ? Math.min(dayIndex ?? days.length - 1, days.length - 1) : 0;
  const day = days[index] ?? null;
  const sample = Boolean(data?.sample || network?.sample);
  const stale = data ? isStale(data.as_of, now) : false;
  const interventions = interventionsRes?.ok ? interventionsRes.data.interventions : [];
  const verification = verifyRes?.ok ? verifyRes.data : null;
  const pairs = new Set(corridors.map((c) => c.pair_id).filter(Boolean)).size;

  const latest = () => {
    setDayIndex(null);
    if (network?.status === "ok" && network.day === days.at(-1) && network.hour != null) setHour(network.hour);
  };

  let freshness: preact.ComponentChildren = "loading published indices…";
  if (corridorsRes && !corridorsRes.ok) freshness = <span style={{ color: RUST }}>read API unreachable · nothing shown rather than something stale</span>;
  else if (data) {
    freshness = (
      <span>
        indices computed {fmtIst(data.as_of)} · hourly cells
        {stale ? <span style={{ color: RUST }}> · STALE, no run in the last 30 h</span> : null}
        {data.low_confidence ? <span style={{ color: RUST }}> · ◌ window coverage {fmtCoverage(data.missingness_rate)}</span> : null}
      </span>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: PAPER }}>
      {/* Sticky on wide screens only: on a phone the header, tabs and scrubbers would cover the view. */}
      <div style={{ position: narrow ? "static" : "sticky", top: 0, zIndex: 30, background: PAPER }}>
        {sample ? (
          <div style={{ background: "#1a1917", color: PAPER, display: "flex", flexWrap: "wrap", gap: "14px", justifyContent: "space-between", alignItems: "baseline", padding: "7px 22px", fontFamily: MONO, fontSize: "11px", letterSpacing: ".2em", textTransform: "uppercase" }}>
            <span>◆ Sample data — synthetic placeholder values, not measurements</span>
            <span style={{ letterSpacing: ".12em", textTransform: "none", color: "#a8a59d" }}>every corridor name is prefixed “Demo —”</span>
          </div>
        ) : null}

        <div style={{ borderBottom: `1px solid ${INK}`, background: PAPER }}>
          <div style={{ maxWidth: "1440px", margin: "0 auto", padding: "18px 22px 14px", display: "flex", flexWrap: "wrap", gap: "18px", alignItems: "flex-end", justifyContent: "space-between" }}>
            <div style={{ maxWidth: "640px" }}>
              <div style={{ fontSize: "11px", letterSpacing: ".22em", textTransform: "uppercase", color: MID, fontFamily: MONO }}>
                Independent measurement{data?.method_version ? ` · ${data.method_version}` : ""}
              </div>
              <h1 style={{ margin: "6px 0 8px", fontSize: "30px", lineHeight: 1.02, letterSpacing: "-.025em", fontWeight: 700 }}>Hyderabad Corridor Ledger</h1>
              <p style={{ margin: 0, fontSize: "14px", lineHeight: 1.45, color: TEXT, maxWidth: "52ch", textWrap: "pretty" }}>
                Google tells you the fastest route right now. We tell you the most reliable route at 8:40 on a Tuesday.
              </p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "8px" }}>
              <div style={{ ...mono, fontSize: "12px", color: TEXT }}>{freshness}</div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button onClick={() => (location.search = "?mode=wall")} style={{ fontSize: "11px", letterSpacing: ".14em", textTransform: "uppercase", padding: "7px 12px", background: INK, color: PAPER, border: `1px solid ${INK}`, cursor: "pointer" }}>
                  Wall mode
                </button>
                <span style={{ fontSize: "11px", color: SOFT, fontFamily: MONO }}>?mode=wall</span>
              </div>
            </div>
          </div>

          <div style={{ maxWidth: "1440px", margin: "0 auto", padding: "0 22px 12px", display: "flex", gap: "2px", flexWrap: "wrap" }}>
            {TABS.map(([key, label]) => {
              const active = view === key;
              return (
                <button key={key} onClick={() => setView(key)} style={{ fontSize: "12px", letterSpacing: ".04em", padding: "8px 13px", cursor: "pointer", border: `1px solid ${active ? INK : "transparent"}`, borderBottom: active ? `1px solid ${PAPER}` : "1px solid transparent", marginBottom: "-1px", background: active ? PAPER : "transparent", color: active ? INK : MID, fontWeight: active ? 600 : 400 }}>
                  {label}
                </button>
              );
            })}
          </div>

          {day ? (
            <div style={{ maxWidth: "1440px", margin: "0 auto", padding: "12px 22px 14px", borderTop: `1px solid ${FAINT}`, display: "flex", flexWrap: "wrap", gap: "20px", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: "10px", minWidth: "210px" }}>
                <div style={{ ...mono, fontSize: "26px", fontWeight: 500, letterSpacing: "-.02em" }}>{fmtHour(hour)}</div>
                <div style={{ ...mono, fontSize: "12px", color: MID }}>{fmtWeekday(day)} {fmtDay(day)}</div>
              </div>
              <div style={{ flex: "1 1 260px", minWidth: "200px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", letterSpacing: ".16em", textTransform: "uppercase", color: SOFT, marginBottom: "4px" }}>
                  <span>Date · {days.length}d window</span>
                  <span>{index === days.length - 1 ? "latest" : `−${days.length - 1 - index}d`}</span>
                </div>
                <input type="range" min={0} max={days.length - 1} step={1} value={index} onInput={(e) => setDayIndex(Number((e.target as HTMLInputElement).value))} style={{ width: "100%", display: "block" }} aria-label="Date" />
              </div>
              <div style={{ flex: "1 1 260px", minWidth: "200px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", letterSpacing: ".16em", textTransform: "uppercase", color: SOFT, marginBottom: "4px" }}>
                  <span>Time of day · hourly cells</span>
                  <span>{fmtHour(hour)}</span>
                </div>
                <input type="range" min={0} max={23} step={1} value={hour} onInput={(e) => setHour(Number((e.target as HTMLInputElement).value))} style={{ width: "100%", display: "block" }} aria-label="Hour" />
              </div>
              <button onClick={latest} style={{ fontSize: "11px", letterSpacing: ".14em", textTransform: "uppercase", padding: "7px 12px", background: "transparent", color: INK, border: `1px solid ${INK}`, cursor: "pointer" }}>
                Latest
              </button>
              <div style={{ fontSize: "11px", color: SOFT, maxWidth: "26ch", lineHeight: 1.35 }}>“Live” and “historical” are the same views at different scrubber positions.</div>
            </div>
          ) : null}
        </div>
      </div>

      <div style={{ maxWidth: "1440px", margin: "0 auto", padding: "26px 22px 90px" }}>
        {corridorsRes === null ? (
          <div style={{ ...mono, fontSize: "12px", color: MID }}>Loading published indices…</div>
        ) : !corridorsRes.ok ? (
          <Notice kicker="Degraded" title="The read API could not be reached">
            {corridorsRes.error}. Nothing is shown rather than something stale.{" "}
            <button onClick={() => location.reload()} style={{ marginLeft: "6px", fontSize: "11px", letterSpacing: ".1em", textTransform: "uppercase", padding: "4px 8px", border: `1px solid ${INK}`, background: "transparent", cursor: "pointer" }}>
              Retry
            </button>
          </Notice>
        ) : !day ? (
          <Notice kicker="Empty ledger" title="No measurements published yet" tone="ink">
            The collector has not published any samples, so there is nothing to show. The ledger fills after the first metrics run.
          </Notice>
        ) : (
          <>
            {seriesSet && seriesSet.byId.size + seriesSet.failed.length < seriesSet.total && (view === "ledger" || view === "pulse" || view === "map") ? (
              <div style={{ ...mono, fontSize: "11px", color: MID, marginBottom: "10px" }}>
                loading hourly series {seriesSet.byId.size + seriesSet.failed.length}/{seriesSet.total}…
              </div>
            ) : null}
            {seriesSet && seriesSet.failed.length ? (
              <div style={{ ...mono, fontSize: "11px", color: RUST, marginBottom: "10px" }}>
                {seriesSet.failed.length} corridor series failed to load; their rows show no data rather than an estimate.
              </div>
            ) : null}
            {view === "ledger" ? <Ledger corridors={corridors} views={views} days={days} dayIndex={index} hour={hour} narrow={narrow} interventions={interventions} floors={data?.floors ?? null} /> : null}
            {view === "pulse" ? <Pulse corridors={corridors} views={views} days={days} dayIndex={index} hour={hour} /> : null}
            {view === "rhythm" ? <Rhythm corridors={corridors} day={day} hour={hour} /> : null}
            {view === "compare" ? <Compare corridors={corridors} hour={hour} windowEnd={days.at(-1)!} /> : null}
            {view === "audit" ? <Audit interventions={interventions} corridors={corridors} /> : null}
            {view === "map" ? <MapView corridors={corridors} views={views} day={day} hour={hour} asOf={data?.as_of ?? null} /> : null}
          </>
        )}

        <div style={{ marginTop: "60px", paddingTop: "16px", borderTop: `1px solid ${INK}`, display: "flex", flexWrap: "wrap", gap: "24px", justifyContent: "space-between", fontSize: "11px", color: MID, lineHeight: 1.55 }}>
          <div style={{ maxWidth: "62ch" }}>
            Method: probe travel times from TomTom calculateRoute (summary only) at each corridor’s scheduled slots, aggregated to hourly cells. Indices are computed against two free-flow references, both published: TomTom’s no-traffic time and the observed 5th percentile of night-slot calls (00:00–04:00 IST) over a trailing 28 days. A 95th percentile, and BTI and PTI with it, is never computed on an hourly cell of two to four calls: it is computed on calls pooled over a stated window and published only above a sample floor, as a point value beside the number of calls it pools. {NO_INTERVAL_REASON} Corridor length is the payload’s measured length_meters and is shown as an em dash when absent. Missing samples are never interpolated.
          </div>
          <div style={{ ...mono, display: "flex", flexDirection: "column", gap: "4px", alignItems: "flex-end" }}>
            <span>
              Hyderabad Corridor Ledger{sample ? " · sample data" : ""} · {pairs} pairs · {corridors.length} measured corridors · {days.length}-day window
            </span>
            <span>
              open data: <a href="/api/export.csv">CSV</a> · <a href="/api/export.parquet">Parquet</a> ·{" "}
              <a href="/api/verify">
                {verification?.status === "ok"
                  ? `chain verified ${fmtIst(verification.verification?.verified_at)}`
                  : verification?.status === "broken"
                    ? "CHAIN BROKEN — see /verify"
                    : "chain not yet verified"}
              </a>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
