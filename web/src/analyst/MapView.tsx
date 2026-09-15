import { useEffect, useMemo, useState } from "preact/hooks";
import type { Corridor } from "../api/types";
import { LegendBar } from "../encodings/LegendBar";
import { INK, MID, MONO, RAMP_DEG, SOFT, TEXT, ramp } from "../lib/color";
import { fmtHour, fmtIst, fmtNum } from "../lib/format";
import { type MapGround, browserStorage, drawnCorridors, effectiveMode, modeOptions, readBasemap, unavailableReason, writeBasemap } from "../lib/mapmode";
import { Scheduler } from "../lib/scheduler";
import { BASEMAPS, HYDERABAD, TILE_SIZE, frameFor, tilesFor, toFrame, trafficTileUrl } from "../lib/tiles";
import { type Basis, Select, kicker } from "./common";
import type { SeriesView } from "./series";

const TILE_KEY = __TOMTOM_TILE_KEY__;
const TRAFFIC_REFRESH_MS = 120_000;

interface Props {
  corridors: Corridor[];
  views: Map<string, SeriesView>;
  day: string;
  hour: number;
  asOf: string | null;
}

const codes = (cs: Corridor[]) => cs.map((c) => c.code ?? c.id).join(", ");

/**
 * Static map of Greater Hyderabad: TomTom raster tiles as plain <img> elements with an
 * SVG overlay. No pan, no zoom, no map library. A corridor whose road has been stored
 * (fetched once from TomTom when the corridor was verified) is drawn as that road.
 * A corridor without one never renders over a recognisable basemap: over any tile
 * basemap a straight line asserts a path, so it is drawn as a straight connector only on
 * blank ground, and over tiles it is listed as not drawn (lib/mapmode.ts).
 */
export function MapView({ corridors, views, day, hour, asOf }: Props) {
  const [basis, setBasis] = useState<Basis>("tomtom");
  const [preferred, setPreferred] = useState<MapGround>(() => readBasemap(browserStorage()));
  const [trafficEpoch, setTrafficEpoch] = useState(0);
  // A layer with any failed tile is hidden whole, so a refused tile (429 when the tile
  // allowance runs out) leaves the overlay on a plain ground, never a broken grid. A
  // failed layer is not requested again until the page reloads.
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const fail = (layer: string) => () => setFailed((f) => (f[layer] ? f : { ...f, [layer]: true }));
  useEffect(() => {
    const scheduler = new Scheduler();
    // Every refresh requests the whole traffic layer again, and traffic tiles may not be
    // cached. A tab nobody is looking at requests none.
    scheduler.every(TRAFFIC_REFRESH_MS, () => {
      if (document.visibilityState === "visible") setTrafficEpoch((n) => n + 1);
    });
    return () => scheduler.stop();
  }, []);

  const hasKey = TILE_KEY !== "";
  const frame = useMemo(() => frameFor(HYDERABAD), []);
  const pairs = useMemo(() => corridors.filter((c) => c.role !== "alternate"), [corridors]);
  const mode = effectiveMode(preferred, hasKey, pairs);
  const source = mode === "blank" ? null : BASEMAPS[mode];
  const basemapTiles = useMemo(() => (source ? tilesFor(frame, source.zoom, source.tileSize) : []), [frame, source]);
  const trafficTiles = useMemo(() => tilesFor(frame), [frame]);
  const { drawn: shown, withheld } = useMemo(() => drawnCorridors(mode, pairs), [mode, pairs]);
  const showBasemap = source !== null && hasKey && !failed[mode];
  const showTraffic = source !== null && hasKey && mode !== "satellite" && !failed.traffic;
  const fallback = hasKey && preferred !== mode ? unavailableReason(preferred, hasKey, pairs) : null;
  const roads = shown.filter((c) => c.path);
  const connectors = shown.filter((c) => !c.path);

  const values = shown.map((c) => views.get(c.id)?.value(basis === "tomtom" ? "tti_tomtom" : "tti_p5", day, hour) ?? null);
  const present = values.filter((v): v is number => v != null);
  const [lo, hi] = present.length ? [Math.min(...present), Math.max(...present)] : [1, 2];

  const nodes = useMemo(() => {
    const degree = new Map<string, { lat: number; lon: number; n: number }>();
    for (const c of shown) {
      for (const p of [c.origin, c.destination]) {
        const name = p.name ?? `${p.lat},${p.lon}`;
        const entry = degree.get(name) ?? { lat: p.lat, lon: p.lon, n: 0 };
        entry.n++;
        degree.set(name, entry);
      }
    }
    const placed: [number, number, number, number][] = [];
    return [...degree.entries()]
      .sort((a, b) => b[1].n - a[1].n)
      .map(([name, { lat, lon }]) => {
        const pt = toFrame(frame, lat, lon);
        const box: [number, number, number, number] = [pt.x + 7, pt.y - 20, pt.x + 7 + name.length * 8.4 + 8, pt.y - 3];
        const free = !placed.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]));
        if (free) placed.push(box);
        return { name, pt, label: free };
      });
  }, [shown, frame]);

  const pct = (v: number, of: number) => `${(v / of) * 100}%`;
  const tileStyle = (left: number, top: number, size: number) => ({
    position: "absolute" as const,
    left: pct(left, frame.width),
    top: pct(top, frame.height),
    width: pct(size, frame.width),
    height: pct(size, frame.height),
    pointerEvents: "none" as const,
  });
  const choose = (value: string) => {
    const next = value as MapGround;
    setPreferred(next);
    writeBasemap(browserStorage(), next);
  };

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "24px", alignItems: "flex-end", justifyContent: "space-between", marginBottom: "14px" }}>
        <div>
          <h2 style={{ margin: "0 0 4px", fontSize: "19px", letterSpacing: "-.01em" }}>Corridor map</h2>
          <p style={{ margin: 0, color: "#5b584f", fontSize: "13px", maxWidth: "62ch" }}>
            Declared corridors, coloured by TTI at the scrubber position. A corridor whose road has been stored — fetched once from TomTom when the corridor was verified — is drawn as that road, over any basemap. A corridor without a stored road never renders over a map that shows roads, where any line would read as the path taken: it is drawn only on blank ground, as a straight connector between its measured endpoints, and listed below the map.
          </p>
        </div>
        <div style={{ display: "flex", gap: "14px", alignItems: "center", flexWrap: "wrap" }}>
          <Select label="Basemap" value={mode} options={modeOptions(hasKey, pairs)} onChange={choose} />
          <Select label="Free-flow" value={basis} options={[{ value: "tomtom", label: "TomTom" }, { value: "p5", label: "Observed p5" }]} onChange={(v) => setBasis(v as Basis)} />
          <div style={{ fontFamily: MONO, fontSize: "11.5px", color: TEXT, border: `1px solid ${INK}`, padding: "7px 10px", fontVariantNumeric: "tabular-nums" }}>
            indices {fmtIst(asOf)} · {fmtHour(hour)}{showTraffic ? " · traffic tiles refresh every 2 min while this tab is visible" : ""}
          </div>
        </div>
      </div>
      {fallback ? (
        <div style={{ fontFamily: MONO, fontSize: "11.5px", color: MID, marginBottom: "8px" }}>
          {preferred} basemap unavailable: {fallback} · showing {mode}
        </div>
      ) : null}

      <div style={{ position: "relative", width: "100%", maxWidth: "1000px", aspectRatio: `${frame.width} / ${frame.height}`, border: `1px solid ${INK}`, overflow: "hidden", background: "#eceae4" }}>
        {showBasemap
          ? basemapTiles.map((t) => (
              <img key={`${mode}${t.x}_${t.y}`} src={source.url(t, TILE_KEY)} alt="" loading="lazy" decoding="async" onError={fail(mode)} style={{ ...tileStyle(t.left, t.top, source.tileSize), filter: source.filter }} />
            ))
          : null}
        {showTraffic
          ? trafficTiles.map((t) => (
              <img key={`t${t.x}_${t.y}_${trafficEpoch}`} src={trafficTileUrl(t, TILE_KEY)} alt="" decoding="async" onError={fail("traffic")} style={{ ...tileStyle(t.left, t.top, TILE_SIZE), opacity: 0.85 }} />
            ))
          : null}
        <svg viewBox={`0 0 ${frame.width} ${frame.height}`} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} role="img" aria-label="Stored corridor roads, and straight connectors between measured endpoints where no road is stored">
          {source === null ? (
            <text x={frame.width / 2} y={frame.height - 24} font-size={15} font-family={MONO} fill="#a8a59d" text-anchor="middle">
              {hasKey ? "blank ground · no basemap" : "blank ground · no browser tile key in this build"}
            </text>
          ) : null}
          {source !== null && hasKey && (failed[mode] || (mode !== "satellite" && failed.traffic)) ? (
            <text x={frame.width / 2} y={frame.height - 24} font-size={15} font-family={MONO} fill="#8b8880" text-anchor="middle">
              {failed[mode] && failed.traffic && mode !== "satellite"
                ? "basemap and traffic tiles failed to load · overlay only"
                : failed[mode]
                  ? "basemap tiles failed to load · drawn without a basemap"
                  : "traffic tiles failed to load · traffic layer hidden"}
            </text>
          ) : null}
          {shown.map((c, i) => {
            const v = values[i];
            const t = v == null ? 0 : (v - lo) / (hi - lo || 1);
            const stroke = v == null ? "#8b8880" : ramp(RAMP_DEG, t);
            const width = v == null ? 3 : 3.4 + t * 5;
            const title = `${c.code ?? c.id} ${c.name}: TTI ${fmtNum(v)} · ${c.path ? `stored road, TomTom, fetched ${fmtIst(c.path.fetched_at)}` : "straight connector between endpoints, not the road"}`;
            if (c.path) {
              const points = c.path.points.map(([lat, lon]) => {
                const p = toFrame(frame, lat, lon);
                return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
              }).join(" ");
              return (
                <g key={c.id}>
                  {mode === "satellite" ? <polyline points={points} fill="none" stroke="#1a1917" stroke-width={width + 3} stroke-linecap="round" stroke-linejoin="round" opacity={0.55} /> : null}
                  <polyline points={points} fill="none" stroke-linecap="round" stroke-linejoin="round" stroke={stroke} stroke-width={width} stroke-dasharray={v == null ? "4 7" : undefined} opacity={v == null ? 0.8 : 0.95}>
                    <title>{title}</title>
                  </polyline>
                </g>
              );
            }
            const a = toFrame(frame, c.origin.lat, c.origin.lon);
            const b = toFrame(frame, c.destination.lat, c.destination.lon);
            return (
              <line key={c.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke-linecap="round" stroke={stroke} stroke-width={width} stroke-dasharray={v == null ? "4 7" : undefined} opacity={v == null ? 0.8 : 0.95}>
                <title>{title}</title>
              </line>
            );
          })}
          {nodes.map((n) => (
            <g key={n.name}>
              <circle cx={n.pt.x} cy={n.pt.y} r={3.2} fill="#3a3832" />
              {n.label ? (
                <text x={n.pt.x + 7} y={n.pt.y - 6} font-size={14} font-family={MONO} fill="#3a3832" stroke="#f4f3ef" stroke-width={3.6} paint-order="stroke">
                  {n.name}
                </text>
              ) : null}
            </g>
          ))}
        </svg>
        {source && (showBasemap || showTraffic) ? (
          <div style={{ position: "absolute", right: 0, bottom: 0, fontFamily: MONO, fontSize: "10px", color: "#3a3832", background: "rgba(244,243,239,.8)", padding: "1px 5px" }}>{source.attribution}</div>
        ) : null}
      </div>
      <div style={{ marginTop: "8px", fontSize: "11.5px", color: MID, maxWidth: "88ch", lineHeight: 1.5 }}>
        {roads.length ? <div>Stored roads ({roads.length}): {codes(roads)}. The road TomTom routes through each corridor's declared points, fetched once when the corridor was verified and checked weekly since.</div> : null}
        {connectors.length ? <div>Straight connectors on blank ground ({connectors.length}): {codes(connectors)}. No road is stored for these yet: the line joins the measured endpoints and is not the road taken.</div> : null}
        {withheld.length ? <div>Not drawn over this basemap ({withheld.length}): {codes(withheld)}. No road is stored, and any line over a map that shows roads would read as the path taken. Choose blank ground to see them as straight connectors.</div> : null}
        <div>Dashed grey lines have no published value at this hour.</div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "30px", marginTop: "14px", alignItems: "flex-end" }}>
        <div>
          <div style={{ ...kicker, marginBottom: "6px" }}>Corridor TTI · {basis === "tomtom" ? "TomTom" : "observed p5"} free-flow</div>
          <LegendBar stops={RAMP_DEG} labels={[fmtNum(lo), "", "", "", fmtNum(hi)]} />
        </div>
        <div style={{ fontFamily: MONO, fontSize: "10.5px", color: SOFT, lineHeight: 1.6, maxWidth: "58ch" }}>
          <div>layer 1 · {mode === "blank" ? "none: blank ground" : mode === "minimal" ? "TomTom street tiles, desaturated in the browser" : mode === "street" ? "TomTom street tiles" : "TomTom satellite imagery"}</div>
          {mode === "minimal" || mode === "street" ? <div>layer 2 · traffic-flow tiles, TomTom relative0 raster, 2-min refresh while visible</div> : null}
          <div>layer 3 · {mode === "blank" ? "stored roads where fetched, straight connectors elsewhere" : "stored roads only"}, coloured by TTI</div>
          <div>a layer whose tiles fail to load is hidden whole, never shown as a broken grid</div>
        </div>
      </div>
    </div>
  );
}
