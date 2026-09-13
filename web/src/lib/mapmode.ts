/**
 * Which basemap the corridor map shows, and what may be drawn over it.
 *
 * All three modes are TomTom raster tiles on the one browser key (lib/tiles.ts).
 * A straight connector over a street or plain basemap reads as a schematic. The same
 * line over satellite imagery reads as a claim about the road: a line cutting across
 * Hussain Sagar or through buildings, which no caption undoes. So satellite imagery is
 * offered only once some corridor has a stored road, and over it only corridors with a
 * stored road are drawn.
 */
import type { Corridor } from "../api/types";
import type { BasemapMode } from "./tiles";

export const BASEMAP_MODES: readonly BasemapMode[] = ["minimal", "street", "satellite"];
export const DEFAULT_BASEMAP: BasemapMode = "minimal";
export const BASEMAP_STORAGE_KEY = "ledger.map.basemap";

const LABELS: Record<BasemapMode, string> = {
  minimal: "Minimal · TomTom, desaturated",
  street: "Street · TomTom",
  satellite: "Satellite · TomTom imagery",
};

/** Why a mode cannot be shown, or null when it can. */
export function unavailableReason(mode: BasemapMode, hasKey: boolean, corridors: readonly Corridor[]): string | null {
  if (!hasKey) return "no browser tile key in this build";
  if (mode === "satellite" && !corridors.some((c) => c.path)) return "no corridor has a stored road yet";
  return null;
}

export function modeOptions(hasKey: boolean, corridors: readonly Corridor[]): { value: BasemapMode; label: string; disabled: boolean }[] {
  return BASEMAP_MODES.map((mode) => {
    const reason = unavailableReason(mode, hasKey, corridors);
    return { value: mode, label: reason ? `${LABELS[mode]} (${reason})` : LABELS[mode], disabled: reason !== null };
  });
}

/** The reader's choice when it can be shown, otherwise the default. */
export function effectiveMode(preferred: BasemapMode, hasKey: boolean, corridors: readonly Corridor[]): BasemapMode {
  return unavailableReason(preferred, hasKey, corridors) === null ? preferred : DEFAULT_BASEMAP;
}

/** Over satellite imagery only corridors with a stored road are drawn; elsewhere every corridor is. */
export function drawnCorridors(mode: BasemapMode, corridors: readonly Corridor[]): { drawn: Corridor[]; withheld: Corridor[] } {
  if (mode !== "satellite") return { drawn: [...corridors], withheld: [] };
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

export function readBasemap(storage: ChoiceStore | null): BasemapMode {
  try {
    const value = storage?.getItem(BASEMAP_STORAGE_KEY);
    return BASEMAP_MODES.find((mode) => mode === value) ?? DEFAULT_BASEMAP;
  } catch {
    return DEFAULT_BASEMAP;
  }
}

export function writeBasemap(storage: ChoiceStore | null, mode: BasemapMode): void {
  try {
    storage?.setItem(BASEMAP_STORAGE_KEY, mode);
  } catch {
    // storage blocked or full: the choice lasts until the page reloads
  }
}
