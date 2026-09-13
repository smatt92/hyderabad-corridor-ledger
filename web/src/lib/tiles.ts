/**
 * Static slippy-tile grid for the corridor map. No map library, no pan, no zoom:
 * the map is spatial orientation, not exploration. Every tile URL in the bundle is
 * built here, and every one is TomTom's: no Google tiles, which exist only inside the
 * Maps JavaScript API with a billing-enabled key.
 *
 * Web Mercator world pixels at a fixed zoom place <img> tiles and the SVG
 * overlay in the same coordinate space.
 */

export interface Extent {
  west: number;
  east: number;
  south: number;
  north: number;
}

/** Greater Hyderabad, Patancheru to ECIL and Kompally to Shamshabad. */
export const HYDERABAD: Extent = { west: 78.2, east: 78.68, south: 17.2, north: 17.62 };
export const ZOOM = 11;
export const TILE_SIZE = 512;

export interface Point {
  x: number;
  y: number;
}

export function project(lat: number, lon: number, zoom = ZOOM, tileSize = TILE_SIZE): Point {
  const world = tileSize * 2 ** zoom;
  const phi = (lat * Math.PI) / 180;
  return {
    x: ((lon + 180) / 360) * world,
    y: ((1 - Math.log(Math.tan(phi) + 1 / Math.cos(phi)) / Math.PI) / 2) * world,
  };
}

export interface Frame {
  x0: number;
  y0: number;
  width: number;
  height: number;
}

export function frameFor(extent: Extent, zoom = ZOOM, tileSize = TILE_SIZE): Frame {
  const nw = project(extent.north, extent.west, zoom, tileSize);
  const se = project(extent.south, extent.east, zoom, tileSize);
  return { x0: nw.x, y0: nw.y, width: se.x - nw.x, height: se.y - nw.y };
}

/** A point in frame pixels, for the SVG overlay. */
export function toFrame(frame: Frame, lat: number, lon: number, zoom = ZOOM, tileSize = TILE_SIZE): Point {
  const p = project(lat, lon, zoom, tileSize);
  return { x: p.x - frame.x0, y: p.y - frame.y0 };
}

export interface Tile {
  x: number;
  y: number;
  left: number;
  top: number;
}

export function tilesFor(frame: Frame, zoom = ZOOM, tileSize = TILE_SIZE): Tile[] {
  const tiles: Tile[] = [];
  const [x0, x1] = [Math.floor(frame.x0 / tileSize), Math.floor((frame.x0 + frame.width) / tileSize)];
  const [y0, y1] = [Math.floor(frame.y0 / tileSize), Math.floor((frame.y0 + frame.height) / tileSize)];
  const max = 2 ** zoom - 1;
  for (let y = Math.max(0, y0); y <= Math.min(max, y1); y++) {
    for (let x = Math.max(0, x0); x <= Math.min(max, x1); x++) {
      tiles.push({ x, y, left: x * tileSize - frame.x0, top: y * tileSize - frame.y0 });
    }
  }
  return tiles;
}

export function basemapTileUrl(tile: Tile, key: string, zoom = ZOOM, tileSize = TILE_SIZE): string {
  return `https://api.tomtom.com/map/1/tile/basic/main/${zoom}/${tile.x}/${tile.y}.png?tileSize=${tileSize}&key=${encodeURIComponent(key)}`;
}

export function trafficTileUrl(tile: Tile, key: string, zoom = ZOOM, tileSize = TILE_SIZE): string {
  return `https://api.tomtom.com/traffic/map/4/tile/flow/relative0/${zoom}/${tile.x}/${tile.y}.png?tileSize=${tileSize}&key=${encodeURIComponent(key)}`;
}

export type BasemapMode = "minimal" | "street" | "satellite";

export interface TileSource {
  zoom: number;
  tileSize: number;
  url: (tile: Tile, key: string) => string;
  /** Applied in the browser; the tiles requested are unchanged. */
  filter?: string;
  attribution: string;
}

/** TomTom satellite tiles are served at 256 px only. */
export function satelliteTileUrl(tile: Tile, key: string, zoom = 12): string {
  return `https://api.tomtom.com/map/1/tile/sat/main/${zoom}/${tile.x}/${tile.y}.jpg?key=${encodeURIComponent(key)}`;
}

/**
 * Every mode is TomTom raster tiles on the browser key, against TomTom's tile
 * allowance. TomTom publishes no grey or minimal raster style, so minimal is the
 * street tiles desaturated in the browser, and switching between the two requests no
 * new tile. Satellite tiles come at 256 px only, so they are drawn at zoom 12: the
 * same world size in pixels as zoom 11 at 512 px, hence the same frame and overlay.
 */
export const BASEMAPS: Record<BasemapMode, TileSource> = {
  minimal: { zoom: ZOOM, tileSize: TILE_SIZE, url: (t, key) => basemapTileUrl(t, key), filter: "grayscale(1) contrast(.8) brightness(1.1)", attribution: "© TomTom" },
  street: { zoom: ZOOM, tileSize: TILE_SIZE, url: (t, key) => basemapTileUrl(t, key), attribution: "© TomTom" },
  satellite: { zoom: 12, tileSize: 256, url: (t, key) => satelliteTileUrl(t, key), attribution: "© TomTom" },
};

/**
 * TomTom tiles one map view requests on load, before any browser cache: the unit the
 * tile budget is worked in. The traffic layer is requested again on every refresh while
 * the tab is visible, and is not drawn over satellite imagery.
 */
export function tilesPerView(mode: BasemapMode, extent: Extent = HYDERABAD): { basemap: number; traffic: number } {
  const frame = frameFor(extent);
  const source = BASEMAPS[mode];
  return { basemap: tilesFor(frame, source.zoom, source.tileSize).length, traffic: mode === "satellite" ? 0 : tilesFor(frame).length };
}
