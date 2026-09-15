import { useEffect, useMemo, useState } from "preact/hooks";
import { type Result, getJson, pooled } from "../api/client";
import type { CorridorsResponse, HealthResponse, HeatmapResponse, NetworkStateResponse, SeriesResponse } from "../api/types";
import { SeriesView } from "../analyst/series";
import { RhythmMatrix, type RhythmStyle } from "../encodings/RhythmMatrix";
import { WALL } from "../lib/color";
import { addDays, fmtCoverage, fmtHour, fmtIst, fmtNum, fmtSigned, fmtWeekday, isStale } from "../lib/format";
import { WALL_NOT_STARTED } from "../lib/collection";
import { Scheduler, msUntilIstHour } from "../lib/scheduler";
import { WallBars } from "./WallBars";

const MONO = "ui-monospace, Menlo, Consolas, monospace";
const SANS = "Helvetica Neue, Helvetica, Arial, sans-serif";
const TITLES = ["Network state", "Worst 5 corridors", "City rhythm", "Biggest movers"];
const HEALTH_EVERY_MS = 60_000;
const DATA_EVERY_MS = 15 * 60_000;
const RELOAD_AT_IST_HOUR = 4;

const WALL_RHYTHM: RhythmStyle = {
  cellW: 67, cellH: 80, padLeft: 170, padTop: 52, gap: 3,
  stops: WALL.rhythm, dayFont: 48, hourFont: 48, hourStep: 3, labelFill: WALL.dim, hourFill: WALL.faint,
  emptyFill: "#141413", emptyStroke: "#3a3a36", valueFont: null, valueFill: WALL.text,
  dayLabels: ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"],
};

interface WallData {
  corridors: CorridorsResponse;
  network: NetworkStateResponse;
  rhythm: HeatmapResponse | null;
  views: Map<string, SeriesView>;
  loadedAt: number;
}

interface Health {
  ok: boolean;
  lastOkAt: number | null;
  failingSince: number | null;
  detail: string | null;
}

async function loadWall(signal: AbortSignal): Promise<Result<WallData>> {
  const [corridors, network, rhythm] = await Promise.all([
    getJson<CorridorsResponse>("/api/corridors", signal),
    getJson<NetworkStateResponse>("/api/network/state", signal),
    getJson<HeatmapResponse>("/api/network/heatmap", signal),
  ]);
  if (!corridors.ok) return corridors;
  if (!network.ok) return network;
  const views = new Map<string, SeriesView>();
  const day = network.data.day;
  if (day) {
    const range = `from=${addDays(day, -7)}&to=${day}`;
    await pooled(corridors.data.corridors, 6, async (c) => {
      const res = await getJson<SeriesResponse>(`/api/corridors/${encodeURIComponent(c.id)}/series?${range}`, signal);
      if (res.ok && res.data.series) views.set(c.id, new SeriesView(res.data.series));
    });
  }
  return {
    ok: true,
    status: 200,
    data: { corridors: corridors.data, network: network.data, rhythm: rhythm.ok ? rhythm.data : null, views, loadedAt: Date.now() },
  };
}

function wallLabel(c: CorridorsResponse["corridors"][number]): string {
  return `${c.code ?? c.id} · ${c.origin.name ?? "?"} → ${c.destination.name ?? "?"}${c.role === "alternate" ? " (alt)" : ""}`;
}

function rotateSeconds(): number {
  const raw = Number(new URLSearchParams(location.search).get("rotate"));
  return Number.isFinite(raw) && raw > 0 ? Math.min(60, Math.max(6, Math.round(raw))) : 25;
}

/**
 * Unattended wall display. Every timer and request belongs to one Scheduler
 * that is stopped on unmount; the page reloads itself daily at 04:00 IST; an
 * unreachable API shows as a visible degraded state over the last good data,
 * never as a blank screen.
 */
export function WallApp() {
  const rotate = useMemo(rotateSeconds, []);
  const [data, setData] = useState<WallData | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health>({ ok: true, lastOkAt: null, failingSince: null, detail: null });
  const [rotation, setRotation] = useState(0);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const scheduler = new Scheduler();
    const previousBackground = document.body.style.background;
    document.body.style.background = WALL.ground;

    const advance = () =>
      scheduler.after(rotate * 1000, () => {
        setRotation((r) => r + 1);
        advance();
      });
    advance();

    scheduler.every(HEALTH_EVERY_MS, async (signal) => {
      const res = await getJson<HealthResponse>("/api/health", signal);
      const ok = res.ok && res.data.status === "ok";
      setHealth((h) =>
        ok
          ? { ok: true, lastOkAt: Date.now(), failingSince: null, detail: null }
          : { ok: false, lastOkAt: h.lastOkAt, failingSince: h.failingSince ?? Date.now(), detail: res.ok ? `database ${res.data.database}` : res.error },
      );
    });

    scheduler.every(DATA_EVERY_MS, async (signal) => {
      const loaded = await loadWall(signal);
      if (loaded.ok) {
        setData(loaded.data);
        setDataError(null);
      } else {
        setDataError(loaded.error);
      }
    });

    scheduler.after(msUntilIstHour(new Date(), RELOAD_AT_IST_HOUR), () => location.reload());

    const onResize = () => setScale(Math.min(window.innerWidth / 1920, window.innerHeight / 1080) || 1);
    onResize();
    window.addEventListener("resize", onResize);
    return () => {
      scheduler.stop();
      window.removeEventListener("resize", onResize);
      document.body.style.background = previousBackground;
    };
  }, [rotate]);

  const panel = rotation % TITLES.length;
  const degraded = !health.ok || dataError !== null;
  const network = data?.network;
  const sample = Boolean(data?.corridors.sample || network?.sample);
  const collectionStatus = data?.corridors.collection?.status;
  const notStarted = collectionStatus === "not_started" || collectionStatus === "unknown";
  // STALE means publication stopped; a ledger that never published is not stale.
  const stale = data && !notStarted ? isStale(data.corridors.as_of, new Date()) : false;
  const clock = network?.status === "ok" && network.day ? `${fmtHour(network.hour ?? 0)}  ${fmtWeekday(network.day).toUpperCase()}` : "--:--";

  return (
    <div style={{ position: "fixed", inset: 0, background: WALL.ground, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
      <div style={{ position: "relative", width: "1920px", height: "1080px", transform: `scale(${scale})`, transformOrigin: "center center", flex: "none", background: WALL.ground }}>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", color: WALL.text, fontFamily: SANS }}>
          <div style={{ height: "6px", flex: "none", background: WALL.track }}>
            <div key={rotation} style={{ height: "100%", background: WALL.text, width: 0, animation: `ledger-wall-progress ${rotate}s linear forwards` }} />
          </div>

          <div style={{ flex: "none", display: "flex", justifyContent: "space-between", alignItems: "center", padding: "26px 64px 0", fontFamily: MONO, fontSize: "48px" }}>
            {sample ? (
              <>
                <div style={{ letterSpacing: ".14em", color: WALL.ground, background: WALL.amber, padding: "6px 22px" }}>◆ SAMPLE DATA</div>
                <div style={{ color: WALL.faint, letterSpacing: ".08em" }}>SYNTHETIC · NOT A MEASUREMENT</div>
              </>
            ) : (
              <>
                <div style={{ color: WALL.faint, letterSpacing: ".08em" }}>HYDERABAD CORRIDOR LEDGER</div>
                <div style={{ color: degraded ? WALL.amber : WALL.faint, letterSpacing: ".08em", animation: degraded ? "ledger-wall-pulse 2s ease-in-out infinite" : "none" }}>
                  {degraded ? "▲ DEGRADED" : notStarted ? "○ NOT STARTED" : stale ? "◌ STALE DATA" : "● LINK OK"}
                </div>
              </>
            )}
          </div>

          <div style={{ flex: "none", display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "26px 64px 24px" }}>
            <div style={{ fontSize: "48px", letterSpacing: "-.01em", fontWeight: 500 }}>{notStarted ? "Collection" : TITLES[panel]}</div>
            <div style={{ fontFamily: MONO, fontSize: "48px", color: WALL.dim, fontVariantNumeric: "tabular-nums", letterSpacing: "-.02em" }}>{clock}</div>
          </div>

          {degraded ? (
            <div style={{ flex: "none", margin: "0 64px 18px", padding: "14px 22px", border: `3px solid ${WALL.amber}`, color: WALL.amber, fontFamily: MONO, fontSize: "40px", lineHeight: 1.2 }}>
              {!health.ok ? "API UNREACHABLE" : "DATA REFRESH FAILED"}
              {health.failingSince ? ` SINCE ${fmtIst(new Date(health.failingSince).toISOString())}` : ""}
              {data ? ` · SHOWING LAST GOOD DATA, INDICES ${fmtIst(data.corridors.as_of)}` : " · NO DATA LOADED YET"} · RETRYING
            </div>
          ) : null}

          <div style={{ flex: "1 1 auto", padding: "0 64px", minHeight: 0, opacity: degraded ? 0.45 : 1 }}>
            {data && notStarted ? (
              <NotStartedWall unknown={collectionStatus === "unknown"} asOf={data.corridors.collection?.as_of ?? null} />
            ) : data ? (
              <Panel panel={panel} data={data} />
            ) : (
              <div style={{ height: "100%", display: "flex", alignItems: "center", fontFamily: MONO, fontSize: "96px", color: dataError ? WALL.amber : WALL.faint }}>
                {dataError ? "NO DATA · API UNREACHABLE" : "LOADING…"}
              </div>
            )}
          </div>

          <div style={{ flex: "none", display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "24px 64px 40px", fontFamily: MONO, fontSize: "48px", color: stale ? WALL.amber : WALL.faint, fontVariantNumeric: "tabular-nums" }}>
            <div>
              {sample ? "SAMPLE DATA · " : ""}INDICES {data ? fmtIst(data.corridors.as_of).toUpperCase() : "—"}
              {stale ? " · STALE" : " · HOURLY CELLS"}
            </div>
            <div>{TITLES.map((_, i) => (i === panel ? "●" : "○")).join(" ")}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Before anything is measured: the reason, in the wall's register, never an empty panel. */
function NotStartedWall({ unknown, asOf }: { unknown: boolean; asOf: string | null }) {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", gap: "30px" }}>
      <div style={{ fontFamily: MONO, fontSize: "120px", lineHeight: 1, letterSpacing: "-.03em" }}>{unknown ? WALL_NOT_STARTED.unknown : WALL_NOT_STARTED.headline}</div>
      {WALL_NOT_STARTED.lines.map((line) => (
        <div key={line} style={{ fontFamily: MONO, fontSize: "56px", color: WALL.dim }}>{line}</div>
      ))}
      <div style={{ fontFamily: MONO, fontSize: "44px", color: WALL.faint }}>{asOf ? `SAMPLE LOG CHECKED ${fmtIst(asOf).toUpperCase()}` : "NO CHECK OF THE SAMPLE LOG RECORDED"}</div>
    </div>
  );
}

function Panel({ panel, data }: { panel: number; data: WallData }) {
  const { network, corridors, views } = data;
  const day = network.day;
  const hour = network.hour;

  if (panel === 0) {
    if (network.status !== "ok" || network.value == null) {
      return <Center text="NO CITYWIDE READING PUBLISHED YET" />;
    }
    const pct = network.value;
    const [symbol, label] = network.state === "worse" ? ["▲", "WORSE THAN NORMAL"] : network.state === "better" ? ["▼", "BETTER THAN NORMAL"] : ["●", "NORMAL FOR THIS HOUR"];
    const color = network.state === "worse" ? WALL.amber : network.state === "better" ? WALL.steel : WALL.text;
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", gap: "90px" }}>
        <div style={{ fontSize: "260px", lineHeight: 1, color, fontFamily: MONO, flex: "none", width: "300px", textAlign: "center" }}>{symbol}</div>
        <div>
          <div style={{ fontFamily: MONO, fontSize: "260px", lineHeight: 0.85, letterSpacing: "-.05em", color, fontVariantNumeric: "tabular-nums" }}>
            {fmtSigned(pct, 0)}%
          </div>
          <div style={{ fontSize: "64px", marginTop: "18px", letterSpacing: "-.01em" }}>{label}</div>
          <div style={{ fontSize: "48px", color: WALL.dim, marginTop: "14px" }}>citywide travel time vs same hour, last 8 weeks</div>
          {network.low_confidence ? (
            <div style={{ fontFamily: MONO, fontSize: "44px", color: WALL.amber, marginTop: "14px" }}>
              ◌ LOW CONFIDENCE · COVERAGE {fmtCoverage(network.missingness_rate)}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  if (panel === 2) {
    const rhythm = data.rhythm;
    if (!rhythm) return <Center text="CITY RHYTHM UNAVAILABLE" />;
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ width: "1778px" }}>
          <RhythmMatrix matrix={rhythm.tti_tomtom_p50} style={WALL_RHYTHM} />
        </div>
        <div style={{ fontSize: "48px", color: WALL.dim, marginTop: "20px" }}>median travel time index · TomTom free-flow · all corridors pooled</div>
      </div>
    );
  }

  if (!day || hour == null) return <Center text="NO HOURLY READING PUBLISHED YET" />;
  const rows = corridors.corridors.map((c) => {
    const view = views.get(c.id);
    return {
      c,
      tomtom: view?.value("tti_tomtom", day, hour) ?? null,
      p5: view?.value("tti_p5", day, hour) ?? null,
      dTomtom: view?.value("tti_tomtom_delta_wk", day, hour) ?? null,
      dP5: view?.value("tti_p5_delta_wk", day, hour) ?? null,
      low: view ? view.lowConfidence(day, hour) : true,
    };
  });

  if (panel === 1) {
    const top = rows.filter((r) => r.tomtom != null).sort((a, b) => b.tomtom! - a.tomtom!).slice(0, 5);
    if (!top.length) return <Center text="NO TTI PUBLISHED AT THIS HOUR" />;
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", gap: "10px" }}>
        <WallBars
          labels={top.map((r) => `${wallLabel(r.c)}${r.low ? " ◌" : ""}`)}
          values={top.map((r) => r.tomtom!)}
          colors={top.map((r, i) => (r.low ? "#5a574f" : i === 0 ? WALL.amber : "#9c7a45"))}
          valueText={top.map((r) => `${fmtNum(r.tomtom)} · ${fmtNum(r.p5)}`)}
        />
        <div style={{ fontSize: "40px", color: WALL.dim }}>TTI at {fmtHour(hour)} · TomTom · observed p5 free-flow · ◌ low confidence</div>
      </div>
    );
  }

  const movers = rows.filter((r) => r.dTomtom != null).sort((a, b) => Math.abs(b.dTomtom!) - Math.abs(a.dTomtom!)).slice(0, 5);
  if (!movers.length) return <Center text="NO WEEK-ON-WEEK CHANGE PUBLISHED" />;
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", gap: "10px" }}>
      <WallBars
        diverging
        labels={movers.map((r) => `${wallLabel(r.c)}${r.low ? " ◌" : ""}`)}
        values={movers.map((r) => r.dTomtom!)}
        colors={movers.map((r) => (r.low ? "#5a574f" : r.dTomtom! > 0 ? WALL.amber : WALL.steel))}
        valueColors={movers.map((r) => (r.dTomtom! > 0 ? WALL.amber : WALL.steel))}
        valueText={movers.map((r) => `${fmtSigned(r.dTomtom)} · ${fmtSigned(r.dP5)}`)}
      />
      <div style={{ fontSize: "40px", color: WALL.dim }}>TTI change vs same hour last week · TomTom · observed p5</div>
    </div>
  );
}

function Center({ text }: { text: string }) {
  return <div style={{ height: "100%", display: "flex", alignItems: "center", fontFamily: MONO, fontSize: "72px", color: WALL.faint }}>{text}</div>;
}
