import type { ComponentChildren, JSX } from "preact";
import { MID, MONO, RUST, SOFT, TEXT } from "../lib/color";
import { publication } from "../lib/floors";
import { insufficientText } from "../lib/format";
import { EM_DASH } from "../lib/route";

export const kicker: JSX.CSSProperties = {
  fontSize: "10px",
  letterSpacing: ".18em",
  textTransform: "uppercase",
  color: MID,
};

export const smallCaps: JSX.CSSProperties = {
  fontSize: "9.5px",
  letterSpacing: ".16em",
  textTransform: "uppercase",
  color: SOFT,
};

export function SectionHead(props: { title: string; sub: ComponentChildren; right?: ComponentChildren }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "24px", alignItems: "flex-end", justifyContent: "space-between", marginBottom: "16px" }}>
      <div>
        <h2 style={{ margin: "0 0 4px", fontSize: "19px", letterSpacing: "-.01em" }}>{props.title}</h2>
        <p style={{ margin: 0, color: "#5b584f", fontSize: "13px", maxWidth: "64ch" }}>{props.sub}</p>
      </div>
      {props.right}
    </div>
  );
}

export function StatList({ items }: { items: [string, ComponentChildren][] }) {
  return (
    <div style={{ fontFamily: MONO, fontSize: "11.5px", color: TEXT, lineHeight: 1.7, fontVariantNumeric: "tabular-nums" }}>
      {items.map(([k, v]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: "14px", borderBottom: "1px dotted #dcd9d1", padding: "2px 0" }}>
          <span style={{ color: MID }}>{k}</span>
          <span style={{ textAlign: "right" }}>{v}</span>
        </div>
      ))}
    </div>
  );
}

export function Select(props: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
      <span style={{ fontSize: "10px", letterSpacing: ".16em", textTransform: "uppercase", color: SOFT }}>{props.label}</span>
      <select
        value={props.value}
        onChange={(e) => props.onChange((e.target as HTMLSelectElement).value)}
        style={{ fontFamily: MONO, fontSize: "12px", padding: "6px 8px", border: "1px solid #1a1917", background: "#fbfaf7", maxWidth: "340px" }}
      >
        {props.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/** A state the reader must see rather than an empty panel. */
export function Notice(props: { kicker: string; title: string; children: ComponentChildren; tone?: "rust" | "ink" }) {
  return (
    <div style={{ border: "1.5px solid #1a1917", background: "#fbfaf7", padding: "34px 28px", display: "flex", flexDirection: "column", gap: "10px" }}>
      <div style={{ fontFamily: MONO, fontSize: "11px", letterSpacing: ".2em", textTransform: "uppercase", color: props.tone === "ink" ? "#1a1917" : "#8a4413" }}>
        {props.kicker}
      </div>
      <div style={{ fontSize: "18px", fontWeight: 500 }}>{props.title}</div>
      <div style={{ fontSize: "13.5px", color: TEXT, maxWidth: "58ch", lineHeight: 1.55 }}>{props.children}</div>
    </div>
  );
}

/**
 * A pooled statistic, or the explicit reason it is withheld: an em dash with
 * "insufficient samples" and the count against its floor, never a number and
 * never a blank.
 */
export function PooledStat(props: {
  value: number | null | undefined;
  n: number | null | undefined;
  floor: number;
  /** Shown only when the value is published. */
  text: string;
  /** Shown when there are enough calls but nothing was published. */
  unavailable?: string;
  unscheduled?: boolean;
}) {
  if (props.unscheduled) return <span style={{ color: MID }}>{`${EM_DASH} no scheduled slots at this hour`}</span>;
  const state = publication(props.value, props.n, props.floor);
  if (state === "published") return <span>{props.text}</span>;
  if (state === "insufficient") return <span style={{ color: RUST }}>{insufficientText(props.n, props.floor)}</span>;
  return <span style={{ color: MID }}>{`${EM_DASH} ${props.unavailable ?? "not published"}`}</span>;
}

export type Basis = "tomtom" | "p5";
export const BASIS_LABEL: Record<Basis, string> = { tomtom: "TomTom free-flow", p5: "observed p5 free-flow" };
