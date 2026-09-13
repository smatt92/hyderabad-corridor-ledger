import { useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { CompareResponse, CompareSide, Corridor } from "../api/types";
import { SpreadBand } from "../charts/SpreadBand";
import { AdvantageStrip } from "../encodings/AdvantageStrip";
import { TIE_SECONDS, advantagePhrase, byHour } from "../lib/advantage";
import { CARD, FAINT, HATCH, INK, MID, MONO, RUST, SOFT, TEAL, TEXT } from "../lib/color";
import { fmtCoverage, fmtDay, fmtHour, fmtMinutes, fmtNum } from "../lib/format";
import { EM_DASH, formatLength, mapsHandoffUrl } from "../lib/route";
import { cache } from "./cache";
import { Notice, SectionHead, Select, StatList, kicker, smallCaps } from "./common";

const big = { fontFamily: MONO, fontSize: "40px", fontWeight: 500, letterSpacing: "-.03em", lineHeight: 1, fontVariantNumeric: "tabular-nums" };

function atHour(side: CompareSide, hour: number) {
  const p = side.profile;
  return {
    median: byHour(p.hour, p.tt_p50_s),
    p95: byHour(p.hour, p.tt_p95_s),
    bti: byHour(p.hour, p.bti)[hour] ?? null,
    low: byHour(p.hour, p.low_confidence)[hour] ?? true,
  };
}

const minutes = (v: (number | null)[]) => v.map((s) => (s == null ? null : s / 60));

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
  const footnote = (
    <div style={{ marginTop: "14px", fontSize: "11.5px", color: MID, maxWidth: "88ch", lineHeight: 1.5 }}>
      We are not a live routing product. Every figure here is a distribution over the window ending {fmtDay(windowEnd)} at the selected hour, for two separately declared corridors. Alternates are declared in the payload and measured in their own right — never derived from geometry. The Maps button passes the corridor’s origin and destination only, with no intermediate points; if you want the fastest road right now, that is Google’s job, and it is a different question.
    </div>
  );

  if (primaries.length === 0) {
    return <div>{head}<Notice kicker="No pairs" title="No corridor pairs are declared">Nothing to compare until pairs are declared.</Notice></div>;
  }
  if (res === null) return <div>{head}<div style={{ fontFamily: MONO, fontSize: "12px", color: MID }}>loading…</div></div>;
  if (!res.ok) {
    return <div>{head}<Notice kicker="Degraded" title="Comparison unavailable">The read API returned: {res.error}.</Notice>{footnote}</div>;
  }

  const data = res.data;
  const primary = data.primary;
  const title = `${data.pair_id} · ${primary.origin.name ?? "origin"} → ${primary.destination.name ?? "destination"}`;
  if (!data.alternate) {
    return (
      <div>
        {head}
        <Notice kicker="No measured alternate" title={title}>
          No measured alternate for this corridor. Pair {data.pair_id} declares one corridor only; we do not construct a second route to compare it against.
        </Notice>
        {footnote}
      </div>
    );
  }

  const sides = [primary, data.alternate] as const;
  const values = sides.map((s) => atHour(s, hour));
  const advantage = data.advantage ? byHour(data.advantage.hour, data.advantage.advantage_p95_s) : Array(24).fill(null);
  const advLow = data.advantage ? byHour(data.advantage.hour, data.advantage.low_confidence).map((v) => v ?? true) : Array(24).fill(true);
  const adv = advantage[hour] ?? null;
  const better = adv == null ? null : adv > 0 ? 1 : 0;
  const tie = adv != null && Math.abs(adv) < TIE_SECONDS;
  const advNum = adv == null ? EM_DASH : tie ? "±0 min" : `${adv > 0 ? "+" : "−"}${(Math.abs(adv) / 60).toFixed(1)} min`;
  const advColor = adv == null || tie ? MID : adv > 0 ? TEAL : RUST;
  const phrase = advantagePhrase(advantage);
  const advText =
    adv == null
      ? `No p95 travel time is published for both corridors at ${fmtHour(hour)}. `
      : tie
        ? "At this hour the two measured corridors are indistinguishable. Take either; the choice only matters at peak. "
        : adv > 0
          ? `In favour of the declared alternate: it arrives ${(adv / 60).toFixed(1)} min earlier at the 95th percentile — the number you plan around, not the median. `
          : `In favour of the primary corridor: ${(-adv / 60).toFixed(1)} min less tail risk at this hour. `;

  return (
    <div>
      {head}
      <div style={{ border: `1.5px solid ${INK}`, background: CARD }}>
        <div style={{ padding: "20px 24px", borderBottom: `1px solid ${FAINT}`, display: "flex", flexWrap: "wrap", gap: "18px", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ fontSize: "16px", fontWeight: 500 }}>{title}</div>
          <div style={{ fontFamily: MONO, fontSize: "12px", color: MID, fontVariantNumeric: "tabular-nums" }}>{fmtHour(hour)} · window to {fmtDay(windowEnd)}</div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(290px,1fr))" }}>
          {sides.map((s, i) => {
            const v = values[i]!;
            const isBetter = better === i;
            const median = v.median[hour] ?? null;
            const p95 = v.p95[hour] ?? null;
            return (
              <div key={s.id} style={{ padding: "22px 24px", borderRight: i === 0 ? `1px solid ${FAINT}` : "none", background: v.low ? HATCH : isBetter ? "#f7f5f0" : "transparent" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "12px", marginBottom: "16px" }}>
                  <div>
                    <div style={kicker}>{i === 0 ? `Primary corridor · ${s.code}` : `Declared alternate · ${s.code}`}</div>
                    <div style={{ fontSize: "15px", fontWeight: 500, marginTop: "3px" }}>{s.origin.name} → {s.destination.name}</div>
                    <div style={{ fontFamily: MONO, fontSize: "11px", color: SOFT }}>
                      pair {s.pair_id} · length {formatLength(s.length_meters)} · free-flow {fmtMinutes(s.free_flow.tomtom_s)} min
                    </div>
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: "10px", letterSpacing: ".1em", padding: "5px 8px", whiteSpace: "nowrap", border: `1px solid ${isBetter ? INK : FAINT}`, background: isBetter ? INK : "transparent", color: isBetter ? "#fbfaf7" : MID }}>
                    {better == null ? "NO P95 AT THIS HOUR" : isBetter ? "MORE RELIABLE AT THIS HOUR" : "WIDER SPREAD"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "26px", flexWrap: "wrap", alignItems: "flex-end" }}>
                  <div><div style={smallCaps}>Median</div><div style={big}>{fmtMinutes(median)}<span style={{ fontSize: "15px", color: MID }}> min</span></div></div>
                  <div><div style={smallCaps}>p95 · plan for this</div><div style={big}>{fmtMinutes(p95)}<span style={{ fontSize: "15px", color: MID }}> min</span></div></div>
                  <div><div style={smallCaps}>BTI</div><div style={big}>{fmtNum(v.bti)}</div></div>
                </div>
                <div style={{ marginTop: "18px" }}>
                  <div style={{ ...smallCaps, marginBottom: "6px" }}>Spread by hour · median to p95</div>
                  <SpreadBand median={minutes(v.median)} p95={minutes(v.p95)} hour={hour} />
                </div>
                <div style={{ marginTop: "18px", paddingTop: "14px", borderTop: `1px solid ${FAINT}`, fontSize: "10.5px", color: SOFT, lineHeight: 1.45 }}>
                  {p95 == null
                    ? "No p95 published at this hour; nothing is estimated in its place."
                    : `Budget ${fmtMinutes(p95)} min to arrive on time 19 trips out of 20${isBetter ? ", the more reliable of the two measured corridors at this hour." : "."}`}
                  {v.low ? <div style={{ color: RUST, fontFamily: MONO, marginTop: "4px" }}>◌ low confidence at this hour · more than 15% of samples missing, not interpolated</div> : null}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ borderTop: `1.5px solid ${INK}`, padding: "22px 24px", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: "26px", alignItems: "start" }}>
          <div>
            <div style={{ ...kicker, marginBottom: "8px" }}>Reliability advantage at this hour</div>
            <div style={{ fontFamily: MONO, fontSize: "56px", lineHeight: 0.95, letterSpacing: "-.04em", fontWeight: 500, fontVariantNumeric: "tabular-nums", color: advColor }}>{advNum}</div>
            <div style={{ fontSize: "13px", color: TEXT, marginTop: "8px", maxWidth: "38ch", lineHeight: 1.5 }}>{advText}{phrase}</div>
          </div>
          <div>
            <div style={{ ...kicker, marginBottom: "8px" }}>Advantage across the day</div>
            <AdvantageStrip values={advantage.map((v) => (v == null ? null : v / 60))} lowConfidence={advLow} cursor={hour} />
            <div style={{ fontSize: "10.5px", color: SOFT, marginTop: "6px", lineHeight: 1.45 }}>
              Above the rule the alternate holds less tail risk; below it, the primary corridor does. Whether the winner changes with the hour is itself the finding.
            </div>
          </div>
          <StatList
            items={[
              ["hour", fmtHour(hour)],
              ["pair id", data.pair_id],
              ["primary p95", `${fmtMinutes(values[0]!.p95[hour] ?? null)} min`],
              ["alternate p95", `${fmtMinutes(values[1]!.p95[hour] ?? null)} min`],
              ["BTI primary / alt", `${fmtNum(values[0]!.bti)} / ${fmtNum(values[1]!.bti)}`],
              ["coverage", `${fmtCoverage(primary.missingness_rate)} / ${fmtCoverage(data.alternate.missingness_rate)}`],
            ]}
          />
        </div>

        <div style={{ borderTop: `1px solid ${FAINT}`, padding: "20px 24px", display: "flex", flexWrap: "wrap", gap: "20px", alignItems: "center", justifyContent: "space-between" }}>
          <a href={mapsHandoffUrl(primary.origin, primary.destination)} target="_blank" rel="noopener noreferrer" style={{ padding: "13px 18px", fontSize: "12.5px", letterSpacing: ".03em", border: `1px solid ${INK}`, background: INK, color: "#fbfaf7" }}>
            Open in Google Maps · endpoints only, Google chooses the road
          </a>
          <div style={{ fontSize: "11px", color: MID, maxWidth: "52ch", lineHeight: 1.5 }}>
            The link passes this pair’s origin and destination only. Both measured corridors share those endpoints, so Google — not this page — decides which road you are sent down
            {better == null ? "." : `: it may route you along ${better === 1 ? "the primary corridor" : "the alternate"}, the wider-spread of the two at this hour.`} We publish the reliability of each corridor; we do not steer traffic onto one.
          </div>
        </div>
      </div>
      {footnote}
    </div>
  );
}
