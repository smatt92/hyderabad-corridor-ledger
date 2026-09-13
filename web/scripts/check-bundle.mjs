// Post-build guard over the emitted bundle. The build plugin in vite.config.ts
// already fails on forbidden packages by module id; this catches what survives
// minification as text.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dist = join(import.meta.dirname, "..", "dist", "assets");
const banned = [
  [/waypoints/i, "a waypoints parameter (route handoff must carry origin and destination only)"],
  [/haversine/i, "a haversine distance"],
  [/TOMTOM_API_KEY/, "the collector's TomTom key name"],
  [/LEDGER_FIXTURE_DIR/, "fixture plumbing"],
  [/THREE\.WebGLRenderer|WebGLRenderer\(/, "three.js"],
  [/maplibregl|mapboxgl/i, "a map library"],
  [/deck\.gl/i, "deck.gl"],
];

let failed = false;
for (const file of readdirSync(dist).filter((f) => f.endsWith(".js"))) {
  const text = readFileSync(join(dist, file), "utf8");
  for (const [pattern, what] of banned) {
    if (pattern.test(text)) {
      console.error(`check-bundle: ${file} contains ${what}`);
      failed = true;
    }
  }
}
if (failed) process.exit(1);
console.log("check-bundle: ok");
