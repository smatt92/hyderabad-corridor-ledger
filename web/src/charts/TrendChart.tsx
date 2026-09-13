import { useMemo } from "preact/hooks";
import type uPlot from "uplot";
import { FAINT, GHOST, INK, RUST } from "../lib/color";
import { fmtDay } from "../lib/format";
import { UPlot } from "./UPlot";
import { gapTicks, line, monoAxis, rules } from "./plugins";

interface Props {
  days: string[];
  tomtom: (number | null)[];
  p5: (number | null)[];
  dayIndex: number;
  markers: { dayIndex: number; label: string }[];
}

/** TTI at the scrubber hour across the window. Lines break where there is nothing to report. */
export function TrendChart({ days, tomtom, p5, dayIndex, markers }: Props) {
  const [lo, hi] = useMemo(() => {
    const values = [...tomtom, ...p5].filter((v): v is number => v != null);
    return values.length ? [Math.min(...values) * 0.96, Math.max(...values) * 1.04] : [1, 2];
  }, [tomtom, p5]);

  const options = useMemo<Omit<uPlot.Options, "width" | "height">>(() => {
    const last = days.length - 1;
    const ticks = [0, Math.round(last / 3), Math.round((2 * last) / 3), last];
    return {
      legend: { show: false },
      cursor: { show: false },
      scales: { x: { time: false, range: [0, Math.max(1, last)] }, y: { range: [lo, hi] } },
      axes: [
        monoAxis({ splits: () => ticks, values: (_u, s) => s.map((i) => (days[i] ? fmtDay(days[i]!, true) : "")), size: 18 }),
        monoAxis({
          splits: () => [lo, (lo + hi) / 2, hi],
          values: (_u, s) => s.map((v, i) => (i === 1 ? "" : v.toFixed(2))),
          grid: { show: true, stroke: FAINT, width: 1, filter: (_u, s) => s.map((v, i) => (i === 1 ? v : null)) },
          size: 34,
        }),
      ],
      series: [{}, line(INK, 1.2), line(GHOST, 1)],
      plugins: [
        gapTicks([1, 2], "#c8c5bd"),
        rules(() => [
          ...markers.map((m) => ({ x: m.dayIndex, color: RUST, label: m.label })),
          { x: dayIndex, color: INK, alpha: 0.5 },
        ]),
      ],
    };
  }, [days, lo, hi, dayIndex, markers]);

  const data = useMemo<uPlot.AlignedData>(() => [days.map((_, i) => i), tomtom, p5], [days, tomtom, p5]);
  return <UPlot options={options} data={data} height={150} />;
}
