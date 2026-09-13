import { describe, expect, it } from "vitest";
import { HYDERABAD, frameFor, project, tilesFor, toFrame, trafficTileUrl } from "./tiles";

describe("project", () => {
  it("matches Web Mercator reference points", () => {
    expect(project(0, 0, 0, 256)).toEqual({ x: 128, y: 128 });
    expect(project(0, 180, 0, 256).x).toBe(256);
    expect(project(85.0511287798, 0, 0, 256).y).toBeCloseTo(0, 6);
  });
});

describe("Hyderabad frame", () => {
  const frame = frameFor(HYDERABAD);

  it("spans the extent at zoom 11 with 512 px tiles", () => {
    // width = 0.48 / 360 * 512 * 2^11 = 1398.1
    // height = 512 * 2^11 / (2 pi) * [ln tan(pi/4 + 17.62 deg / 2) - ln tan(pi/4 + 17.20 deg / 2)] = 1282.1
    expect(frame.width).toBeCloseTo(1398.1, 1);
    expect(frame.height).toBeCloseTo(1282.1, 1);
  });

  it("tiles cover the whole frame and nothing far outside it", () => {
    const tiles = tilesFor(frame);
    const left = Math.min(...tiles.map((t) => t.left));
    const top = Math.min(...tiles.map((t) => t.top));
    const right = Math.max(...tiles.map((t) => t.left + 512));
    const bottom = Math.max(...tiles.map((t) => t.top + 512));
    expect(left).toBeLessThanOrEqual(0);
    expect(top).toBeLessThanOrEqual(0);
    expect(right).toBeGreaterThanOrEqual(frame.width);
    expect(bottom).toBeGreaterThanOrEqual(frame.height);
    expect(left).toBeGreaterThan(-512);
    expect(right).toBeLessThan(frame.width + 512);
  });

  it("needs 12 tiles per layer, the figure the tile budget is worked from", () => {
    expect(tilesFor(frame)).toHaveLength(12);
  });

  it("places extent corners at the frame corners", () => {
    const nw = toFrame(frame, HYDERABAD.north, HYDERABAD.west);
    const se = toFrame(frame, HYDERABAD.south, HYDERABAD.east);
    expect(nw.x).toBeCloseTo(0, 6);
    expect(nw.y).toBeCloseTo(0, 6);
    expect(se.x).toBeCloseTo(frame.width, 6);
    expect(se.y).toBeCloseTo(frame.height, 6);
  });
});

describe("tile urls", () => {
  it("uses the relative0 flow style and escapes the key", () => {
    expect(trafficTileUrl({ x: 1469, y: 928, left: 0, top: 0 }, "a&b")).toBe(
      "https://api.tomtom.com/traffic/map/4/tile/flow/relative0/11/1469/928.png?tileSize=512&key=a%26b",
    );
  });
});
