import { useEffect, useRef } from "preact/hooks";
import uPlot from "uplot";

interface Props {
  /** Memoise: a new options object rebuilds the chart. */
  options: Omit<uPlot.Options, "width" | "height">;
  data: uPlot.AlignedData;
  height: number;
}

/**
 * uPlot draws into a container this component owns. The chart is created once
 * per options object, updated with setData, resized with the container, and
 * destroyed on unmount.
 */
export function UPlot({ options, data, height }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const chart = new uPlot({ ...options, width: Math.max(40, el.clientWidth), height }, data, el);
    plot.current = chart;
    const observer = new ResizeObserver(() => chart.setSize({ width: Math.max(40, el.clientWidth), height }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.destroy();
      plot.current = null;
    };
    // data is applied by the effect below; rebuilding on data would discard the chart
  }, [options, height]);

  useEffect(() => {
    plot.current?.setData(data);
  }, [data]);

  return <div ref={host} style={{ width: "100%", height: `${height}px` }} />;
}
