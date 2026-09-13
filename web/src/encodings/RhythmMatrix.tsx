import { ramp } from "../lib/color";

export interface RhythmStyle {
  cellW: number;
  cellH: number;
  padLeft: number;
  padTop: number;
  gap: number;
  stops: readonly string[];
  dayFont: number;
  hourFont: number;
  hourStep: number;
  labelFill: string;
  hourFill: string;
  emptyFill: string;
  emptyStroke: string;
  valueFont: number | null;
  valueFill: string;
  dayLabels: string[];
}

export const ANALYST_RHYTHM: RhythmStyle = {
  cellW: 34, cellH: 30, padLeft: 74, padTop: 30, gap: 1,
  stops: ["#e5e1d8", "#d8c39f", "#c8913f", "#a55f16", "#6e3608"],
  dayFont: 15, hourFont: 13, hourStep: 2, labelFill: "#6d6a63", hourFill: "#6d6a63",
  emptyFill: "#f4f3ef", emptyStroke: "#dcd9d1", valueFont: 12, valueFill: "#fbfaf7",
  dayLabels: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
};

export function extent(matrix: (number | null)[][]): [number, number] | null {
  const values = matrix.flat().filter((v): v is number => v != null);
  return values.length ? [Math.min(...values), Math.max(...values)] : null;
}

/**
 * The 24 x 7 rhythm matrix: weekday rows (Sunday first), hour columns. Colour
 * encodes magnitude only, on a ramp with monotonic lightness. Cells with too
 * few days to publish are dashed and left empty, never filled in.
 */
export function RhythmMatrix({ matrix, style, highlight }: {
  matrix: (number | null)[][];
  style: RhythmStyle;
  highlight?: { dow: number; hour: number } | null;
}) {
  const s = style;
  const width = s.padLeft + 24 * s.cellW;
  const height = s.padTop + 7 * s.cellH + 10;
  const range = extent(matrix);
  const [lo, hi] = range ?? [0, 1];
  const span = hi - lo || 1;
  const cells = [];
  for (let dow = 0; dow < 7; dow++) {
    cells.push(
      <text key={`d${dow}`} x={s.padLeft - 10} y={s.padTop + dow * s.cellH + s.cellH * 0.66} font-size={s.dayFont}
        font-family="ui-monospace, Menlo, Consolas, monospace" fill={s.labelFill} text-anchor="end">
        {s.dayLabels[dow]}
      </text>,
    );
    for (let hour = 0; hour < 24; hour++) {
      const v = matrix[dow]?.[hour] ?? null;
      const x = s.padLeft + hour * s.cellW;
      const y = s.padTop + dow * s.cellH;
      const w = s.cellW - 2 * s.gap;
      const h = s.cellH - 2 * s.gap;
      if (v == null) {
        cells.push(<rect key={`n${dow}_${hour}`} x={x + s.gap} y={y + s.gap} width={w} height={h} fill={s.emptyFill} stroke={s.emptyStroke} stroke-dasharray="2 2" />);
        continue;
      }
      cells.push(<rect key={`c${dow}_${hour}`} x={x + s.gap} y={y + s.gap} width={w} height={h} fill={ramp(s.stops, (v - lo) / span)} />);
      if (s.valueFont && v >= hi - span * 0.18) {
        cells.push(
          <text key={`t${dow}_${hour}`} x={x + s.cellW / 2} y={y + s.cellH / 2 + s.valueFont * 0.375} font-size={s.valueFont}
            font-family="ui-monospace, Menlo, Consolas, monospace" fill={s.valueFill} text-anchor="middle">
            {v.toFixed(1)}
          </text>,
        );
      }
    }
  }
  for (let hour = 0; hour < 24; hour += s.hourStep) {
    cells.push(
      <text key={`h${hour}`} x={s.padLeft + hour * s.cellW + s.cellW / 2} y={s.padTop - 12} font-size={s.hourFont}
        font-family="ui-monospace, Menlo, Consolas, monospace" fill={s.hourFill} text-anchor="middle">
        {String(hour).padStart(2, "0")}
      </text>,
    );
  }
  if (highlight) {
    cells.push(
      <rect key="hl" x={s.padLeft + highlight.hour * s.cellW} y={s.padTop + highlight.dow * s.cellH}
        width={s.cellW} height={s.cellH} fill="none" stroke="#1a1917" stroke-width={1.5} />,
    );
  }
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ display: "block", maxWidth: "100%", height: "auto" }}>
      {cells}
    </svg>
  );
}
