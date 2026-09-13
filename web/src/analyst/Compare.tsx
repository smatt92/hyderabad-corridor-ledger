import { useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { CompareResponse, CompareSide, Corridor, Floors, Window } from "../api/types";
import { SpreadBand } from "../charts/SpreadBand";
import { AdvantageStrip } from "../encodings/AdvantageStrip";
import { NO_LEAD_REASON, byHour, readAdvantage } from "../lib/advantage";
import { CARD, FAINT, HATCH, INK, MID, MONO, RUST, SOFT, TEXT } from "../lib/color";
import { NO_INTERVAL_REASON, gate, gateOne, meetsFloor, resolveFloors } from "../lib/floors";
import {
  fmtCount, fmtCoverage, fmtDay, fmtHour, fmtInt, fmtMinutes, fmtNum, fmtPooled, fmtSigned, fmtWindow, insufficientText,
  windowDays,
} from "../lib/format";
import { EM_DASH, formatLength, mapsHandoffUrl } from "../lib/route";
import { cache } from "./cache";
import { Notice, PooledStat, SectionHead, Select, StatList, kicker, smallCaps } from "./common";

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const big = { fontFamily: MONO, fontSize: "40px", fontWeight: 500, letterSpacing: "-.03em", lineHeight: 1, fontVariantNumeric: "tabular-nums" };

/** One side's pooled values by hour, each gated by its floor, and the readings at the selected hour. */
function sideAt(side: CompareSide, hour: number, floors: Floors) {
  const p = side.profile;
  const q = floors.p95_min_samples;
  const n = byHour(p.hour, p.n_ok);
  const at = (col: (number | null)[]) => byHour(p.hour, col)[hour] ?? null;
  const nNow = n[hour] ?? null;
  const p95 = gate(byHour(p.hour, p.tt_p95_s), n, q);
  const median = gate(byHour(p.hour, p.tt_p50_s), n, floors.central_min_samples);
  return {
    n,
    nNow,
    median,
    p95,
    medianNow: median[hour] ?? null,
    p95Now: p95[hour] ?? null,
    bti: gateOne(at(p.bti), nNow, q),
    low: byHour(p.hour, p.low_confidence)[hour] ?? true,
  };
}

const minutes = (v: (number | null)[]) => v.map((s) => (s == null ? null : s / 60));
const perMinute = (s: number | null) => (s == null ? null : s / 60);

function BigStat({ label, value, unit, detail, n, floor }: {
  label: string;
  value: string | null;
  unit?: string;
  detail: string;
  n: number | null;
  floor: number;
}) {
  const withheld = value === null;
  return (
    <div>
      <div style={smallCaps}>{label}</div>
      <div style={big}>
        {withheld ? EM_DASH : value}
        {!withheld && unit ? <span style={{ fontSize: "15px", color: MID }}> {unit}</span> : null}
      </div>
      <div style={{ fontFamily: MONO, fontSize: "10.5px", marginTop: "5px", color: withheld ? RUST : MID, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
        {withheld ? (meetsFloor(n, floor) ? "not published" : `insufficient samples · ${fmtCount(n, floor)}`) : detail}
      </div>
    </div>
  );
}

export function Compare({ corridors, hour, windowEnd }: { corridors: Corridor[]; hour: number; windowEnd: string }) {
  const primaries = corridors.filter((c) => c.role === "primary" && c.pair_id);
  const [pairId, setPairId] = useState(primaries[0]?.pair_id ?? "");
  const res = useApi<CompareResponse>(cache, pairId ? `/api/pairs/${encodeURIComponent(pairId)}/compare?hour=${hour}` : null);

  const head = (
    <SectionHead
      title="Route comparison"
      sub="One corridor against its paired alternate, at the scrubber hour. The question is not which is shorter — it is which one you can plan around."
      right={<Select label="Pair" value={pairId} options={primaries.map((c) => ({ value: c.pair_id!, label: `${c.pair_id}  ${c.name}` }))} onChange={setPairId} />}
    />
  );
  const footnote = (window: Window | null) => (
    <div style={{ marginTop: "14px", fontSize: "11.5px", color: MID, maxWidth: "88ch", lineHeight: 1.5 }}>
      We are not a live routing product. Every figure here is computed on calls pooled over {window ? fmtWindow(window) : `the window ending ${fmtDay(windowEnd)}`} at the selected hour, for two separately declared corridors. Alternates are declared in the payload and measured in their own right — never derived from geometry. The Maps button passes the corridor’s origin and destination only, with no intermediate points; if you want the fastest road right now, that is Google’s job, and it is a different question.
    </div>
  );

  if (primaries.length === 0) {
    return <div>{head}<Notice kicker="No pairs" title="No corridor pairs are declared">Nothing to compare until pairs are declared.</Notice></div>;
  }
  if (res === null) return <div>{head}<div style={{ fontFamily: MONO, fontSize: "12px", color: MID }}>loading…</div></div>;
  if (!res.ok) {
    return <div>{head}<Notice kicker="Degraded" title="Comparison unavailable">The read API returned: {res.error}.</Notice>{footnote(null)}</div>;
  }

  const data = res.data;
  const primary = data.primary;
  const window = data.window ?? null;
  const title = `${data.pair_id} · ${primary.origin.name ?? "origin"} → ${primary.destination.name ?? "destination"}`;
  if (!data.alternate) {
    return (
      <div>
        {head}
        <Notice kicker="No measured alternate" title={title}>
          No measured alternate for this corridor. Pair {data.pair_id} declares one corridor only; we do not construct a second route to compare it against.
        </Notice>
        {footnote(window)}
      </div>
    );
  }

  const f = resolveFloors(data.floors);
  const q = f.p95_min_samples;
  const sides = [primary, data.alternate] as const;
  const values = sides.map((s) => sideAt(s, hour, f));
  const A = data.advantage;
  const nulls = HOURS.map(() => null);
  const advRaw = A ? byHour(A.hour, A.advantage_p95_s) : nulls;
  const pN = A ? byHour(A.hour, A.primary_n) : values[0]!.n;
  const aN = A ? byHour(A.hour, A.alternate_n) : values[1]!.n;
  const readings = HOURS.map((h) => readAdvantage(advRaw[h] ?? null, pN[h] ?? null, aN[h] ?? null, q));
  const advantage = readings.map((r) => r.value);
  const advLow = A ? byHour(A.hour, A.low_confidence).map((v) => v ?? true) : HOURS.map(() => true);

  const reading = readings[hour]!;
  const adv = reading.value;
  const pn = pN[hour] ?? null;
  const an = aN[hour] ?? null;
  const advNum = adv == null ? EM_DASH : `${fmtSigned(perMinute(adv), 1)} min`;
  const counts = `primary ${fmtCount(pn, q)} · alternate ${fmtCount(an, q)}`;
  const insufficientHours = readings.filter((r) => r.kind === "insufficient").length;
  const noCallHours = readings.filter((r) => r.kind === "no_calls").length;
  const belowSides = [!meetsFloor(pn, q) ? "the primary corridor" : null, !meetsFloor(an, q) ? "the declared alternate" : null].filter((s): s is string => s != null);

  let advText: string;
  switch (reading.kind) {
    case "insufficient":
      advText = `No advantage is published at ${fmtHour(hour)}: ${belowSides.join(" and ")} ${belowSides.length > 1 ? "have" : "has"} fewer than ${q} pooled calls at this hour, too few for a 95th percentile. That is insufficient samples, not a tie.`;
      break;
    case "no_calls":
      advText = `Neither corridor has pooled calls at ${fmtHour(hour)}, so nothing is published.`;
      break;
    case "unpublished":
      advText = `No p95 travel time is published for both corridors at ${fmtHour(hour)}.`;
      break;
    case "published":
      advText =
        `At ${fmtHour(hour)} the primary corridor’s p95 travel time minus the declared alternate’s is ${advNum}, a point estimate from ${fmtInt(pn)} and ${fmtInt(an)} pooled calls. ` +
        "A positive value means the alternate’s p95 is lower; the sign alone does not make either corridor the more reliable one.";
      break;
  }

  /** Withheld states only: a published hour carries no badge, because no corridor is marked more reliable. */
  const badge = (i: number): string | null => {
    if (reading.kind === "published") return null;
    if (reading.kind === "insufficient") return meetsFloor([pn, an][i], q) ? "OTHER CORRIDOR BELOW FLOOR" : "INSUFFICIENT SAMPLES";
    return "NO P95 AT THIS HOUR";
  };
  const days = windowDays(window);

  return (
    <div>
      {head}
      <div style={{ border: `1.5px solid ${INK}`, background: CARD }}>
        <div style={{ padding: "20px 24px", borderBottom: `1px solid ${FAINT}`, display: "flex", flexWrap: "wrap", gap: "18px", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ fontSize: "16px", fontWeight: 500 }}>{title}</div>
          <div style={{ fontFamily: MONO, fontSize: "12px", color: MID, fontVariantNumeric: "tabular-nums" }}>
            {fmtHour(hour)} · pooled {window ? fmtWindow(window) : `to ${fmtDay(windowEnd)}`}
          </div>
        </div>
        <div style={{ padding: "12px 24px", borderBottom: `1px solid ${FAINT}`, fontSize: "11.5px", color: TEXT, lineHeight: 1.5 }}>
          {window ? `Pooled over ${fmtWindow(window)}${days ? ` (${days} days)` : ""}: ` : "Pooling window not published: "}
          all successful calls at each local hour on each corridor, every day in the window. p95 and BTI are published from {q} pooled calls at the hour and medians from {f.central_min_samples}. {NO_INTERVAL_REASON}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(290px,1fr))" }}>
          {sides.map((s, i) => {
            const v = values[i]!;
            const b = badge(i);
            return (
              <div key={s.id} style={{ padding: "22px 24px", borderRight: i === 0 ? `1px solid ${FAINT}` : "none", background: v.low ? HATCH : "transparent" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "12px", marginBottom: "16px" }}>
                  <div>
                    <div style={kicker}>{i === 0 ? `Primary corridor · ${s.code}` : `Declared alternate · ${s.code}`}</div>
                    <div style={{ fontSize: "15px", fontWeight: 500, marginTop: "3px" }}>{s.origin.name} → {s.destination.name}</div>
                    <div style={{ fontFamily: MONO, fontSize: "11px", color: SOFT }}>
                      pair {s.pair_id} · length {formatLength(s.length_meters)} · free-flow {fmtMinutes(s.free_flow.tomtom_s)} min
                    </div>
                  </div>
                  {b ? (
                    <div style={{ fontFamily: MONO, fontSize: "10px", letterSpacing: ".1em", padding: "5px 8px", whiteSpace: "nowrap", border: `1px solid ${FAINT}`, color: reading.kind === "insufficient" && !meetsFloor([pn, an][i], q) ? RUST : MID }}>
                      {b}
                    </div>
                  ) : null}
                </div>
                <div style={{ display: "flex", gap: "26px", flexWrap: "wrap", alignItems: "flex-start" }}>
                  <BigStat label="Median" value={v.medianNow == null ? null : fmtMinutes(v.medianNow)} unit="min" detail={`n = ${fmtInt(v.nNow)} pooled calls`} n={v.nNow} floor={f.central_min_samples} />
                  <BigStat label="p95 · plan for this" value={v.p95Now == null ? null : fmtMinutes(v.p95Now, 1)} unit="min" detail={`n = ${fmtInt(v.nNow)} pooled calls`} n={v.nNow} floor={q} />
                  <BigStat label="BTI" value={v.bti == null ? null : v.bti.toFixed(2)} detail={`n = ${fmtInt(v.nNow)} pooled calls`} n={v.nNow} floor={q} />
                </div>
                <div style={{ marginTop: "18px" }}>
                  <div style={{ ...smallCaps, marginBottom: "6px" }}>Spread by hour · median to p95 · gaps below floor</div>
                  <SpreadBand median={minutes(v.median)} p95={minutes(v.p95)} hour={hour} />
                </div>
                <div style={{ marginTop: "18px", paddingTop: "14px", borderTop: `1px solid ${FAINT}`, fontSize: "10.5px", color: SOFT, lineHeight: 1.45 }}>
                  {v.p95Now == null ? (
                    <span style={{ color: meetsFloor(v.nNow, q) ? SOFT : RUST }}>
                      {meetsFloor(v.nNow, q) ? `${EM_DASH} no p95 published at this hour` : insufficientText(v.nNow, q)}; nothing is estimated in its place.
                    </span>
                  ) : (
                    `Budget ${fmtMinutes(v.p95Now, 1)} min to arrive on time 19 trips out of 20.`
                  )}
                  {v.low ? <div style={{ color: RUST, fontFamily: MONO, marginTop: "4px" }}>◌ low confidence at this hour · more than 15% of samples missing, not interpolated</div> : null}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ borderTop: `1.5px solid ${INK}`, padding: "22px 24px", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: "26px", alignItems: "start" }}>
          <div>
            <div style={{ ...kicker, marginBottom: "8px" }}>Reliability advantage at this hour</div>
            <div style={{ fontFamily: MONO, fontSize: "56px", lineHeight: 0.95, letterSpacing: "-.04em", fontWeight: 500, fontVariantNumeric: "tabular-nums", color: adv == null ? MID : INK }}>{advNum}</div>
            <div style={{ fontFamily: MONO, fontSize: "11px", marginTop: "8px", lineHeight: 1.5, fontVariantNumeric: "tabular-nums", color: reading.kind === "insufficient" ? RUST : MID }}>
              {adv != null ? (
                <>
                  <div>primary p95 − alternate p95 · point estimate</div>
                  <div>{counts}</div>
                </>
              ) : reading.kind === "insufficient" ? (
                <>
                  <div>{EM_DASH} insufficient samples</div>
                  <div>{counts}</div>
                </>
              ) : reading.kind === "no_calls" ? (
                <div>{EM_DASH} no calls pooled at this hour on either corridor</div>
              ) : (
                <>
                  <div>{EM_DASH} not published</div>
                  <div>{counts}</div>
                </>
              )}
            </div>
            <div style={{ fontSize: "13px", color: TEXT, marginTop: "8px", maxWidth: "38ch", lineHeight: 1.5 }}>{advText}</div>
          </div>
          <div>
            <div style={{ ...kicker, marginBottom: "8px" }}>Advantage across the day</div>
            <AdvantageStrip values={advantage.map(perMinute)} kinds={readings.map((r) => r.kind)} lowConfidence={advLow} cursor={hour} />
            <div style={{ fontSize: "10.5px", color: SOFT, marginTop: "6px", lineHeight: 1.45 }}>
              Bars are each hour’s primary p95 minus alternate p95, a point estimate: above the rule the alternate’s p95 is lower, below it the primary’s. {NO_LEAD_REASON} Rust dotted marks are hours where either corridor has fewer than {q} pooled calls — insufficient samples, not ties ({insufficientHours} {insufficientHours === 1 ? "hour" : "hours"}). Grey dotted marks have no calls pooled ({noCallHours}).
            </div>
          </div>
          <StatList
            items={[
              ["hour", fmtHour(hour)],
              ["pair id", data.pair_id],
              ["pooling window", window ? fmtWindow(window) : EM_DASH],
              ["primary p95", <PooledStat value={values[0]!.p95Now} n={values[0]!.nNow} floor={q} text={fmtPooled(`${fmtMinutes(values[0]!.p95Now, 1)} min`, values[0]!.nNow, "pooled calls")} />],
              ["alternate p95", <PooledStat value={values[1]!.p95Now} n={values[1]!.nNow} floor={q} text={fmtPooled(`${fmtMinutes(values[1]!.p95Now, 1)} min`, values[1]!.nNow, "pooled calls")} />],
              ["BTI primary", <PooledStat value={values[0]!.bti} n={values[0]!.nNow} floor={q} text={fmtPooled(fmtNum(values[0]!.bti), values[0]!.nNow, "pooled calls")} />],
              ["BTI alternate", <PooledStat value={values[1]!.bti} n={values[1]!.nNow} floor={q} text={fmtPooled(fmtNum(values[1]!.bti), values[1]!.nNow, "pooled calls")} />],
              ["p95 advantage", adv != null ? `${advNum} · point estimate` : reading.kind === "insufficient" ? <span style={{ color: RUST }}>{`${EM_DASH} insufficient samples`}</span> : EM_DASH],
              ["pooled calls", `${fmtCount(pn, q)} · ${fmtCount(an, q)}`],
              ["coverage", `${fmtCoverage(primary.missingness_rate)} / ${fmtCoverage(data.alternate.missingness_rate)}`],
            ]}
          />
        </div>

        <div style={{ borderTop: `1px solid ${FAINT}`, padding: "20px 24px", display: "flex", flexWrap: "wrap", gap: "20px", alignItems: "center", justifyContent: "space-between" }}>
          <a href={mapsHandoffUrl(primary.origin, primary.destination)} target="_blank" rel="noopener noreferrer" style={{ padding: "13px 18px", fontSize: "12.5px", letterSpacing: ".03em", border: `1px solid ${INK}`, background: INK, color: "#fbfaf7" }}>
            Open in Google Maps · endpoints only, Google chooses the road
          </a>
          <div style={{ fontSize: "11px", color: MID, maxWidth: "52ch", lineHeight: 1.5 }}>
            The link passes this pair’s origin and destination only. Both measured corridors share those endpoints, so Google — not this page — decides which road you are sent down. We publish the reliability of each corridor; we do not steer traffic onto one.
          </div>
        </div>
      </div>
      {footnote(window)}
    </div>
  );
}
