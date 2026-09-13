import { useMemo } from "preact/hooks";
import type uPlot from "uplot";
import type { Floors, Profile } from "../api/types";
import { FAINT, GHOST, INK, RUST } from "../lib/color";
import { gateProfile } from "../lib/floors";
import { UPlot } from "./UPlot";
import { dots, hidden, line, monoAxis, rules } from "./plugins";

interface Props {
  profile: Profile;
  floors: Floors;
  hour: number;
}

/**
 * 24-hour profile over the pooling window, TomTom basis: p25-p75 band, median,
 * dashed p95. The observed-p5 basis median runs alongside in grey, so neither
 * free-flow reference is dropped. Every value is drawn only where its pooled
 * count meets its floor; elsewhere the line breaks. A published hour with no
 * published neighbour is drawn as a dot.
 */
export function ProfileChart({ profile, floors, hour }: Props) {
  const shown = useMemo(() => gateProfile(profile, floors), [profile, floors]);
  const hi = useMemo(() => {
    const values = [...shown.tti_tomtom_p95, ...shown.tti_tomtom_p75, ...shown.tti_p5_p50].filter((v): v is number => v != null);
    return values.length ? Math.max(...values) * 1.05 : 2;
  }, [shown]);

  const options = useMemo<Omit<uPlot.Options, "width" | "height">>(
    () => ({
      legend: { show: false },
      cursor: { show: false },
      scales: { x: { time: false, range: [0, 23] }, y: { range: [0.95, hi] } },
      axes: [
        monoAxis({ splits: () => [0, 6, 12, 18, 23], values: (_u, s) => s.map((h) => String(h === 23 ? 24 : h).padStart(2, "0")), size: 18 }),
        monoAxis({
          splits: () => [1, 1.5, 2, 2.5, 3, 3.5, 4].filter((v) => v < hi),
          values: (_u, s) => s.map((v) => v.toFixed(1)),
          grid: { show: true, stroke: FAINT, width: 1 },
          size: 30,
        }),
      ],
      series: [{}, hidden, hidden, line(INK, 1.4), line(RUST, 1.4, [5, 3]), line(GHOST, 1)],
      bands: [{ series: [2, 1], fill: "rgba(216,212,203,.85)" }],
      plugins: [rules(() => [{ x: hour, color: INK, alpha: 0.55 }]), dots(4, RUST, 1.8), dots(3, INK, 1.6)],
    }),
    [hi, hour],
  );

  const data = useMemo<uPlot.AlignedData>(
    () => [
      shown.hour,
      shown.tti_tomtom_p25,
      shown.tti_tomtom_p75,
      shown.tti_tomtom_p50,
      shown.tti_tomtom_p95,
      shown.tti_p5_p50,
    ],
    [shown],
  );

  return <UPlot options={options} data={data} height={150} />;
}
