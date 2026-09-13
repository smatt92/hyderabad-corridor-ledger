import type { ComponentChildren, JSX } from "preact";
import { useMemo, useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { Corridor, CorridorLedger, Floors, Intervention, ProfileResponse } from "../api/types";
import { ProfileChart } from "../charts/ProfileChart";
import { Sparkline } from "../charts/Sparkline";
import { TrendChart } from "../charts/TrendChart";
import { CARD, FAINT, GHOST, HATCH, INK, MID, MONO, RAMP_TTI_TEXT, RULE, RUST, SOFT, TEAL, TEXT, ramp } from "../lib/color";
import { type Publication, floorSummary, gateProfile, publication, resolveFloors, sharedPooling } from "../lib/floors";
import {
  addDays, fmtCount, fmtDay, fmtHour, fmtInterval, fmtMinutes, fmtMinutesInterval, fmtNum, fmtSigned, fmtWindow,
  insufficientText, istDay, windowDays,
} from "../lib/format";
import { EM_DASH, formatLength } from "../lib/route";
import { cache } from "./cache";
import { PooledStat, SectionHead, StatList, kicker, smallCaps } from "./common";
import type { SeriesView } from "./series";

/** Values of the hourly cell at the scrubber position. */
type HourlyKey = "tti_tomtom" | "tti_p5" | "delta_tomtom" | "delta_p5" | "coverage";
/** Values pooled over peak hours across the trailing window; the scrubbers do not move them. */
type PooledKey = "bti" | "pti_tomtom" | "pti_p5";
type SortKey = "shrunk" | "name" | HourlyKey | PooledKey;

interface Pooled {
  value: number | null;
  state: Publication | "absent";
  n: number | null;
}

interface Row {
  c: Corridor;
  view: SeriesView | undefined;
  v: Record<HourlyKey, number | null>;
  pooled: Record<PooledKey, Pooled>;
  low: boolean;
  worseness: number | null;
}

type Group = "id" | "hourly" | "pooled";

const COLUMNS: { key: SortKey | "spark"; label: string; sub?: string; align: "left" | "right"; group: Group }[] = [
  { key: "name", label: "Corridor", align: "left", group: "id" },
  { key: "tti_tomtom", label: "TTI", sub: "TomTom", align: "right", group: "hourly" },
  { key: "tti_p5", label: "TTI", sub: "obs p5", align: "right", group: "hourly" },
  { key: "spark", label: "7-day", align: "left", group: "hourly" },
  { key: "delta_tomtom", label: "Δ wk", sub: "TomTom", align: "right", group: "hourly" },
  { key: "delta_p5", label: "Δ wk", sub: "obs p5", align: "right", group: "hourly" },
  { key: "coverage", label: "Samples", sub: "this hour", align: "right", group: "hourly" },
  { key: "bti", label: "BTI", sub: "pooled peak", align: "right", group: "pooled" },
  { key: "pti_tomtom", label: "PTI", sub: "TomTom · pooled", align: "right", group: "pooled" },
  { key: "pti_p5", label: "PTI", sub: "obs p5 · pooled", align: "right", group: "pooled" },
];
const HOURLY_SPAN = COLUMNS.filter((c) => c.group === "hourly").length;
const POOLED_SPAN = COLUMNS.filter((c) => c.group === "pooled").length;
const FIRST_POOLED = COLUMNS.find((c) => c.group === "pooled")!.key;

function isPooled(key: SortKey): key is PooledKey {
  return key === "bti" || key === "pti_tomtom" || key === "pti_p5";
}

function pooledOf(ledger: CorridorLedger | null | undefined, key: PooledKey, floor: number): Pooled {
  if (!ledger) return { value: null, state: "absent", n: null };
  const value = ledger[key]?.value ?? null;
  const state = publication(value, ledger.n, floor);
  return { value: state === "published" ? value : null, state, n: ledger.n };
}

function withheldLabel(p: Pooled, key: PooledKey): string {
  if (p.state === "insufficient") return "insufficient samples";
  if (p.state === "absent") return "no pooled record";
  return key === "pti_p5" ? "no obs p5 reference" : "not published";
}

function num(extra: JSX.CSSProperties = {}): JSX.CSSProperties {
  return { fontFamily: MONO, fontVariantNumeric: "tabular-nums", textAlign: "right", padding: "9px 10px", fontSize: "13.5px", whiteSpace: "nowrap", ...extra };
}

function deltaColor(d: number | null): string {
  return d == null ? MID : d > 0.02 ? RUST : d < -0.02 ? TEAL : MID;
}

function coverageText(c: number | null): string {
  return c == null ? EM_DASH : `${Math.round(c * 100)}%`;
}

function sortValue(row: Row, key: SortKey): number | string | null {
  if (key === "name") return row.c.name;
  if (key === "shrunk") return row.worseness;
  if (isPooled(key)) return row.pooled[key].value;
  return row.v[key];
}

interface Props {
  corridors: Corridor[];
  views: Map<string, SeriesView>;
  days: string[];
  dayIndex: number;
  hour: number;
  narrow: boolean;
  interventions: Intervention[];
  floors: Floors | null;
}

export function Ledger({ corridors, views, days, dayIndex, hour, narrow, interventions, floors }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "shrunk", dir: -1 });
  const [open, setOpen] = useState<string | null>(null);
  const day = days[dayIndex]!;
  const f = resolveFloors(floors);
  const q = f.p95_min_samples;
  const shared = useMemo(() => sharedPooling(corridors.map((c) => c.ledger)), [corridors]);

  const rows = useMemo<Row[]>(() => {
    return corridors.map((c) => {
      const view = views.get(c.id);
      const at = (k: Parameters<SeriesView["value"]>[0]) => view?.value(k, day, hour) ?? null;
      const rank = c.rankings.tti_tomtom?.rank ?? null;
      return {
        c,
        view,
        v: {
          tti_tomtom: at("tti_tomtom"), tti_p5: at("tti_p5"),
          delta_tomtom: at("tti_tomtom_delta_wk"), delta_p5: at("tti_p5_delta_wk"),
          coverage: view?.coverage(day, hour) ?? null,
        },
        pooled: { bti: pooledOf(c.ledger, "bti", q), pti_tomtom: pooledOf(c.ledger, "pti_tomtom", q), pti_p5: pooledOf(c.ledger, "pti_p5", q) },
        low: view ? view.lowConfidence(day, hour) : true,
        worseness: rank == null ? null : -rank,
      };
    });
  }, [corridors, views, day, hour, q]);

  const sorted = useMemo(() => {
    const out = [...rows];
    out.sort((a, b) => {
      const x = sortValue(a, sort.key);
      const y = sortValue(b, sort.key);
      if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1; // absent values last
      return (typeof x === "string" ? x.localeCompare(y as string) : x - (y as number)) * sort.dir;
    });
    return out;
  }, [rows, sort]);

  const tti = rows.map((r) => r.v.tti_tomtom).filter((v): v is number => v != null);
  const [tlo, thi] = tti.length ? [Math.min(...tti), Math.max(...tti)] : [1, 2];
  const ttiColor = (t: number | null) => (t == null ? SOFT : ramp(RAMP_TTI_TEXT, (t - tlo) / (thi - tlo || 1)));
  const last7 = useMemo(() => Array.from({ length: 7 }, (_, k) => addDays(day, k - 6)), [day]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : key === "name" ? 1 : -1 }));
  const toggleOpen = (id: string) => setOpen((o) => (o === id ? null : id));

  const poolWindow = shared ? fmtWindow(shared.window) : null;
  const pooledSentence = shared
    ? `BTI and PTI are not hourly: each is computed once on all successful peak-hour calls (${shared.hours}) pooled over ${poolWindow}, so neither scrubber moves them.`
    : "BTI and PTI are not hourly: each is computed once on all successful peak-hour calls pooled over the corridor’s trailing window (dates in the expanded row), so neither scrubber moves them.";

  return (
    <div>
      <SectionHead
        title="Corridor ledger"
        sub={`${corridors.length} declared corridors, sorted worst-first on the shrunk index. TTI, Δ wk and samples are hourly cells at ${fmtHour(hour)} on ${fmtDay(day)}. ${pooledSentence} Click a row for intervals, the 24-hour profile and the 90-day trend.`}
        right={
          <div style={{ fontFamily: MONO, fontSize: "11px", color: MID, textAlign: "right", lineHeight: 1.5 }}>
            <div>TTI mean ÷ free-flow, TomTom and observed p5 · hourly at {fmtHour(hour)} · Δ vs same hour last week</div>
            <div>BTI (p95−mean)÷mean · PTI p95 ÷ free-flow, both references</div>
            <div>BTI · PTI pooled over peak hours, {poolWindow ?? "each corridor’s trailing window"} · published from {q} calls</div>
          </div>
        }
      />

      {!narrow ? (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th />
              <th colSpan={HOURLY_SPAN} style={{ fontSize: "9.5px", letterSpacing: ".12em", textTransform: "uppercase", color: SOFT, fontWeight: 500, textAlign: "left", padding: "0 10px 6px", borderBottom: `1px solid ${FAINT}` }}>
                Hourly cell · {fmtHour(hour)} · {fmtDay(day)}
              </th>
              <th colSpan={POOLED_SPAN} style={{ fontSize: "9.5px", letterSpacing: ".12em", textTransform: "uppercase", color: SOFT, fontWeight: 500, textAlign: "left", padding: "0 10px 6px", borderBottom: `1px solid ${FAINT}`, borderLeft: `1px solid ${FAINT}` }}>
                Pooled peak hours · {poolWindow ?? "per corridor window"}
              </th>
            </tr>
            <tr style={{ borderBottom: "1.5px solid #1a1917" }}>
              {COLUMNS.map((col) => {
                const active = sort.key === col.key;
                const sortable = col.key !== "spark";
                return (
                  <th
                    key={`${col.key}`}
                    onClick={sortable ? () => toggleSort(col.key as SortKey) : undefined}
                    style={{ fontSize: "10px", letterSpacing: ".16em", textTransform: "uppercase", color: active ? INK : MID, textAlign: col.align, padding: "6px 10px 7px", cursor: sortable ? "pointer" : "default", fontWeight: 500, whiteSpace: "nowrap", userSelect: "none", verticalAlign: "bottom", borderLeft: col.key === FIRST_POOLED ? `1px solid ${FAINT}` : undefined }}
                  >
                    {active ? (sort.dir < 0 ? "↓ " : "↑ ") : ""}
                    {col.label}
                    {col.sub ? <div style={{ letterSpacing: ".08em", textTransform: "none", color: SOFT, fontSize: "9.5px", marginTop: "2px" }}>{col.sub}</div> : null}
                  </th>
                );
              })}
            </tr>
          </thead>
          {sorted.map((r) => {
            const isOpen = open === r.c.id;
            const dim = r.low ? 0.45 : 1;
            return (
              <tbody key={r.c.id} style={{ background: isOpen ? CARD : "transparent" }}>
                <tr onClick={() => toggleOpen(r.c.id)} style={{ borderBottom: `1px solid ${RULE}`, cursor: "pointer", background: r.low ? HATCH : "transparent" }}>
                  <td style={{ padding: "9px 10px 9px 0", verticalAlign: "middle" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: "9px" }}>
                      <span style={{ fontFamily: MONO, fontSize: "10px", color: GHOST, width: "34px", flex: "none" }}>{r.c.code}</span>
                      <span style={{ fontSize: "13.5px", fontWeight: 500 }}>{r.c.name}</span>
                      <span style={{ fontFamily: MONO, fontSize: "10.5px", color: SOFT }}>
                        {r.c.pair_id}
                        {r.c.role === "alternate" ? " · alt" : ""}
                      </span>
                    </div>
                  </td>
                  <td style={num({ fontSize: "15px", fontWeight: 500, color: ttiColor(r.v.tti_tomtom), opacity: r.low ? 0.5 : 1 })}>
                    {fmtNum(r.v.tti_tomtom)}
                    {r.low ? " ◌" : ""}
                  </td>
                  <td style={num({ fontSize: "15px", fontWeight: 500, color: ttiColor(r.v.tti_p5), opacity: r.low ? 0.5 : 1 })}>{fmtNum(r.v.tti_p5)}</td>
                  <td style={{ padding: "6px 10px", width: "104px" }}>
                    <Sparkline tomtom={r.view?.atHour("tti_tomtom", last7, hour) ?? []} p5={r.view?.atHour("tti_p5", last7, hour) ?? []} />
                  </td>
                  <td style={num({ color: deltaColor(r.v.delta_tomtom), opacity: dim })}>{fmtSigned(r.v.delta_tomtom)}</td>
                  <td style={num({ color: deltaColor(r.v.delta_p5), opacity: dim })}>{fmtSigned(r.v.delta_p5)}</td>
                  <td style={num({ fontSize: "12px", color: r.low ? RUST : GHOST })}>{coverageText(r.v.coverage)}</td>
                  {(["bti", "pti_tomtom", "pti_p5"] as const).map((key) => (
                    <PooledCell key={key} p={r.pooled[key]} label={withheldLabel(r.pooled[key], key)} floor={q} first={key === FIRST_POOLED} />
                  ))}
                </tr>
                {isOpen ? (
                  <tr>
                    <td colSpan={COLUMNS.length} style={{ padding: "0 0 22px" }}>
                      <Expanded row={r} days={days} dayIndex={dayIndex} hour={hour} interventions={interventions} floors={floors} />
                    </td>
                  </tr>
                ) : null}
              </tbody>
            );
          })}
        </table>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {sorted.map((r) => {
            const isOpen = open === r.c.id;
            const pv = (p: Pooled) => (p.value == null ? EM_DASH : fmtNum(p.value));
            return (
              <div key={r.c.id} onClick={() => toggleOpen(r.c.id)} style={{ border: `1px solid ${isOpen ? INK : FAINT}`, background: r.low ? "#f7f5f0" : CARD, backgroundImage: r.low ? HATCH : "none", padding: "14px", cursor: "pointer" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "baseline" }}>
                  <div>
                    <div style={{ fontFamily: MONO, fontSize: "10px", color: GHOST }}>{r.c.code}</div>
                    <div style={{ fontSize: "14px", fontWeight: 500, marginTop: "2px" }}>{r.c.name}</div>
                    <div style={{ fontFamily: MONO, fontSize: "10.5px", color: SOFT }}>{r.c.pair_id}{r.c.role === "alternate" ? " · alt" : ""}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontFamily: MONO, fontSize: "30px", fontWeight: 500, letterSpacing: "-.03em", fontVariantNumeric: "tabular-nums", lineHeight: 1, color: ttiColor(r.v.tti_tomtom) }}>{fmtNum(r.v.tti_tomtom)}</div>
                    <div style={{ fontFamily: MONO, fontSize: "14px", color: ttiColor(r.v.tti_p5), marginTop: "3px" }}>{fmtNum(r.v.tti_p5)}</div>
                    <div style={smallCaps}>TTI · TomTom / p5 · {fmtHour(hour)}</div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: "18px", alignItems: "flex-end", marginTop: "12px", flexWrap: "wrap" }}>
                  {([["BTI · pooled", pv(r.pooled.bti), TEXT], ["PTI · pooled", `${pv(r.pooled.pti_tomtom)} / ${pv(r.pooled.pti_p5)}`, TEXT], ["Δ wk", `${fmtSigned(r.v.delta_tomtom)} / ${fmtSigned(r.v.delta_p5)}`, deltaColor(r.v.delta_tomtom)]] as const).map(([k, v, color]) => (
                    <div key={k}>
                      <div style={smallCaps}>{k}</div>
                      <div style={{ fontFamily: MONO, fontSize: "16px", fontVariantNumeric: "tabular-nums", color }}>{v}</div>
                    </div>
                  ))}
                  <div style={{ flex: "1 1 90px", minWidth: "80px" }}>
                    <Sparkline tomtom={r.view?.atHour("tti_tomtom", last7, hour) ?? []} p5={r.view?.atHour("tti_p5", last7, hour) ?? []} />
                  </div>
                </div>
                <div style={{ marginTop: "8px", fontSize: "10.5px", fontFamily: MONO, color: MID, lineHeight: 1.45 }}>
                  {pooledNote(r.c.ledger, r.pooled, q)}
                </div>
                <div style={{ marginTop: "6px", fontSize: "10.5px", fontFamily: MONO, color: r.low ? RUST : GHOST }}>
                  {r.low
                    ? `◌ low confidence at ${fmtHour(hour)} · ${r.v.coverage == null ? "no samples" : `${Math.round((1 - r.v.coverage) * 100)}% samples missing`}, not interpolated`
                    : `${coverageText(r.v.coverage)} sample coverage at ${fmtHour(hour)}`}
                </div>
                {isOpen ? (
                  <div style={{ marginTop: "14px", borderTop: `1px solid ${FAINT}`, paddingTop: "14px" }} onClick={(e) => e.stopPropagation()}>
                    <Expanded row={r} days={days} dayIndex={dayIndex} hour={hour} interventions={interventions} floors={floors} stacked />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <div style={{ marginTop: "18px", paddingTop: "12px", borderTop: `1px solid ${FAINT}`, fontSize: "11.5px", color: MID, maxWidth: "80ch", lineHeight: 1.5 }}>
        Default sort is worst-first on the shrunk index: each corridor’s mean TTI (TomTom basis) over the window is pulled toward the city mean in proportion to how few hourly cells support it, so a thin-sample corridor cannot top the table on noise alone. Both free-flow references are shown in every row. Hourly cells with more than 15% missing samples are hatched and dimmed — degraded, never hidden, never interpolated. BTI and PTI rest on a 95th percentile, which the two to four calls in one hourly cell cannot estimate, so they are computed on all successful peak-hour calls pooled over {poolWindow ?? "each corridor’s trailing window"} and published only from {q} pooled calls. Below that floor the cell shows an em dash, “insufficient samples” and the count against the floor, never a number. The table shows point values; the expanded row gives each with its bootstrap interval ({f.bootstrap_resamples} resamples).
      </div>
    </div>
  );
}

function PooledCell({ p, label, floor, first }: { p: Pooled; label: string; floor: number; first: boolean }) {
  const style = num({ color: TEXT, borderLeft: first ? `1px solid ${FAINT}` : undefined });
  if (p.state === "published") return <td style={style}>{fmtNum(p.value)}</td>;
  const tiny: JSX.CSSProperties = { fontSize: "9.5px", lineHeight: 1.3, color: p.state === "insufficient" ? RUST : MID };
  return (
    <td style={style}>
      <div style={{ color: MID }}>{EM_DASH}</div>
      <div style={tiny}>{label}</div>
      {p.state === "insufficient" ? <div style={tiny}>{fmtCount(p.n, floor)}</div> : null}
    </td>
  );
}

function pooledNote(ledger: CorridorLedger | null | undefined, pooled: Record<PooledKey, Pooled>, floor: number): ComponentChildren {
  if (!ledger) return `BTI · PTI ${EM_DASH} no pooled peak-hour record published`;
  const head = `BTI · PTI pooled over ${ledger.hours}, ${fmtWindow(ledger.window)}`;
  if (pooled.bti.state === "insufficient") {
    return (
      <>
        {head} · <span style={{ color: RUST }}>{insufficientText(ledger.n, floor)}</span>
      </>
    );
  }
  return `${head} · n = ${ledger.n}${pooled.pti_p5.state === "unavailable" ? ` · PTI obs p5 ${EM_DASH} no observed-p5 reference` : ""}`;
}

function Expanded({ row, days, dayIndex, hour, interventions, floors, stacked = false }: {
  row: Row;
  days: string[];
  dayIndex: number;
  hour: number;
  interventions: Intervention[];
  floors: Floors | null;
  stacked?: boolean;
}) {
  const profile = useApi<ProfileResponse>(cache, `/api/corridors/${encodeURIComponent(row.c.id)}/profile`);
  const tomtom = useMemo(() => row.view?.atHour("tti_tomtom", days, hour) ?? days.map(() => null), [row.view, days, hour]);
  const p5 = useMemo(() => row.view?.atHour("tti_p5", days, hour) ?? days.map(() => null), [row.view, days, hour]);
  const markers = useMemo(
    () =>
      interventions
        .filter((iv) => iv.corridor_id === row.c.id)
        .map((iv) => ({ dayIndex: days.indexOf(istDay(iv.effective_at)), label: iv.description }))
        .filter((m) => m.dayIndex >= 0),
    [interventions, row.c.id, days],
  );
  const loaded = profile?.ok ? profile.data : null;
  const pf = resolveFloors(loaded?.floors ?? floors);
  const gated = useMemo(() => (loaded ? gateProfile(loaded.profile, pf) : null), [loaded, pf]);

  const length = row.c.length_meters;
  const note =
    `Coverage ${coverageText(row.v.coverage)} at this hour` +
    (row.low ? "; gaps are drawn as gaps and the trend line breaks where we have nothing to report" : "") +
    `. Free-flow baseline ${fmtMinutes(row.c.free_flow.tomtom_s)} min (TomTom) · ${fmtMinutes(row.c.free_flow.p5_s)} min (observed p5). Payload length ${formatLength(length)}` +
    (length == null ? " — not present in the payload, so no distance is shown and none is estimated." : ".");

  const L = row.c.ledger ?? null;
  const lf = resolveFloors(floors);
  const ledgerDays = L ? windowDays(L.window) : null;
  const pooledBlock = (
    <div>
      <div style={{ ...kicker, marginBottom: "8px" }}>Peak-hour reliability · pooled, not hourly</div>
      {L ? (
        <>
          <div style={{ fontSize: "11.5px", color: TEXT, lineHeight: 1.45, marginBottom: "10px", maxWidth: "52ch" }}>
            Pooled over {fmtWindow(L.window)}{ledgerDays ? ` (${ledgerDays} days)` : ""}: all {L.n} successful calls in {L.hours}. Each statistic is computed once on that pooled distribution and does not move with the scrubbers. Intervals are bootstrap, {lf.bootstrap_resamples} resamples.
          </div>
          <StatList
            items={[
              ["pooled calls", `n = ${L.n} · floors ${lf.p95_min_samples} (p95) / ${lf.central_min_samples} (mean)`],
              ["mean travel time", <PooledStat value={L.tt_mean_s} n={L.n} floor={lf.central_min_samples} text={`${fmtMinutes(L.tt_mean_s, 1)} min`} />],
              ["p95 travel time", <PooledStat value={L.tt_p95_s?.value} n={L.n} floor={lf.p95_min_samples} text={`${fmtMinutesInterval(L.tt_p95_s?.value, L.tt_p95_s?.ci_low, L.tt_p95_s?.ci_high)} min`} />],
              ["BTI", <PooledStat value={L.bti?.value} n={L.n} floor={lf.p95_min_samples} text={fmtInterval(L.bti?.value, L.bti?.ci_low, L.bti?.ci_high)} />],
              ["PTI · TomTom", <PooledStat value={L.pti_tomtom?.value} n={L.n} floor={lf.p95_min_samples} text={fmtInterval(L.pti_tomtom?.value, L.pti_tomtom?.ci_low, L.pti_tomtom?.ci_high)} />],
              ["PTI · obs p5", <PooledStat value={L.pti_p5?.value} n={L.n} floor={lf.p95_min_samples} unavailable="no observed-p5 reference" text={fmtInterval(L.pti_p5?.value, L.pti_p5?.ci_low, L.pti_p5?.ci_high)} />],
            ]}
          />
        </>
      ) : (
        <div style={{ fontSize: "11.5px", color: TEXT, lineHeight: 1.45, maxWidth: "52ch" }}>
          No pooled peak-hour record is published for this corridor yet, so BTI and PTI are withheld rather than estimated.
        </div>
      )}
    </div>
  );

  let profileBody: ComponentChildren;
  if (profile === null) {
    profileBody = <div style={{ height: "150px", fontFamily: MONO, fontSize: "11px", color: GHOST }}>loading profile…</div>;
  } else if (!profile.ok || !loaded || !gated) {
    profileBody = <div style={{ height: "150px", fontFamily: MONO, fontSize: "11px", color: RUST }}>profile unavailable: {profile.ok ? "empty response" : profile.error}</div>;
  } else {
    const p = gated;
    const q = pf.p95_min_samples;
    const i = p.hour.indexOf(hour);
    const at = (col: (number | null)[]) => (i < 0 ? null : (col[i] ?? null));
    const nHour = i < 0 ? null : (p.n_ok[i] ?? null);
    const n5Hour = i < 0 ? null : (p.n_tti_p5?.[i] ?? null);
    const unscheduled = i < 0 || !((p.n_expected[i] ?? 0) > 0);
    const summary = floorSummary(p.n_expected, p.n_ok, q);
    const drawn = p.tti_tomtom_p95.filter((v) => v != null).length;
    profileBody = (
      <>
        <ProfileChart profile={loaded.profile} floors={pf} hour={hour} />
        <div style={{ display: "flex", flexWrap: "wrap", gap: "16px", marginTop: "8px", fontSize: "10.5px", color: MID, fontFamily: MONO }}>
          <span>▮ p25–p75 band</span>
          <span>— p95 (gaps: insufficient samples)</span>
          <span>· median, TomTom</span>
          <span style={{ color: GHOST }}>— median, observed p5</span>
        </div>
        <div style={{ marginTop: "8px", fontSize: "11.5px", color: TEXT, lineHeight: 1.45, maxWidth: "52ch" }}>
          {loaded.window
            ? `Pooled over ${fmtWindow(loaded.window)}: ${loaded.pooling || "all successful calls at each local hour across the window"}.`
            : "The profile’s pooling window is not published."}
          {` The p95 line is drawn at ${drawn} of ${summary.scheduled} scheduled hours; ${summary.below} ${summary.below === 1 ? "hour is" : "hours are"} below the ${q}-call floor and left as gaps, not estimated. The median band needs ${pf.central_min_samples} calls an hour.`}
          {summary.unscheduled > 0 ? ` ${summary.unscheduled} hours have no scheduled slots.` : ""}
        </div>
        <div style={{ marginTop: "8px" }}>
          <StatList
            items={[
              [`p95 TTI TomTom · ${fmtHour(hour)}`, <PooledStat value={at(p.tti_tomtom_p95)} n={nHour} floor={q} unscheduled={unscheduled} text={fmtInterval(at(p.tti_tomtom_p95), at(p.tti_tomtom_p95_ci_low), at(p.tti_tomtom_p95_ci_high))} />],
              [`p95 TTI obs p5 · ${fmtHour(hour)}`, <PooledStat value={at(p.tti_p5_p95)} n={n5Hour} floor={q} unscheduled={unscheduled} unavailable="no observed-p5 reference" text={fmtInterval(at(p.tti_p5_p95), at(p.tti_p5_p95_ci_low), at(p.tti_p5_p95_ci_high))} />],
              [`p95 travel time · ${fmtHour(hour)}`, <PooledStat value={at(p.tt_p95_s)} n={nHour} floor={q} unscheduled={unscheduled} text={`${fmtMinutesInterval(at(p.tt_p95_s), at(p.tt_p95_ci_low), at(p.tt_p95_ci_high))} min`} />],
              [`BTI · ${fmtHour(hour)}`, <PooledStat value={at(p.bti)} n={nHour} floor={q} unscheduled={unscheduled} text={fmtInterval(at(p.bti), at(p.bti_ci_low), at(p.bti_ci_high))} />],
              [`pooled calls · ${fmtHour(hour)}`, unscheduled ? `${EM_DASH} no scheduled slots` : `${nHour ?? EM_DASH} TomTom · ${n5Hour ?? EM_DASH} obs p5`],
            ]}
          />
        </div>
      </>
    );
  }

  const profileBlock = (
    <div>
      <div style={{ ...kicker, marginBottom: "8px" }}>24-hour profile · median band, p95 line</div>
      {profileBody}
    </div>
  );
  const trendBlock = (
    <div>
      <div style={{ ...kicker, marginBottom: "8px" }}>90-day trend at {fmtHour(hour)}</div>
      <TrendChart days={days} tomtom={tomtom} p5={p5} dayIndex={dayIndex} markers={markers} />
      <div style={{ marginTop: "8px", fontSize: "11.5px", color: TEXT, lineHeight: 1.45, maxWidth: "46ch" }}>{note}</div>
    </div>
  );

  if (stacked) {
    return (
      <div onClick={(e) => e.stopPropagation()}>
        {pooledBlock}
        <div style={{ marginTop: "14px" }}>{profileBlock}</div>
        <div style={{ marginTop: "14px" }}>{trendBlock}</div>
      </div>
    );
  }
  return (
    <div style={{ background: CARD, border: `1px solid ${FAINT}`, padding: "18px 20px", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: "26px" }}>
      {pooledBlock}
      {profileBlock}
      {trendBlock}
    </div>
  );
}
