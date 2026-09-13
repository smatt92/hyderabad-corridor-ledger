/**
 * Route handoff and distance display.
 *
 * The frontend never constructs, derives, infers or suggests a route. A route
 * we have not measured must never reach a user: someone may drive it.
 *   - The Google Maps handoff carries the measured origin and destination and
 *     nothing else. Google chooses the road.
 *   - Distance is length_meters from the API payload. It is never computed from
 *     coordinates. When the payload has none, an em dash is shown.
 */

export interface LatLon {
  lat: number;
  lon: number;
}

export const EM_DASH = "—";

function checkCoordinate({ lat, lon }: LatLon): void {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    throw new RangeError(`invalid coordinate ${lat},${lon}`);
  }
}

/** The only outbound route link: api, origin, destination, travelmode. */
export function mapsHandoffUrl(origin: LatLon, destination: LatLon): string {
  checkCoordinate(origin);
  checkCoordinate(destination);
  return (
    "https://www.google.com/maps/dir/?api=1" +
    `&origin=${origin.lat},${origin.lon}` +
    `&destination=${destination.lat},${destination.lon}` +
    "&travelmode=driving"
  );
}

export function formatLength(lengthMeters: number | null | undefined): string {
  if (lengthMeters == null || !Number.isFinite(lengthMeters) || lengthMeters <= 0) return EM_DASH;
  return `${(lengthMeters / 1000).toFixed(1)} km`;
}
