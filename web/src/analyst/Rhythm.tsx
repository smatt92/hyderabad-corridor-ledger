import { useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { Corridor, HeatmapResponse, Window } from "../api/types";
import { ANALYST_RHYTHM, RhythmMatrix, extent } from "../encodings/RhythmMatrix";
import { LegendBar } from "../encodings/LegendBar";
import { FAINT, MID, MONO, RAMP_DEG, RUST, TEXT } from "../lib/color";
import { gateMatrix, resolveFloors } from "../lib/floors";
import { fmtCoverage, fmtHour, fmtMinutes, fmtNum, fmtWindow, parseDay } from "../lib/format";
import { EM_DASH } from "../lib/route";
import { cache } from "./cache";
import { BASIS_LABEL, type Basis, Notice, PooledStat, SectionHead, Select, StatList, kicker } from "./common";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

interface Cell {
  dow: number;
  hour: number;
  v: number;
}

function extremes(matrix: (number | null)[][]): { worst: Cell | null; best: Cell | null } {
  const cells: Cell[] = [];
  matrix.forEach((row, dow) => row.forEach((v, hour) => v != null && cells.push({ dow, hour, v })));
  if (!cells.length) return { worst: null, best: null };
  const worst = cells.reduce((a, b) => (b.v > a.v ? b : a));
  const best = cells.reduce((a, b) => (b.v < a.v ? b : a));
  return { worst, best };
}

function windowOf(w: HeatmapResponse["window"] | undefined): Window | null {
  return w && typeof w.start === "string" && typeof w.end === "string" ? { start: w.start, end: w.end } : null;
}

export function Rhythm({ corridors, day, hour }: { corridors: Corridor[]; day: string; hour: number }) {
  const [corridorId, setCorridorId] = useState(corridors[0]?.id ?? "");
  const [basis, setBasis] = useState<Basis>("tomtom");
  const corridor = corridors.find((c) => c.id === corridorId) ?? corridors[0];
  const res = useApi<HeatmapResponse>(cache, corridor ? `/api/corridors/${encodeURIComponent(corridor.id)}/heatmap` : null);
  const dow = parseDay(day).getUTCDay();
  const loaded = res?.ok ? res.data : null;
  const window = windowOf(loaded?.window);
  const central = resolveFloors(loaded?.floors).central_min_samples;

  const controls = (
    <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", alignItems: "center" }}>
      <Select label="Corridor" value={corridor?.id ?? ""} options={corridors.map((c) => ({ value: c.id, label: `${c.code}  ${c.name}` }))} onChange={setCorridorId} />
      <Select label="Free-flow" value={basis} options={[{ value: "tomtom", label: "TomTom" }, { value: "p5", label: "Observed p5" }]} onChange={(v) => setBasis(v as Basis)} />
    </div>
  );
  const head = (
    <SectionHead
      title="Weekly rhythm"
      sub={`Median TTI of all successful calls at each weekday and hour, pooled over ${window ? fmtWindow(window) : "the read window"}, against ${BASIS_LABEL[basis]}. A median is published from ${central} pooled calls in a cell. The hour you leave matters more than the route you pick.`}
      right={controls}
    />
  );
  if (!corridor) return <div>{head}</div>;
  if (res === null) return <div>{head}<div style={{ fontFamily: MONO, fontSize: "12px", color: MID }}>loading…</div></div>;
  if (!res.ok || !loaded) {
    return (
      <div>
        {head}
        <Notice kicker="Degraded" title="Rhythm matrix unavailable">The read API returned: {res.ok ? "an empty response" : res.error}. Nothing is drawn rather than a guess.</Notice>
      </div>
    );
  }

  const counts = loaded.n_ok ?? undefined;
  const matrix = gateMatrix(basis === "tomtom" ? loaded.tti_tomtom_p50 : loaded.tti_p5_p50, counts, central);
  const range = extent(matrix);
  const { worst, best } = extremes(matrix);
  const here = matrix[dow]?.[hour] ?? null;
  const nHere = counts?.[dow]?.[hour] ?? null;
  let withCalls = 0;
  let below = 0;
  counts?.forEach((row) => row.forEach((n) => {
    if (n != null && n > 0) {
      withCalls++;
      if (n < central) below++;
    }
  }));
  const cellLabel = `${DAYS[dow]!.slice(0, 3)} ${fmtHour(hour)}`;
  const readout =
    (worst && best
      ? `On ${corridor.name} the worst published hour of the week is ${DAYS[worst.dow]} ${fmtHour(worst.hour)} (median TTI ${fmtNum(worst.v)}); the lightest is ${DAYS[best.dow]} ${fmtHour(best.hour)} (${fmtNum(best.v)}).`
      : "No hour-weekday cell on this corridor has enough pooled calls to publish a median yet.") +
    ` Hatched cells have fewer than ${central} pooled calls — insufficient samples — and plain dashed cells have none. Neither is estimated.`;

  let hereValue;
  if (!counts) hereValue = here == null ? `${EM_DASH} not published` : fmtNum(here);
  else if (!(nHere != null && nHere > 0)) hereValue = `${EM_DASH} no calls pooled in this cell`;
  else hereValue = <PooledStat value={here} n={nHere} floor={central} text={fmtNum(here)} />;

  return (
    <div>
      {head}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.5fr) minmax(280px,1fr)", gap: "28px", alignItems: "start" }}>
        <div style={{ minWidth: 0 }}>
          <RhythmMatrix matrix={matrix} counts={counts} floor={central} style={ANALYST_RHYTHM} highlight={{ dow, hour }} />
          <div style={{ marginTop: "6px", fontSize: "11.5px", color: TEXT, lineHeight: 1.5 }}>
            {window ? `Pooled over ${fmtWindow(window)}: ` : "Pooling window not published: "}all successful calls at each weekday and hour, one median per cell.
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "46ch" }}>
          <div>
            <div style={{ ...kicker, marginBottom: "8px" }}>Scale · median TTI</div>
            <LegendBar stops={RAMP_DEG} labels={[range ? fmtNum(range[0]) : "low", "", "", "", range ? fmtNum(range[1]) : "high"]} />
            <div style={{ marginTop: "6px", fontSize: "11px", color: MID, lineHeight: 1.5 }}>
              Lightness is monotonic, so the scale stays ordered under deuteranopia and in greyscale print. Colour encodes magnitude only. Hatched dashed cell: insufficient samples, fewer than {central} pooled calls. Plain dashed cell: no calls.
            </div>
          </div>
          <div style={{ borderTop: `1px solid ${FAINT}`, paddingTop: "14px" }}>
            <div style={{ ...kicker, marginBottom: "8px" }}>Read-out</div>
            <div style={{ fontSize: "13px", lineHeight: 1.55, color: TEXT }}>{readout}</div>
          </div>
          <div style={{ borderTop: `1px solid ${FAINT}`, paddingTop: "14px" }}>
            <StatList
              items={[
                ["corridor id", corridor.code ?? corridor.id],
                ["pair id", corridor.pair_id ?? EM_DASH],
                ["role", corridor.role ?? EM_DASH],
                ["length_meters", corridor.length_meters == null ? EM_DASH : String(corridor.length_meters)],
                ["free-flow", `${fmtMinutes(corridor.free_flow.tomtom_s)} min TomTom · ${fmtMinutes(corridor.free_flow.p5_s)} min p5`],
                ["pooling window", window ? fmtWindow(window) : EM_DASH],
                [`median TTI ${cellLabel}`, hereValue],
                [`pooled calls ${cellLabel}`, nHere == null ? EM_DASH : `n = ${nHere}`],
                ["cells below floor", counts ? `${below} of ${withCalls} cells with calls` : EM_DASH],
                ["coverage", fmtCoverage(corridor.missingness_rate)],
              ]}
            />
            {corridor.low_confidence ? (
              <div style={{ marginTop: "8px", fontFamily: MONO, fontSize: "10.5px", color: RUST }}>◌ low confidence · more than 15% of samples missing</div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
