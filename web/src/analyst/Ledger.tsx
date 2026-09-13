import type { JSX } from "preact";
import { useMemo, useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { Corridor, Intervention, ProfileResponse } from "../api/types";
import { ProfileChart } from "../charts/ProfileChart";
import { Sparkline } from "../charts/Sparkline";
import { TrendChart } from "../charts/TrendChart";
import { CARD, FAINT, GHOST, HATCH, INK, MID, MONO, RAMP_TTI_TEXT, RULE, RUST, SOFT, TEAL, TEXT, ramp } from "../lib/color";
import { addDays, fmtHour, fmtMinutes, fmtNum, fmtSigned, istDay } from "../lib/format";
import { EM_DASH, formatLength } from "../lib/route";
import { cache } from "./cache";
import { SectionHead, kicker, smallCaps } from "./common";
import type { SeriesView } from "./series";

type ValueKey = "tti_tomtom" | "tti_p5" | "bti" | "pti_tomtom" | "pti_p5" | "delta_tomtom" | "delta_p5" | "coverage";
type SortKey = "shrunk" | "name" | ValueKey;

interface Row {
  c: Corridor;
  view: SeriesView | undefined;
  v: Record<ValueKey, number | null>;
  low: boolean;
  worseness: number | null;
}

const COLUMNS: { key: SortKey | "spark"; label: string; sub?: string; align: "left" | "right" }[] = [
  { key: "name", label: "Corridor", align: "left" },
  { key: "tti_tomtom", label: "TTI", sub: "TomTom", align: "right" },
  { key: "tti_p5", label: "TTI", sub: "obs p5", align: "right" },
  { key: "bti", label: "BTI", align: "right" },
  { key: "pti_tomtom", label: "PTI", sub: "TomTom", align: "right" },
  { key: "pti_p5", label: "PTI", sub: "obs p5", align: "right" },
  { key: "spark", label: "7-day", align: "left" },
  { key: "delta_tomtom", label: "Δ wk", sub: "TomTom", align: "right" },
  { key: "delta_p5", label: "Δ wk", sub: "obs p5", align: "right" },
  { key: "coverage", label: "Samples", align: "right" },
];

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
}

export function Ledger({ corridors, views, days, dayIndex, hour, narrow, interventions }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "shrunk", dir: -1 });
  const [open, setOpen] = useState<string | null>(null);
  const day = days[dayIndex]!;

  const rows = useMemo<Row[]>(() => {
    return corridors.map((c) => {
      const view = views.get(c.id);
      const at = (k: Parameters<SeriesView["value"]>[0]) => view?.value(k, day, hour) ?? null;
      const rank = c.rankings.tti_tomtom?.rank ?? null;
      return {
        c,
        view,
        v: {
          tti_tomtom: at("tti_tomtom"), tti_p5: at("tti_p5"), bti: at("bti"),
          pti_tomtom: at("pti_tomtom"), pti_p5: at("pti_p5"),
          delta_tomtom: at("tti_tomtom_delta_wk"), delta_p5: at("tti_p5_delta_wk"),
          coverage: view?.coverage(day, hour) ?? null,
        },
        low: view ? view.lowConfidence(day, hour) : true,
        worseness: rank == null ? null : -rank,
      };
    });
  }, [corridors, views, day, hour]);

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

  return (
    <div>
      <SectionHead
        title="Corridor ledger"
        sub={`${corridors.length} declared corridors, sorted worst-first on the shrunk index. Values at ${fmtHour(hour)}. Click a row for its 24-hour profile and 90-day trend.`}
        right={
          <div style={{ fontFamily: MONO, fontSize: "11px", color: MID, textAlign: "right", lineHeight: 1.5 }}>
            <div>TTI mean ÷ free-flow, TomTom and observed p5 · BTI (p95−mean)÷mean</div>
            <div>PTI p95 ÷ free-flow, both references · Δ vs same hour last week</div>
          </div>
        }
      />

      {!narrow ? (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1.5px solid #1a1917" }}>
              {COLUMNS.map((col) => {
                const active = sort.key === col.key;
                const sortable = col.key !== "spark";
                return (
                  <th
                    key={`${col.key}`}
                    onClick={sortable ? () => toggleSort(col.key as SortKey) : undefined}
                    style={{ fontSize: "10px", letterSpacing: ".16em", textTransform: "uppercase", color: active ? INK : MID, textAlign: col.align, padding: "0 10px 7px", cursor: sortable ? "pointer" : "default", fontWeight: 500, whiteSpace: "nowrap", userSelect: "none", verticalAlign: "bottom" }}
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
                  <td style={num({ opacity: dim, color: TEXT })}>{fmtNum(r.v.bti)}</td>
                  <td style={num({ opacity: dim, color: TEXT })}>{fmtNum(r.v.pti_tomtom)}</td>
                  <td style={num({ opacity: dim, color: TEXT })}>{fmtNum(r.v.pti_p5)}</td>
                  <td style={{ padding: "6px 10px", width: "104px" }}>
                    <Sparkline tomtom={r.view?.atHour("tti_tomtom", last7, hour) ?? []} p5={r.view?.atHour("tti_p5", last7, hour) ?? []} />
                  </td>
                  <td style={num({ color: deltaColor(r.v.delta_tomtom), opacity: dim })}>{fmtSigned(r.v.delta_tomtom)}</td>
                  <td style={num({ color: deltaColor(r.v.delta_p5), opacity: dim })}>{fmtSigned(r.v.delta_p5)}</td>
                  <td style={num({ fontSize: "12px", color: r.low ? RUST : GHOST })}>{coverageText(r.v.coverage)}</td>
                </tr>
                {isOpen ? (
                  <tr>
                    <td colSpan={COLUMNS.length} style={{ padding: "0 0 22px" }}>
                      <Expanded row={r} days={days} dayIndex={dayIndex} hour={hour} interventions={interventions} />
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
                    <div style={smallCaps}>TTI · TomTom / p5</div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: "18px", alignItems: "flex-end", marginTop: "12px", flexWrap: "wrap" }}>
                  {([["BTI", fmtNum(r.v.bti), TEXT], ["PTI", `${fmtNum(r.v.pti_tomtom)} / ${fmtNum(r.v.pti_p5)}`, TEXT], ["Δ wk", `${fmtSigned(r.v.delta_tomtom)} / ${fmtSigned(r.v.delta_p5)}`, deltaColor(r.v.delta_tomtom)]] as const).map(([k, v, color]) => (
                    <div key={k}>
                      <div style={smallCaps}>{k}</div>
                      <div style={{ fontFamily: MONO, fontSize: "16px", fontVariantNumeric: "tabular-nums", color }}>{v}</div>
                    </div>
                  ))}
                  <div style={{ flex: "1 1 90px", minWidth: "80px" }}>
                    <Sparkline tomtom={r.view?.atHour("tti_tomtom", last7, hour) ?? []} p5={r.view?.atHour("tti_p5", last7, hour) ?? []} />
                  </div>
                </div>
                <div style={{ marginTop: "10px", fontSize: "10.5px", fontFamily: MONO, color: r.low ? RUST : GHOST }}>
                  {r.low
                    ? `◌ low confidence · ${r.v.coverage == null ? "no samples" : `${Math.round((1 - r.v.coverage) * 100)}% samples missing`}, not interpolated`
                    : `${coverageText(r.v.coverage)} sample coverage`}
                </div>
                {isOpen ? (
                  <div style={{ marginTop: "14px", borderTop: `1px solid ${FAINT}`, paddingTop: "14px" }} onClick={(e) => e.stopPropagation()}>
                    <Expanded row={r} days={days} dayIndex={dayIndex} hour={hour} interventions={interventions} stacked />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <div style={{ marginTop: "18px", paddingTop: "12px", borderTop: `1px solid ${FAINT}`, fontSize: "11.5px", color: MID, maxWidth: "80ch", lineHeight: 1.5 }}>
        Default sort is worst-first on the shrunk index: each corridor’s mean TTI (TomTom basis) over the window is pulled toward the city mean in proportion to how few hourly cells support it, so a thin-sample corridor cannot top the table on noise alone. Both free-flow references are shown in every row. Cells with more than 15% missing samples are hatched and dimmed — degraded, never hidden, never interpolated.
      </div>
    </div>
  );
}

function Expanded({ row, days, dayIndex, hour, interventions, stacked = false }: {
  row: Row;
  days: string[];
  dayIndex: number;
  hour: number;
  interventions: Intervention[];
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
  const length = row.c.length_meters;
  const note =
    `Coverage ${coverageText(row.v.coverage)} at this hour` +
    (row.low ? "; gaps are drawn as gaps and the trend line breaks where we have nothing to report" : "") +
    `. Free-flow baseline ${fmtMinutes(row.c.free_flow.tomtom_s)} min (TomTom) · ${fmtMinutes(row.c.free_flow.p5_s)} min (observed p5). Payload length ${formatLength(length)}` +
    (length == null ? " — not present in the payload, so no distance is shown and none is estimated." : ".");

  const profileBlock = (
    <div>
      <div style={{ ...kicker, marginBottom: "8px" }}>24-hour profile · median band, p95 line</div>
      {profile === null ? (
        <div style={{ height: "150px", fontFamily: MONO, fontSize: "11px", color: GHOST }}>loading profile…</div>
      ) : profile.ok ? (
        <ProfileChart profile={profile.data.profile} hour={hour} />
      ) : (
        <div style={{ height: "150px", fontFamily: MONO, fontSize: "11px", color: RUST }}>profile unavailable: {profile.error}</div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "16px", marginTop: "8px", fontSize: "10.5px", color: MID, fontFamily: MONO }}>
        <span>▮ p25–p75 band</span>
        <span>— p95</span>
        <span>· median, TomTom</span>
        <span style={{ color: GHOST }}>— median, observed p5</span>
      </div>
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
        {profileBlock}
        <div style={{ marginTop: "14px" }}>{trendBlock}</div>
      </div>
    );
  }
  return (
    <div style={{ background: CARD, border: `1px solid ${FAINT}`, padding: "18px 20px", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: "26px" }}>
      {profileBlock}
      {trendBlock}
    </div>
  );
}
