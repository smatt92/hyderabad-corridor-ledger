import { useMemo } from "preact/hooks";
import type uPlot from "uplot";
import { INK, RUST } from "../lib/color";
import { UPlot } from "./UPlot";
import { hidden, line, rules } from "./plugins";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

/** Median-to-p95 spread across the day, in minutes, with the scrubber hour marked. */
export function SpreadBand({ median, p95, hour }: { median: (number | null)[]; p95: (number | null)[]; hour: number }) {
  const hi = useMemo(() => Math.max(1, ...p95.filter((v): v is number => v != null)) * 1.05, [p95]);
  const options = useMemo<Omit<uPlot.Options, "width" | "height">>(
    () => ({
      legend: { show: false },
      cursor: { show: false },
      scales: { x: { time: false, range: [0, 23] }, y: { range: [0, hi] } },
      axes: [{ show: false }, { show: false }],
      padding: [2, 0, 2, 0],
      series: [{}, line(INK, 1.2), hidden],
      bands: [{ series: [2, 1], fill: "#d8d4cb" }],
      plugins: [rules(() => [{ x: hour, color: RUST }])],
    }),
    [hi, hour],
  );
  const data = useMemo<uPlot.AlignedData>(() => [HOURS, median, p95], [median, p95]);
  return <UPlot options={options} data={data} height={44} />;
}
