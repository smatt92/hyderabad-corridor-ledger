/**
 * Which ground the corridor map is drawn on, and what may be drawn over it.
 *
 * A corridor without a stored road never renders over a recognisable basemap. Any tile
 * basemap shows a road network: satellite imagery, TomTom's street map, the same map
 * desaturated, and the traffic-flow layer drawn over the street maps. Over any of them a
 * straight line between two endpoints asserts the path taken, whatever the caption says;
 * imagery makes the claim vivid, not different in kind. So:
 * - over every tile basemap only corridors with a stored road are drawn;
 * - tile basemaps are offered only once some corridor has a stored road;
 * - a straight connector appears only on blank ground, which is the default.
 *
 * The tile basemaps are TomTom raster tiles on the one browser key (lib/tiles.ts). Blank
 * ground requests no tiles.
 */
import type { Corridor } from "../api/types";
import type { BasemapMode } from "./tiles";

export type MapGround = "blank" | BasemapMode;

export const GROUNDS: readonly MapGround[] = ["blank", "minimal", "street", "satellite"];
export const DEFAULT_GROUND: MapGround = "blank";
export const BASEMAP_STORAGE_KEY = "ledger.map.basemap";

const LABELS: Record<MapGround, string> = {
  blank: "Blank ground · no basemap",
  minimal: "Minimal · TomTom, desaturated",
  street: "Street · TomTom",
  satellite: "Satellite · TomTom imagery",
};

/** Why a ground cannot be shown, or null when it can. Blank ground always can. */
export function unavailableReason(ground: MapGround, hasKey: boolean, corridors: readonly Corridor[]): string | null {
  if (ground === "blank") return null;
  if (!hasKey) return "no browser tile key in this build";
  if (!corridors.some((c) => c.path)) return "no corridor has a stored road yet";
  return null;
}

export function modeOptions(hasKey: boolean, corridors: readonly Corridor[]): { value: MapGround; label: string; disabled: boolean }[] {
  return GROUNDS.map((ground) => {
    const reason = unavailableReason(ground, hasKey, corridors);
    return { value: ground, label: reason ? `${LABELS[ground]} (${reason})` : LABELS[ground], disabled: reason !== null };
  });
}

/** The reader's choice when it can be shown, otherwise blank ground. */
export function effectiveMode(preferred: MapGround, hasKey: boolean, corridors: readonly Corridor[]): MapGround {
  return unavailableReason(preferred, hasKey, corridors) === null ? preferred : DEFAULT_GROUND;
}

/**
 * Over any tile basemap only corridors with a stored road are drawn, and the rest are
 * withheld and listed. On blank ground every corridor is drawn.
 */
export function drawnCorridors(ground: MapGround, corridors: readonly Corridor[]): { drawn: Corridor[]; withheld: Corridor[] } {
  if (ground === "blank") return { drawn: [...corridors], withheld: [] };
  return { drawn: corridors.filter((c) => c.path), withheld: corridors.filter((c) => !c.path) };
}

type ChoiceStore = Pick<Storage, "getItem" | "setItem">;

export function browserStorage(): ChoiceStore | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function readBasemap(storage: ChoiceStore | null): MapGround {
  try {
    const value = storage?.getItem(BASEMAP_STORAGE_KEY);
    return GROUNDS.find((ground) => ground === value) ?? DEFAULT_GROUND;
  } catch {
    return DEFAULT_GROUND;
  }
}

export function writeBasemap(storage: ChoiceStore | null, ground: MapGround): void {
  try {
    storage?.setItem(BASEMAP_STORAGE_KEY, ground);
  } catch {
    // storage blocked or full: the choice lasts until the page reloads
  }
}
