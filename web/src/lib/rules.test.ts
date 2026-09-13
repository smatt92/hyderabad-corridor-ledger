/**
 * Source-level guards for rules that no unit test of a single function can
 * catch: route construction and the dependency boundaries of the bundle.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = join(import.meta.dirname, "..", "..");
const SRC = join(ROOT, "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.ts$/.test(name) ? [path] : [];
  });
}

function code(path: string): string {
  // strip comments so documentation of a rule does not trip the rule
  return readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

describe("route construction", () => {
  const banned: [RegExp, string][] = [
    [/waypoint/i, "waypoints"],
    [/haversine/i, "haversine distance"],
    [/midpoint/i, "route midpoints"],
    [/nearest[\s_-]*node/i, "nearest-node heuristics"],
    [/\bvia[\s_-]*(node|point)/i, "via nodes"],
    [/\b(asin|acos|atan2)\s*\(/, "great-circle trigonometry"],
  ];

  for (const file of sourceFiles(SRC)) {
    it(`${relative(ROOT, file)} derives no route and computes no distance`, () => {
      const text = code(file);
      for (const [pattern, what] of banned) {
        expect(text, `${what} found`).not.toMatch(pattern);
      }
    });
  }

  it("only lib/route.ts builds a maps URL", () => {
    const builders = sourceFiles(SRC).filter((f) => /google\.[a-z.]+\/maps/.test(code(f)));
    expect(builders.map((f) => relative(SRC, f))).toEqual(["lib/route.ts"]);
  });
});

describe("map tiles", () => {
  // Tiles are pulled by browsers straight from TomTom against a monthly allowance that
  // nothing here meters, so every tile request has to be accounted for in source.
  it("only lib/tiles.ts builds a TomTom tile URL", () => {
    const builders = sourceFiles(SRC).filter((f) => /api\.tomtom\.com/.test(code(f)));
    expect(builders.map((f) => relative(SRC, f))).toEqual(["lib/tiles.ts"]);
  });

  it("wall mode requests no map tiles, on any rotation", () => {
    for (const file of sourceFiles(join(SRC, "wall"))) {
      expect(code(file), relative(ROOT, file)).not.toMatch(/lib\/tiles|MapView|TileUrl/);
    }
  });

  it("every map tile hides its whole layer when it fails to load", () => {
    const imgs = [...code(join(SRC, "analyst/MapView.tsx")).matchAll(/<img\b[^>]*>/g)].map((m) => m[0]);
    expect(imgs).toHaveLength(2);
    for (const img of imgs) expect(img).toMatch(/onError=\{fail\((mode|"traffic")\)\}/);
  });

  it("no Google map tile is requested anywhere", () => {
    for (const file of sourceFiles(SRC)) {
      expect(code(file), relative(ROOT, file)).not.toMatch(/(mt\d*|khms\d*)\.google\.|maps\.googleapis\.com|tile\.googleapis\.com|google\.[a-z.]+\/(vt|kh)\//);
    }
  });

  it("the map decides what it may draw over each basemap through drawnCorridors", () => {
    expect(code(join(SRC, "analyst/MapView.tsx"))).toMatch(/drawnCorridors\(mode, /);
  });

  it("traffic tiles refresh only while the tab is visible", () => {
    expect(code(join(SRC, "analyst/MapView.tsx"))).toMatch(/every\(TRAFFIC_REFRESH_MS,[\s\S]{0,80}visibilityState === "visible"/);
  });
});

describe("SVG attributes", () => {
  // Preact, unlike React, passes attribute names through unchanged. A camelCase
  // SVG presentation attribute is silently dropped by the browser: labels fall
  // back to 14 px and lose their anchors, and strokes lose widths and dashes.
  const camel = /\s(fontSize|fontFamily|textAnchor|strokeWidth|strokeDasharray|strokeLinecap|strokeOpacity|fillOpacity|paintOrder|dominantBaseline)=/;

  for (const file of sourceFiles(SRC).filter((f) => f.endsWith(".tsx"))) {
    it(`${relative(ROOT, file)} uses real SVG attribute names`, () => {
      expect(code(file)).not.toMatch(camel);
    });
  }
});

describe("intervention audit", () => {
  // The audit publishes point estimates only: its bootstrap interval lost
  // coverage when corridors drifted, and nothing observable said when. The view
  // cannot be rendered in this node test environment, so its source is checked.
  const files = ["analyst/Audit.tsx", "lib/audit.ts", "charts/BlockChart.tsx", "charts/PlaceboRanks.tsx", "charts/SlopeChart.tsx"];
  const interval = /\b(ci_low|ci_high|equal_ci_low|equal_ci_high|resamples)\b|fmt\w*Interval\b|excludes zero|%\s*(bootstrap\s*)?interval/;

  for (const name of files) {
    it(`src/${name} reads no interval field and renders no interval`, () => {
      expect(code(join(SRC, name))).not.toMatch(interval);
    });
  }

  it("the view states its capability in the heading shared by every status", () => {
    const view = code(join(SRC, "analyst/Audit.tsx"));
    expect(view).toMatch(/const head = \([\s\S]*?<Capability \/>[\s\S]*?<Select/);
  });

  it("the view prints no placebo p without the chance expectation beside it", () => {
    expect(code(join(SRC, "analyst/Audit.tsx"))).not.toMatch(/placeboResolutionText\s*\(/);
  });
});

describe("pooled statistics", () => {
  // Ledger, profile and route-comparison intervals resampled single calls as if
  // calls from the same day and week were independent, and lost coverage in
  // simulation. These views show point values with their pooled counts and mark
  // no hour as a reliable lead.
  const files = ["analyst/Ledger.tsx", "analyst/Compare.tsx", "encodings/AdvantageStrip.tsx", "lib/advantage.ts"];
  const interval = /\bci_(low|high)\b|_ci_(low|high)\b|\bci(Low|High)\b|fmt\w*Interval\b|bootstrap_resamples|\[\$\{|\[\{\s*fmt/;

  for (const name of files) {
    it(`src/${name} reads no interval field and renders no interval bracket`, () => {
      expect(code(join(SRC, name))).not.toMatch(interval);
    });
  }
});

describe("dependency boundaries", () => {
  const forbidden = /^(d3|d3-selection|d3-transition|d3-zoom|d3-brush|three|deck\.gl|@deck\.gl\/.*|maplibre-gl|mapbox-gl|leaflet)$/;

  it("package.json declares no forbidden package", () => {
    const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
    const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
    expect(names.filter((n) => forbidden.test(n))).toEqual([]);
  });

  it("no source file imports a forbidden package", () => {
    for (const file of sourceFiles(SRC)) {
      for (const [, spec] of code(file).matchAll(/from\s+["']([^"']+)["']/g)) {
        expect(forbidden.test(spec!), `${relative(ROOT, file)} imports ${spec}`).toBe(false);
      }
    }
  });

  it("the collector's TomTom key is never referenced", () => {
    for (const file of sourceFiles(SRC)) {
      expect(code(file)).not.toContain("TOMTOM_API_KEY");
    }
  });
});
