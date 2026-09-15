import { describe, expect, it } from "vitest";
import type { Corridor } from "../api/types";
import { BASEMAP_STORAGE_KEY, type MapGround, drawnCorridors, effectiveMode, modeOptions, readBasemap, writeBasemap } from "./mapmode";

function corridor(id: string, stored: boolean): Corridor {
  return {
    id, code: null, name: id, pair_id: null, role: null,
    origin: { name: null, lat: 17.497, lon: 78.36 }, destination: { name: null, lat: 17.447, lon: 78.377 },
    length_meters: null, free_flow: { tomtom_s: null, p5_s: null }, missingness_rate: null, low_confidence: null,
    ledger: null, rankings: {},
    path: stored ? { points: [[17.497, 78.36], [17.464, 78.357], [17.447, 78.377]], fetched_at: "2026-09-14T02:00:00+00:00", source: "TomTom" } : null,
  };
}

const connectorsOnly = [corridor("a", false), corridor("b", false)];
const oneRoad = [corridor("a", true), corridor("b", false)];
const TILED: MapGround[] = ["minimal", "street", "satellite"];

function memory(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return { data, getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => void (data[k] = v) };
}

describe("map grounds", () => {
  it("never draws a corridor without a stored road over any tile basemap, street and minimal included", () => {
    for (const ground of TILED) {
      const over = drawnCorridors(ground, oneRoad);
      expect(over.drawn.map((c) => c.id), ground).toEqual(["a"]);
      expect(over.withheld.map((c) => c.id), ground).toEqual(["b"]);
      expect(drawnCorridors(ground, connectorsOnly).drawn, ground).toEqual([]);
    }
  });

  it("draws straight connectors only on blank ground, where every corridor is drawn", () => {
    const blank = drawnCorridors("blank", oneRoad);
    expect(blank.drawn.map((c) => c.id)).toEqual(["a", "b"]);
    expect(blank.withheld).toEqual([]);
  });

  it("offers tile basemaps only once some corridor has a stored road, and blank ground always", () => {
    const options = (cs: Corridor[]) => Object.fromEntries(modeOptions(true, cs).map((o) => [o.value, o]));
    const none = options(connectorsOnly);
    expect(none.blank).toMatchObject({ disabled: false, label: "Blank ground · no basemap" });
    for (const ground of TILED) expect(none[ground]!.label).toMatch(/\(no corridor has a stored road yet\)$/);
    expect(TILED.every((ground) => none[ground]!.disabled)).toBe(true);
    expect(Object.values(options(oneRoad)).every((o) => !o.disabled)).toBe(true);
    expect(effectiveMode("street", true, connectorsOnly)).toBe("blank");
    expect(effectiveMode("minimal", true, oneRoad)).toBe("minimal");
  });

  it("offers only blank ground without a tile key", () => {
    expect(modeOptions(false, oneRoad).filter((o) => !o.disabled).map((o) => o.value)).toEqual(["blank"]);
    expect(effectiveMode("satellite", false, oneRoad)).toBe("blank");
  });

  it("remembers the choice locally, defaults to blank ground, and survives blocked storage", () => {
    const store = memory();
    expect(readBasemap(store)).toBe("blank");
    writeBasemap(store, "street");
    expect(store.data[BASEMAP_STORAGE_KEY]).toBe("street");
    expect(readBasemap(store)).toBe("street");
    expect(readBasemap(memory({ [BASEMAP_STORAGE_KEY]: "google" }))).toBe("blank");
    const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readBasemap(blocked)).toBe("blank");
    expect(() => writeBasemap(blocked, "street")).not.toThrow();
    expect(readBasemap(null)).toBe("blank");
  });
});
