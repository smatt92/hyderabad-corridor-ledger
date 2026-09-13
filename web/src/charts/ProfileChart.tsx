import { useMemo } from "preact/hooks";
import type uPlot from "uplot";
import type { Profile } from "../api/types";
import { FAINT, GHOST, INK, RUST } from "../lib/color";
import { UPlot } from "./UPlot";
import { hidden, line, monoAxis, rules } from "./plugins";

interface Props {
  profile: Profile;
  hour: number;
}

/**
 * 24-hour profile over the read window, TomTom basis: p25-p75 band, median,
 * dashed p95. The observed-p5 basis median runs alongside in grey, so neither
 * free-flow reference is dropped.
 */
export function ProfileChart({ profile, hour }: Props) {
  const hi = useMemo(() => {
    const values = [...profile.tti_tomtom_p95, ...profile.tti_p5_p50].filter((v): v is number => v != null);
    return values.length ? Math.max(...values) * 1.05 : 2;
  }, [profile]);

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
      plugins: [rules(() => [{ x: hour, color: INK, alpha: 0.55 }])],
    }),
    [hi, hour],
  );

  const data = useMemo<uPlot.AlignedData>(
    () => [
      profile.hour,
      profile.tti_tomtom_p25,
      profile.tti_tomtom_p75,
      profile.tti_tomtom_p50,
      profile.tti_tomtom_p95,
      profile.tti_p5_p50,
    ],
    [profile],
  );

  return <UPlot options={options} data={data} height={150} />;
}
