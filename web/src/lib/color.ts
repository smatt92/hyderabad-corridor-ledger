import { scaleLinear } from "d3-scale";

// Analyst register, from the P-03 design.
export const PAPER = "#f4f3ef";
export const CARD = "#fbfaf7";
export const INK = "#1a1917";
export const TEXT = "#3a3832";
export const MID = "#6d6a63";
export const SOFT = "#8b8880";
export const FAINT = "#dcd9d1";
export const RULE = "#eae7e0";
export const GHOST = "#9a978f";
export const RUST = "#8a4413";
export const RUST_DARK = "#5d2c09";
export const TEAL = "#31627a";
export const MONO = "ui-monospace, Menlo, Consolas, monospace";

/** Worse than normal. Lightness is monotonic, so order survives greyscale and deuteranopia. */
export const RAMP_DEG = ["#e5e1d8", "#d8c39f", "#c8913f", "#a55f16", "#6e3608"] as const;
/** Better than normal, mirrored. */
export const RAMP_IMP = ["#e5e1d8", "#b8c6cd", "#7e9fae", "#4a748a", "#20465c"] as const;
export const RAMP_TTI_TEXT = ["#57544d", "#8a4413", "#5d2c09"] as const;

// Wall register.
export const WALL = {
  ground: "#0e0e0d",
  text: "#f2f1ed",
  dim: "#a8a59d",
  faint: "#77746d",
  track: "#242422",
  bar: "#1c1c1a",
  amber: "#c8913f",
  steel: "#7e9fae",
  rhythm: ["#22221f", "#6e6a5f", "#c8913f", "#e8c98e"],
} as const;

export const HATCH = "repeating-linear-gradient(45deg,rgba(26,25,23,.055) 0 2px,transparent 2px 5px)";

/** Colour at t in [0, 1] along evenly spaced stops. */
export function ramp(stops: readonly string[], t: number): string {
  const scale = scaleLinear<string>()
    .domain(stops.map((_, i) => i / (stops.length - 1)))
    .range([...stops])
    .clamp(true);
  return scale(Number.isFinite(t) ? t : 0);
}
