import { describe, expect, it } from "vitest";
import type { Corridor } from "../api/types";
import { BASEMAP_STORAGE_KEY, drawnCorridors, effectiveMode, modeOptions, readBasemap, writeBasemap } from "./mapmode";

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

function memory(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return { data, getItem: (k: string) => data[k] ?? null, setItem: (k: string, v: string) => void (data[k] = v) };
}

describe("basemap modes", () => {
  it("offers satellite imagery only once some corridor has a stored road", () => {
    const satellite = (cs: Corridor[]) => modeOptions(true, cs).find((o) => o.value === "satellite")!;
    expect(satellite(connectorsOnly)).toMatchObject({ disabled: true, label: "Satellite · TomTom imagery (no corridor has a stored road yet)" });
    expect(satellite(oneRoad).disabled).toBe(false);
    expect(effectiveMode("satellite", true, connectorsOnly)).toBe("minimal");
    expect(effectiveMode("satellite", true, oneRoad)).toBe("satellite");
  });

  it("never draws a corridor without a stored road over satellite imagery", () => {
    const over = drawnCorridors("satellite", oneRoad);
    expect(over.drawn.map((c) => c.id)).toEqual(["a"]);
    expect(over.withheld.map((c) => c.id)).toEqual(["b"]);
    expect(drawnCorridors("minimal", oneRoad).drawn.map((c) => c.id)).toEqual(["a", "b"]);
    expect(drawnCorridors("street", connectorsOnly).withheld).toEqual([]);
  });

  it("offers nothing without a tile key, and falls back to minimal", () => {
    expect(modeOptions(false, oneRoad).every((o) => o.disabled)).toBe(true);
    expect(effectiveMode("street", false, oneRoad)).toBe("minimal");
  });

  it("remembers the choice locally, defaults to minimal, and survives blocked storage", () => {
    const store = memory();
    expect(readBasemap(store)).toBe("minimal");
    writeBasemap(store, "street");
    expect(store.data[BASEMAP_STORAGE_KEY]).toBe("street");
    expect(readBasemap(store)).toBe("street");
    expect(readBasemap(memory({ [BASEMAP_STORAGE_KEY]: "google" }))).toBe("minimal");
    const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readBasemap(blocked)).toBe("minimal");
    expect(() => writeBasemap(blocked, "street")).not.toThrow();
    expect(readBasemap(null)).toBe("minimal");
  });
});
