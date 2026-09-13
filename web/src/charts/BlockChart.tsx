import type { ComponentChildren } from "preact";
import { scaleLinear } from "d3-scale";
import { type BlockRow, type Settling, blockSegments, dayNumber, fmtSettling } from "../lib/audit";
import { FAINT, GHOST, INK, MID, MONO, RULE, RUST } from "../lib/color";
import { meetsFloor } from "../lib/floors";
import { fmtDay } from "../lib/format";

const W = 680;
const H = 240;
const TOP = 42;
const RIGHT = 12;
const BOTTOM = 30;
const LEFT = 46;
const HATCH_ID = "audit-settling-hatch";

export interface BlockChartProps {
  /** Pre blocks, then post blocks. */
  rows: readonly BlockRow[];
  preStart: string;
  preEnd: string;
  /** Recorded, or with each derived boundary marked inferred; null draws no band. */
  settling: Settling | null;
  postStart: string;
  postEnd: string;
  effectiveDay: string;
  floor: number;
  treatedLabel: string;
  syntheticLabel: string;
}

function Key({ children, swatch }: { children: ComponentChildren; swatch: ComponentChildren }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
      <svg width={22} height={10} viewBox="0 0 22 10" style={{ display: "block" }}>{swatch}</svg>
      {children}
    </span>
  );
}

/**
 * Treated and synthetic BTI, block by block. Each flat segment spans the
 * recorded days of one block, because a block's BTI is pooled once over all of
 * them. A block without a published treated value is a gap with a tick on the
 * baseline: rust where the treated corridor is below the floor, grey
 * otherwise. A post block that has not completed is outlined as open. The
 * change and the excluded settling period sit at their recorded dates.
 */
export function BlockChart(p: BlockChartProps) {
  const bottom = H - BOTTOM;
  const day = (d: string) => dayNumber(d);
  const x = scaleLinear().domain([day(p.preStart), day(p.postEnd) + 1]).range([LEFT, W - RIGHT]);
  const values = p.rows.flatMap((r) => [r.treated, r.synthetic]).filter((v): v is number => v !== null);
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 1;
  const pad = hi > lo ? (hi - lo) * 0.15 : Math.max(0.02, Math.abs(hi) * 0.1);
  const y = scaleLinear().domain([lo - pad, hi + pad]).range([bottom, TOP]).nice(4);
  const treated = blockSegments(p.rows, (r) => r.treated);
  const synthetic = blockSegments(p.rows, (r) => r.synthetic);

  const pre0 = x(day(p.preStart));
  const pre1 = x(day(p.preEnd) + 1);
  const settle0 = p.settling ? x(day(p.settling.start.day)) : null;
  const settle1 = p.settling ? x(day(p.settling.end.day) + 1) : null;
  const post0 = x(day(p.postStart));
  const post1 = x(day(p.postEnd) + 1);
  const change = Math.round(x(day(p.effectiveDay))) + 0.5;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", overflow: "visible", maxWidth: `${W * 1.3}px` }}>
        <defs>
          <pattern id={HATCH_ID} width={5} height={5} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width={2} height={5} fill={INK} opacity={0.09} />
          </pattern>
        </defs>

        {y.ticks(4).map((t) => (
          <g key={`y${t}`}>
            <line x1={LEFT} x2={W - RIGHT} y1={y(t)} y2={y(t)} stroke={RULE} stroke-width={1} />
            <text x={LEFT - 6} y={y(t) + 3} font-size={9} font-family={MONO} fill={GHOST} text-anchor="end">{t.toFixed(2)}</text>
          </g>
        ))}
        <text x={LEFT - 6} y={TOP - 10} font-size={9.5} font-family={MONO} fill={MID} text-anchor="end">BTI</text>

        {settle0 !== null && settle1 !== null ? (
          <rect x={settle0} y={TOP} width={Math.max(0, settle1 - settle0)} height={bottom - TOP} fill={`url(#${HATCH_ID})`} />
        ) : null}

        {p.rows.map((r, i) =>
          r.start ? <line key={`b${i}`} x1={x(day(r.start))} x2={x(day(r.start))} y1={TOP} y2={bottom} stroke={FAINT} stroke-width={1} /> : null,
        )}
        <line x1={pre1} x2={pre1} y1={TOP} y2={bottom} stroke={FAINT} stroke-width={1} />
        <line x1={post1} x2={post1} y1={TOP} y2={bottom} stroke={FAINT} stroke-width={1} />
        <line x1={LEFT} x2={W - RIGHT} y1={bottom} y2={bottom} stroke={INK} stroke-width={1} />

        <text x={(pre0 + pre1) / 2} y={14} font-size={10} font-family={MONO} fill={MID} text-anchor="middle" letter-spacing=".12em">PRE</text>
        <text x={(post0 + post1) / 2} y={14} font-size={10} font-family={MONO} fill={MID} text-anchor="middle" letter-spacing=".12em">POST</text>

        {p.rows.map((r, i) => {
          if (!r.start || !r.end) return null;
          const x0 = x(day(r.start));
          const x1 = x(day(r.end) + 1);
          const centre = (x0 + x1) / 2;
          if (!r.complete) {
            return (
              <g key={`o${i}`}>
                <rect x={x0 + 1.5} y={TOP + 1.5} width={Math.max(0, x1 - x0 - 3)} height={bottom - TOP - 3} fill="none" stroke={GHOST} stroke-width={1} stroke-dasharray="3 3" />
                <text x={centre} y={bottom - 6} font-size={9} font-family={MONO} fill={GHOST} text-anchor="middle">open</text>
              </g>
            );
          }
          if (r.treated !== null) return null;
          const thin = !meetsFloor(r.n, p.floor);
          return (
            <line key={`g${i}`} x1={centre} x2={centre} y1={bottom - (thin ? 10 : 6)} y2={bottom} stroke={thin ? RUST : GHOST} stroke-width={thin ? 1.5 : 1} stroke-dasharray={thin ? "2 1.5" : "1 2"} />
          );
        })}

        {synthetic.map((s, i) => (
          <line key={`s${i}`} x1={x(s.x0) + 1.5} x2={x(s.x1) - 1.5} y1={y(s.value)} y2={y(s.value)} stroke={GHOST} stroke-width={2} stroke-dasharray="5 3" />
        ))}
        {treated.map((s, i) => (
          <line key={`t${i}`} x1={x(s.x0) + 1.5} x2={x(s.x1) - 1.5} y1={y(s.value)} y2={y(s.value)} stroke={INK} stroke-width={2.5} />
        ))}

        <line x1={change} x2={change} y1={TOP - 16} y2={bottom + 4} stroke={RUST} stroke-width={1} />
        <text x={change - 5} y={TOP - 8} font-size={10} font-family={MONO} fill={RUST} text-anchor="end">change · {fmtDay(p.effectiveDay, true)}</text>

        <text x={pre0} y={bottom + 15} font-size={9.5} font-family={MONO} fill={GHOST} text-anchor="start">{fmtDay(p.preStart, true)}</text>
        <text x={post0} y={bottom + 15} font-size={9.5} font-family={MONO} fill={GHOST} text-anchor="start">{fmtDay(p.postStart, true)}</text>
        <text x={post1} y={bottom + 15} font-size={9.5} font-family={MONO} fill={GHOST} text-anchor="end">{fmtDay(p.postEnd, true)}</text>
      </svg>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", fontFamily: MONO, fontSize: "10.5px", color: MID, marginTop: "8px" }}>
        <Key swatch={<line x1={1} x2={21} y1={5} y2={5} stroke={INK} stroke-width={2.5} />}>treated · {p.treatedLabel}</Key>
        <Key swatch={<line x1={1} x2={21} y1={5} y2={5} stroke={GHOST} stroke-width={2} stroke-dasharray="5 3" />}>synthetic control · {p.syntheticLabel}</Key>
        <Key swatch={<rect width={22} height={10} fill={`url(#${HATCH_ID})`} stroke={FAINT} />}>settling, excluded · {fmtSettling(p.settling)}</Key>
        <Key swatch={<line x1={11} x2={11} y1={0} y2={10} stroke={RUST} stroke-width={1.5} stroke-dasharray="2 1.5" />}>no BTI · block below {p.floor} calls</Key>
        <Key swatch={<line x1={11} x2={11} y1={2} y2={10} stroke={GHOST} stroke-width={1} stroke-dasharray="1 2" />}>no BTI published</Key>
        <Key swatch={<rect x={1} y={1} width={20} height={8} fill="none" stroke={GHOST} stroke-dasharray="3 3" />}>open · block not yet complete</Key>
      </div>
    </div>
  );
}
