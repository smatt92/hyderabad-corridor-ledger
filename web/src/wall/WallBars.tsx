import { useMemo } from "preact/hooks";
import uPlot from "uplot";
import { WALL } from "../lib/color";
import { UPlot } from "../charts/UPlot";

const SANS = "Helvetica Neue, Helvetica, Arial, sans-serif";
const MONO = "ui-monospace, Menlo, Consolas, monospace";

interface Props {
  labels: string[];
  values: number[];
  colors: string[];
  valueText: string[];
  /** Colour of each value's text; defaults to the wall text colour. */
  valueColors?: string[];
  diverging?: boolean;
  rowHeight?: number;
}

const LABEL_COLUMN = 700;
const VALUE_COLUMN = 480; // wide enough for "−0.00 · −0.00" at 64 px, so text never sits on a bar

/** Ranked horizontal bars for the wall, drawn by uPlot; labels and values on the canvas. */
export function WallBars({ labels, values, colors, valueText, valueColors, diverging = false, rowHeight = 100 }: Props) {
  const n = labels.length;
  const m = Math.max(1e-6, ...values.map(Math.abs));
  const options = useMemo<Omit<uPlot.Options, "width" | "height">>(() => {
    const bars = uPlot.paths.bars!({
      size: [0.56, Infinity],
      align: 0,
      disp: { fill: { unit: 3, values: () => colors } },
    });
    const decorate = (u: uPlot) => {
      const { ctx } = u;
      const px = uPlot.pxRatio;
      ctx.save();
      ctx.textBaseline = "middle";
      labels.forEach((label, i) => {
        const y = u.valToPos(i, "x", true);
        ctx.fillStyle = WALL.text;
        ctx.font = `${48 * px}px ${SANS}`;
        ctx.textAlign = "left";
        let text = label;
        const max = 660 * px;
        while (ctx.measureText(text).width > max && text.length > 4) text = `${text.slice(0, -2)}…`;
        ctx.fillText(text, 0, y);
        ctx.font = `${64 * px}px ${MONO}`;
        ctx.textAlign = "right";
        ctx.fillStyle = valueColors?.[i] ?? WALL.text;
        ctx.fillText(valueText[i] ?? "", u.width * px, y);
      });
      if (diverging) {
        const x = Math.round(u.valToPos(0, "y", true)) + 0.5;
        ctx.strokeStyle = "#4a4a46";
        ctx.lineWidth = 2 * px;
        ctx.beginPath();
        ctx.moveTo(x, u.bbox.top);
        ctx.lineTo(x, u.bbox.top + u.bbox.height);
        ctx.stroke();
      }
      ctx.restore();
    };
    return {
      legend: { show: false },
      cursor: { show: false },
      padding: [0, VALUE_COLUMN, 0, LABEL_COLUMN],
      scales: {
        x: { time: false, ori: 1, dir: -1, range: [-0.5, n - 0.5] },
        y: { ori: 0, range: diverging ? [-m, m] : [0, m] },
      },
      axes: [{ show: false }, { show: false }],
      series: [{}, { paths: bars, fill: colors[0] ?? WALL.amber, stroke: "transparent", points: { show: false } }],
      plugins: [{ hooks: { draw: [decorate] } }],
    };
  }, [labels, values, colors, valueText, valueColors, diverging, n, m]);

  const data = useMemo<uPlot.AlignedData>(() => [labels.map((_, i) => i), values], [labels, values]);
  return <UPlot options={options} data={data} height={n * rowHeight} />;
}
