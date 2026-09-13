import type { AdvantageKind } from "../lib/advantage";
import { GHOST, INK, RUST } from "../lib/color";

const W = 260;
const H = 90;
const BOTTOM = 16;
const PAD = 5;

/**
 * Reliability advantage by hour: the published p95 gap between a pair's two
 * measured corridors. Above the rule the alternate holds less tail risk, below
 * it the primary does. A thin line through a bar is its bootstrap interval.
 * Hours with no published advantage draw a dotted gap mark: rust where either
 * corridor is below the sample floor (insufficient samples, not a tie), grey
 * elsewhere. Low-confidence hours are faded.
 */
export function AdvantageStrip({ values, ciLow, ciHigh, kinds, lowConfidence, cursor }: {
  values: (number | null)[];
  ciLow?: (number | null)[];
  ciHigh?: (number | null)[];
  kinds?: AdvantageKind[];
  lowConfidence: boolean[];
  cursor: number;
}) {
  const extent = values.flatMap((v, h) => (v == null ? [] : [v, ciLow?.[h] ?? v, ciHigh?.[h] ?? v]));
  const m = Math.max(1, ...extent.map(Math.abs));
  const x = (h: number) => PAD + (h / 23) * (W - 2 * PAD);
  const zero = (H - BOTTOM) / 2;
  const y = (v: number) => zero - (v / m) * (zero - 3);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", overflow: "visible", maxWidth: `${W * 1.4}px` }}>
      <line x1={0} x2={W} y1={zero} y2={zero} stroke={INK} stroke-width={1} />
      {values.map((v, h) => {
        if (v == null) {
          const insufficient = kinds?.[h] === "insufficient";
          return (
            <line key={h} x1={x(h)} x2={x(h)} y1={zero - (insufficient ? 7 : 4)} y2={zero + (insufficient ? 7 : 4)}
              stroke={insufficient ? RUST : GHOST} stroke-width={insufficient ? 1.5 : 1} stroke-dasharray={insufficient ? "2 1.5" : "1 2"} />
          );
        }
        const lo = ciLow?.[h] ?? null;
        const hi = ciHigh?.[h] ?? null;
        return (
          <g key={h} opacity={lowConfidence[h] ? 0.4 : 1}>
            <rect x={x(h) - 4} y={v >= 0 ? y(v) : zero} width={8} height={Math.abs(y(v) - zero)} fill={v >= 0 ? "#4a748a" : "#a55f16"} />
            {lo != null && hi != null ? <line x1={x(h)} x2={x(h)} y1={y(lo)} y2={y(hi)} stroke={INK} stroke-width={1} opacity={0.75} /> : null}
          </g>
        );
      })}
      {[0, 6, 12, 18, 23].map((h) => (
        <text key={`t${h}`} x={x(h)} y={H - 3} font-size={9} font-family="ui-monospace, Menlo, Consolas, monospace" fill={GHOST} text-anchor="middle">
          {String(h).padStart(2, "0")}
        </text>
      ))}
      <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={H - BOTTOM} stroke={INK} opacity={0.45} />
    </svg>
  );
}
