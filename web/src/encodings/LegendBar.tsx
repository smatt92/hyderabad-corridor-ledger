import { MID, MONO } from "../lib/color";

export function LegendBar({ stops, labels, dark = false }: { stops: readonly string[]; labels: string[]; dark?: boolean }) {
  const width = stops.length * 40;
  return (
    <svg viewBox={`0 0 ${width} 28`} width={width} height={28} style={{ display: "block" }}>
      {stops.map((fill, i) => (
        <rect key={i} x={i * 40} y={0} width={38} height={11} fill={fill} />
      ))}
      {labels.map((label, i) => {
        const last = i === labels.length - 1;
        return (
          <text
            key={`t${i}`}
            x={i === 0 ? 0 : last ? width - 2 : width / 2}
            y={24}
            font-size={9.5}
            font-family={MONO}
            fill={dark ? "#a8a59d" : MID}
            text-anchor={i === 0 ? "start" : last ? "end" : "middle"}
          >
            {label}
          </text>
        );
      })}
    </svg>
  );
}
