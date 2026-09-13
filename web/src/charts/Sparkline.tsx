import { useMemo } from "preact/hooks";
import type uPlot from "uplot";
import { GHOST, INK, MONO } from "../lib/color";
import { UPlot } from "./UPlot";
import { dots, gapTicks, line } from "./plugins";

interface Props {
  tomtom: (number | null)[];
  p5: (number | null)[];
}

/** Seven days at the scrubber hour: TomTom basis in ink, observed-p5 basis in grey. */
export function Sparkline({ tomtom, p5 }: Props) {
  const options = useMemo<Omit<uPlot.Options, "width" | "height">>(
    () => ({
      legend: { show: false },
      cursor: { show: false },
      scales: { x: { time: false } },
      axes: [{ show: false }, { show: false }],
      padding: [3, 3, 3, 3],
      series: [{}, line(INK, 1.25), line(GHOST, 1)],
      plugins: [gapTicks([1, 2], "#c8c5bd"), dots(1, INK, 1.8)],
    }),
    [],
  );
  const data = useMemo<uPlot.AlignedData>(() => [tomtom.map((_, i) => i), tomtom, p5], [tomtom, p5]);

  if (tomtom.every((v) => v == null) && p5.every((v) => v == null)) {
    return <div style={{ fontSize: "9px", fontFamily: MONO, color: "#b6b3ab", height: "22px", lineHeight: "22px" }}>no data</div>;
  }
  return <UPlot options={options} data={data} height={22} />;
}
