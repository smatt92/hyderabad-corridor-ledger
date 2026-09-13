import { GHOST, INK } from "../lib/color";

const W = 260;
const H = 90;
const BOTTOM = 16;
const PAD = 5;

/**
 * Reliability advantage by hour: the published p95 gap between a pair's two
 * measured corridors. Above the rule the alternate holds less tail risk, below
 * it the primary does. Hours without both p95 values draw a dotted gap mark,
 * and low-confidence hours are faded.
 */
export function AdvantageStrip({ values, lowConfidence, cursor }: {
  values: (number | null)[];
  lowConfidence: boolean[];
  cursor: number;
}) {
  const m = Math.max(1, ...values.filter((v): v is number => v != null).map(Math.abs));
  const x = (h: number) => PAD + (h / 23) * (W - 2 * PAD);
  const zero = (H - BOTTOM) / 2;
  const y = (v: number) => zero - (v / m) * (zero - 3);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", overflow: "visible", maxWidth: `${W * 1.4}px` }}>
      <line x1={0} x2={W} y1={zero} y2={zero} stroke={INK} stroke-width={1} />
      {values.map((v, h) =>
        v == null ? (
          <line key={h} x1={x(h)} x2={x(h)} y1={zero - 4} y2={zero + 4} stroke={GHOST} stroke-width={1} stroke-dasharray="1 2" />
        ) : (
          <rect
            key={h}
            x={x(h) - 4}
            y={v >= 0 ? y(v) : zero}
            width={8}
            height={Math.abs(y(v) - zero)}
            fill={v >= 0 ? "#4a748a" : "#a55f16"}
            opacity={lowConfidence[h] ? 0.4 : 1}
          />
        ),
      )}
      {[0, 6, 12, 18, 23].map((h) => (
        <text key={`t${h}`} x={x(h)} y={H - 3} font-size={9} font-family="ui-monospace, Menlo, Consolas, monospace" fill={GHOST} text-anchor="middle">
          {String(h).padStart(2, "0")}
        </text>
      ))}
      <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={H - BOTTOM} stroke={INK} opacity={0.45} />
    </svg>
  );
}
