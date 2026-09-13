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
