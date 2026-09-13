import { useMemo } from "preact/hooks";
import uPlot from "uplot";
import { GHOST, INK, MID, MONO, RUST } from "../lib/color";
import { UPlot } from "./UPlot";

interface Props {
  treated: [number, number];
  synthetic: [number, number];
  treatedLabel: string;
  changeDate: string;
  changeLabel: string;
}

/**
 * Pre/post slope chart, treated corridor against its synthetic control. Every
 * annotation is drawn on the chart itself, not in a tooltip, so a printed page
 * still carries the argument.
 */
export function SlopeChart({ treated, synthetic, treatedLabel, changeDate, changeLabel }: Props) {
  const all = [...treated, ...synthetic];
  const lo = Math.min(...all) * 0.9;
  const hi = Math.max(...all) * 1.1;

  const options = useMemo<Omit<uPlot.Options, "width" | "height">>(() => {
    const annotate = (u: uPlot) => {
      const { ctx } = u;
      const px = uPlot.pxRatio;
      const X = (v: number) => u.valToPos(v, "x", true);
      const Y = (v: number) => u.valToPos(v, "y", true);
      const text = (s: string, x: number, y: number, color: string, size: number, align: CanvasTextAlign = "left", mono = true) => {
        ctx.fillStyle = color;
        ctx.font = `${size * px}px ${mono ? MONO : "Helvetica Neue, Helvetica, Arial, sans-serif"}`;
        ctx.textAlign = align;
        ctx.fillText(s, x, y);
      };
      ctx.save();
      const top = u.bbox.top;
      const bottom = u.bbox.top + u.bbox.height;
      text("PRE", X(0), top - 26 * px, MID, 10, "center");
      text("POST", X(1), top - 26 * px, MID, 10, "center");
      text("BTI", X(0) - 46 * px, top + 10 * px, MID, 10, "left");
      // change date rule
      const mx = Math.round(X(0.5)) + 0.5;
      ctx.strokeStyle = RUST;
      ctx.lineWidth = px;
      ctx.beginPath();
      ctx.moveTo(mx, top - 12 * px);
      ctx.lineTo(mx, bottom + 6 * px);
      ctx.stroke();
      text(changeDate, mx + 6 * px, top - 2 * px, RUST, 10);
      text(changeLabel, mx + 6 * px, top + 11 * px, RUST, 10.5, "left", false);
      // endpoint values and series labels
      text(treated[0].toFixed(2), X(0) - 10 * px, Y(treated[0]) + 4 * px, INK, 12, "right");
      // When the two post values sit close together, stack treated above and
      // synthetic below so neither label nor value is drawn over the other.
      const apart = Math.abs(Y(treated[1]) - Y(synthetic[1])) > 44 * px;
      const treatedAbove = Y(treated[1]) <= Y(synthetic[1]);
      const tShift = apart ? 0 : treatedAbove ? -16 : 16;
      const sShift = apart ? 0 : treatedAbove ? 16 : -16;
      text(treated[1].toFixed(2), X(1) + 10 * px, Y(treated[1]) + (4 + tShift) * px, INK, 12);
      text(synthetic[1].toFixed(2), X(1) + 10 * px, Y(synthetic[1]) + (4 + sShift) * px, GHOST, 12);
      text(`Treated · ${treatedLabel}`, X(1) + 52 * px, Y(treated[1]) + (4 + tShift) * px, INK, 11.5, "left", false);
      text("Synthetic control", X(1) + 52 * px, Y(synthetic[1]) + (4 + sShift) * px, GHOST, 11.5, "left", false);
      text("shared pre-period, by construction", X(0) + 10 * px, Y(treated[0]) + 17 * px, GHOST, 9.5);
      ctx.restore();
    };
    return {
      legend: { show: false },
      cursor: { show: false },
      padding: [44, 230, 34, 70],
      scales: { x: { time: false, range: [0, 1] }, y: { range: [lo, hi] } },
      axes: [{ show: false }, { show: false }],
      series: [
        {},
        { stroke: INK, width: 3, points: { show: true, size: 8, fill: INK, stroke: INK } },
        { stroke: GHOST, width: 1.5, dash: [5, 4], points: { show: true, size: 8, fill: GHOST, stroke: GHOST } },
      ],
      plugins: [{ hooks: { draw: [annotate] } }],
    };
  }, [treated, synthetic, treatedLabel, changeDate, changeLabel, lo, hi]);

  const data = useMemo<uPlot.AlignedData>(() => [[0, 1], [...treated], [...synthetic]], [treated, synthetic]);
  return <UPlot options={options} data={data} height={310} />;
}
