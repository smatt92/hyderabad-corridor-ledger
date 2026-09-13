import { useMemo } from "preact/hooks";
import type { Corridor } from "../api/types";
import { HorizonRow } from "../encodings/Horizon";
import { LegendBar } from "../encodings/LegendBar";
import { GHOST, INK, MID, MONO, RAMP_DEG, RAMP_IMP, RULE, RUST, SOFT, TEAL, TEXT } from "../lib/color";
import { fmtDay, fmtHour, fmtPercent } from "../lib/format";
import { EM_DASH } from "../lib/route";
import { SectionHead } from "./common";
import type { SeriesView } from "./series";

interface Props {
  corridors: Corridor[];
  views: Map<string, SeriesView>;
  days: string[];
  dayIndex: number;
  hour: number;
}

export function Pulse({ corridors, views, days, dayIndex, hour }: Props) {
  const rows = useMemo(
    () =>
      corridors.map((c) => {
        const view = views.get(c.id);
        // travel time against the corridor's own median at this hour: no free-flow basis needed
        const values = days.map((d) => {
          const ratio = view?.value("tt_ratio_own_median", d, hour) ?? null;
          return ratio == null ? null : ratio - 1;
        });
        return { c, values, today: values[dayIndex] ?? null };
      }),
    [corridors, views, days, hour, dayIndex],
  );

  return (
    <div>
      <SectionHead
        title="Network pulse"
        sub={`Every corridor × every day in the ${days.length}-day window, one screen. Travel time at ${fmtHour(hour)} against each corridor’s own median at that hour, so no free-flow reference is involved. Horizon banding is the only encoding that survives this density.`}
        right={
          <div style={{ display: "flex", gap: "18px", alignItems: "flex-end" }}>
            <div>
              <div style={{ fontSize: "10px", letterSpacing: ".16em", textTransform: "uppercase", color: MID, marginBottom: "4px" }}>Worse than own median</div>
              <LegendBar stops={RAMP_DEG.slice(2)} labels={["band 1", "", "band 3"]} />
            </div>
            <div>
              <div style={{ fontSize: "10px", letterSpacing: ".16em", textTransform: "uppercase", color: MID, marginBottom: "4px" }}>Better · mirrored</div>
              <LegendBar stops={RAMP_IMP.slice(2)} labels={["band 1", "", "band 3"]} />
            </div>
          </div>
        }
      />
      <div style={{ borderTop: `1px solid ${INK}`, borderBottom: `1px solid ${INK}`, padding: "2px 0" }}>
        {rows.map(({ c, values, today }) => (
          <div key={c.id} style={{ display: "flex", alignItems: "center", gap: "8px", borderBottom: `1px solid ${RULE}` }}>
            <div style={{ width: "36px", flex: "none", fontFamily: MONO, fontSize: "9.5px", color: GHOST, textAlign: "right" }}>{c.code}</div>
            <div style={{ width: "118px", flex: "none", fontSize: "10.5px", color: TEXT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.name}>{c.name}</div>
            <div style={{ flex: "1 1 auto", minWidth: 0 }}>
              <HorizonRow values={values} cursor={dayIndex} />
            </div>
            <div style={{ width: "54px", flex: "none", textAlign: "right", fontFamily: MONO, fontSize: "11px", fontVariantNumeric: "tabular-nums", color: today == null ? "#b6b3ab" : today > 0.02 ? RUST : today < -0.02 ? TEAL : MID }}>
              {today == null ? EM_DASH : fmtPercent(today * 100)}
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: "6px", fontFamily: MONO, fontSize: "10px", color: SOFT }}>
        <span>{days[0] ? fmtDay(days[0]) : ""}</span>
        <span>{days.length} days →</span>
        <span>{days.at(-1) ? fmtDay(days.at(-1)!) : ""}</span>
      </div>
      <div style={{ marginTop: "14px", fontSize: "11.5px", color: MID, maxWidth: "80ch", lineHeight: 1.5 }}>
        Blank columns are days with insufficient samples on that corridor. They are left blank on purpose.
      </div>
    </div>
  );
}
