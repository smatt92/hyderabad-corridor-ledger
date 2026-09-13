import type { ComponentChildren } from "preact";
import { scaleLinear } from "d3-scale";
import type { RankedRatio } from "../lib/audit";
import { GHOST, INK, MID, MONO, RUST, TEXT } from "../lib/color";
import { fmtNum } from "../lib/format";
import { EM_DASH } from "../lib/route";

const W = 620;
const ROW = 18;
const LABEL = 170;
const VALUE = 150;
const TOP = 6;
const AXIS = 24;
const AT_LEAST = "#6d6a63";
const SMALLER = "#c8c5bd";

function Key({ children, swatch }: { children: ComponentChildren; swatch: ComponentChildren }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
      <svg width={22} height={10} viewBox="0 0 22 10" style={{ display: "block" }}>{swatch}</svg>
      {children}
    </span>
  );
}

/**
 * Post/pre RMSPE ratios of the treated corridor and every placebo run, largest
 * first. The treated corridor's ratio is rust and carries a dashed rule down
 * the chart. Placebos at least as large, which count against the effect, are
 * dark; smaller ones are light. A placebo with a poor pre-period fit is drawn
 * hollow and labelled. An unpublished ratio keeps its row as a dotted gap.
 */
export function PlaceboRanks({ rows, label }: { rows: readonly RankedRatio[]; label: (corridorId: string) => string }) {
  const ratios = rows.flatMap((r) => (r.ratio === null ? [] : [r.ratio]));
  const max = ratios.length ? Math.max(...ratios) : null;
  const x = scaleLinear().domain([0, max !== null && max > 0 ? max : 1]).range([LABEL, W - VALUE]);
  const treated = rows.find((r) => r.treated)?.ratio ?? null;
  const plotBottom = TOP + rows.length * ROW;
  const H = plotBottom + AXIS;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", maxWidth: `${W * 1.2}px` }}>
        {rows.map((r, i) => {
          const rowTop = TOP + i * ROW;
          const cy = rowTop + ROW / 2;
          const name = r.treated ? `treated · ${label(r.corridor_id)}` : label(r.corridor_id);
          const fill = r.treated ? RUST : r.poorPreFit ? "none" : r.atLeastTreated ? AT_LEAST : SMALLER;
          return (
            <g key={`${r.treated ? "t" : "p"}-${r.corridor_id}`}>
              <text x={LABEL - 8} y={cy + 3.5} font-size={10.5} font-family={MONO} fill={r.treated ? RUST : INK} font-weight={r.treated ? 600 : 400} text-anchor="end">
                {name}
              </text>
              {r.ratio === null ? (
                <line x1={x(0)} x2={x(0) + 14} y1={cy} y2={cy} stroke={GHOST} stroke-width={1.5} stroke-dasharray="1 2" />
              ) : (
                <rect
                  x={x(0)}
                  y={rowTop + 4}
                  width={Math.max(1, x(r.ratio) - x(0))}
                  height={ROW - 8}
                  fill={fill}
                  stroke={r.poorPreFit && !r.treated ? MID : "none"}
                  stroke-width={1}
                  stroke-dasharray={r.poorPreFit && !r.treated ? "2 1.5" : undefined}
                />
              )}
              <text x={W - VALUE + 8} y={cy + 3.5} font-size={10.5} font-family={MONO} fill={r.ratio === null ? GHOST : r.treated ? RUST : TEXT}>
                {r.ratio === null ? `${EM_DASH} not published` : fmtNum(r.ratio)}
                {r.poorPreFit ? " · poor pre fit" : ""}
              </text>
            </g>
          );
        })}
        <line x1={x(0)} x2={x(0)} y1={TOP} y2={plotBottom} stroke={INK} stroke-width={1} />
        {treated !== null ? (
          <line x1={x(treated)} x2={x(treated)} y1={TOP - 3} y2={plotBottom + 3} stroke={RUST} stroke-width={1} stroke-dasharray="3 2" />
        ) : null}
        <text x={x(0)} y={H - 8} font-size={9.5} font-family={MONO} fill={GHOST} text-anchor="middle">0</text>
        {max !== null ? (
          <text x={x(max)} y={H - 8} font-size={9.5} font-family={MONO} fill={GHOST} text-anchor="middle">{fmtNum(max)}</text>
        ) : null}
        <text x={W - VALUE + 8} y={H - 8} font-size={9.5} font-family={MONO} fill={MID}>post/pre RMSPE ratio</text>
      </svg>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", fontFamily: MONO, fontSize: "10.5px", color: MID, marginTop: "8px" }}>
        <Key swatch={<rect x={1} y={2} width={20} height={6} fill={RUST} />}>treated corridor</Key>
        <Key swatch={<rect x={1} y={2} width={20} height={6} fill={AT_LEAST} />}>placebo at least as large</Key>
        <Key swatch={<rect x={1} y={2} width={20} height={6} fill={SMALLER} />}>placebo smaller</Key>
        <Key swatch={<rect x={1} y={2} width={20} height={6} fill="none" stroke={MID} stroke-dasharray="2 1.5" />}>poor pre-period fit</Key>
        <Key swatch={<line x1={1} x2={15} y1={5} y2={5} stroke={GHOST} stroke-width={1.5} stroke-dasharray="1 2" />}>ratio not published</Key>
      </div>
    </div>
  );
}
