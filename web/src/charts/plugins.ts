import uPlot from "uplot";
import { MONO } from "../lib/color";

export interface Rule {
  x: number | null;
  color: string;
  alpha?: number;
  label?: string | null;
}

/** Vertical rules drawn on the canvas, so they print with the chart. */
export function rules(read: () => Rule[]): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u) => {
          const { ctx } = u;
          const { top, height } = u.bbox;
          const px = uPlot.pxRatio;
          for (const rule of read()) {
            if (rule.x == null) continue;
            const x = Math.round(u.valToPos(rule.x, "x", true)) + 0.5;
            ctx.save();
            ctx.globalAlpha = rule.alpha ?? 1;
            ctx.strokeStyle = rule.color;
            ctx.lineWidth = px;
            ctx.beginPath();
            ctx.moveTo(x, top);
            ctx.lineTo(x, top + height);
            ctx.stroke();
            if (rule.label) {
              ctx.globalAlpha = 1;
              ctx.fillStyle = rule.color;
              ctx.font = `${9 * px}px ${MONO}`;
              ctx.fillText(rule.label, x + 4 * px, top + 10 * px);
            }
            ctx.restore();
          }
        },
      ],
    },
  };
}

/** A short tick on the baseline wherever every listed series has no value. Gaps stay gaps. */
export function gapTicks(seriesIndexes: number[], color: string): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u) => {
          const { ctx } = u;
          const px = uPlot.pxRatio;
          const bottom = u.bbox.top + u.bbox.height;
          ctx.save();
          ctx.fillStyle = color;
          u.data[0].forEach((xv, i) => {
            if (seriesIndexes.every((s) => u.data[s]?.[i] == null)) {
              const x = u.valToPos(xv, "x", true);
              ctx.fillRect(x - px, bottom - 3 * px, 2 * px, 3 * px);
            }
          });
          ctx.restore();
        },
      ],
    },
  };
}

/** Dot on isolated values (a value with no neighbour draws no line) and on the last value. */
export function dots(seriesIndex: number, color: string, radius = 1.6): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u) => {
          const ys = u.data[seriesIndex];
          if (!ys) return;
          const { ctx } = u;
          const px = uPlot.pxRatio;
          ctx.save();
          ctx.fillStyle = color;
          ys.forEach((y, i) => {
            if (y == null) return;
            const isolated = ys[i - 1] == null && ys[i + 1] == null;
            if (!isolated && i !== ys.length - 1) return;
            ctx.beginPath();
            ctx.arc(u.valToPos(u.data[0][i]!, "x", true), u.valToPos(y, "y", true), radius * px, 0, Math.PI * 2);
            ctx.fill();
          });
          ctx.restore();
        },
      ],
    },
  };
}

export const hidden: uPlot.Series = { stroke: "transparent", width: 0, points: { show: false } };

export function line(stroke: string, width: number, dash?: number[]): uPlot.Series {
  return { stroke, width, dash, points: { show: false }, spanGaps: false };
}

export function monoAxis(extra: Partial<uPlot.Axis>): uPlot.Axis {
  return {
    stroke: "#9a978f",
    font: `9px ${MONO}`,
    ticks: { show: false },
    grid: { show: false },
    gap: 3,
    ...extra,
  };
}
