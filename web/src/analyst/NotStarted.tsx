import type { Collection } from "../api/types";
import { INK, MID, MONO, TEXT } from "../lib/color";
import { DATA_SOURCES_URL, NOT_STARTED, UNKNOWN, collectionAsOf } from "../lib/collection";

/**
 * What a visitor sees before anything has been measured: an absence with its
 * reason, never an empty instrument. Shown only when the API read the database
 * and found nothing collected, or nothing that says whether collection started.
 */
export function NotStarted({ collection }: { collection: Collection | null | undefined }) {
  const unknown = collection?.status === "unknown";
  const paragraph = { margin: 0, fontSize: "14px", color: TEXT, lineHeight: 1.6, maxWidth: "68ch" } as const;
  return (
    <div style={{ border: `1.5px solid ${INK}`, background: "#fbfaf7", padding: "34px 28px", display: "flex", flexDirection: "column", gap: "14px" }}>
      <div style={{ fontFamily: MONO, fontSize: "11px", letterSpacing: ".2em", textTransform: "uppercase", color: INK }}>
        {unknown ? UNKNOWN.kicker : NOT_STARTED.kicker}
      </div>
      <div style={{ fontSize: "22px", fontWeight: 600, letterSpacing: "-.01em" }}>{unknown ? UNKNOWN.title : NOT_STARTED.title}</div>
      <p style={{ ...paragraph, fontWeight: 500 }}>{unknown ? UNKNOWN.status : NOT_STARTED.status}</p>
      <p style={paragraph}>{NOT_STARTED.what}</p>
      <p style={paragraph}>{NOT_STARTED.why}</p>
      <p style={paragraph}>{NOT_STARTED.next}</p>
      <p style={paragraph}>
        <a href={DATA_SOURCES_URL}>{NOT_STARTED.link}</a> <span style={{ fontFamily: MONO, fontSize: "12px", color: MID }}>docs/data-sources.md</span>
      </p>
      <div style={{ fontFamily: MONO, fontSize: "11px", color: MID }}>{collectionAsOf(collection)}</div>
    </div>
  );
}
