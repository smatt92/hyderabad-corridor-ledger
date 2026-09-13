import { RAMP_DEG, RAMP_IMP, RULE } from "../lib/color";

const CELL = 8;
const ROW = 15;
const BANDS = 3;

/**
 * One horizon row: a corridor's deviation from its own normal for every day
 * in the window. Positive (worse) bands in the warm ramp, negative (better)
 * mirrored into the cool ramp, both rising from the baseline. A day with no
 * value draws nothing.
 */
export function HorizonRow({ values, cursor }: { values: (number | null)[]; cursor: number }) {
  const width = values.length * CELL;
  const present = values.filter((v): v is number => v != null);
  const step = Math.max(0.01, ...present.map(Math.abs)) / BANDS;
  const rects = [];
  for (let d = 0; d < values.length; d++) {
    const v = values[d];
    if (v == null) continue;
    for (let band = 0; band < BANDS; band++) {
      const amount = Math.min(Math.max(Math.abs(v) - band * step, 0), step) / step;
      if (amount <= 0.02) continue;
      const h = amount * ROW;
      rects.push(
        <rect
          key={`${d}_${band}`}
          x={d * CELL + 0.4}
          y={ROW - h}
          width={CELL - 0.8}
          height={h}
          fill={(v >= 0 ? RAMP_DEG : RAMP_IMP)[band + 2]}
        />,
      );
    }
  }
  const cx = cursor * CELL + CELL / 2;
  return (
    <svg
      viewBox={`0 0 ${width} ${ROW}`}
      width="100%"
      height={ROW}
      preserveAspectRatio="none"
      style={{ display: "block", overflow: "visible", height: `${ROW}px` }}
    >
      {rects}
      <line x1={0} x2={width} y1={ROW} y2={ROW} stroke={RULE} stroke-width={1} />
      <line x1={cx} x2={cx} y1={0} y2={ROW} stroke="#1a1917" stroke-width={0.8} opacity={0.4} />
    </svg>
  );
}
