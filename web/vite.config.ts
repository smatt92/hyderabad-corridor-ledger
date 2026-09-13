import { defineConfig, type Plugin } from "vitest/config";

// Packages that must never enter the dashboard bundle. three.js belongs only to
// the P-06 showcase route; maps are plain <img> tiles plus SVG; d3 is imported
// module by module as math and path helpers, never for DOM ownership.
const FORBIDDEN = [
  "d3", "d3-selection", "d3-transition", "d3-zoom", "d3-brush",
  "three", "deck.gl", "@deck.gl", "maplibre-gl", "mapbox-gl", "leaflet",
];

function forbidPackages(): Plugin {
  const pattern = new RegExp(`node_modules/(${FORBIDDEN.map((p) => p.replace(/[.]/g, "\\.")).join("|")})/`);
  return {
    name: "ledger:forbid-packages",
    apply: "build",
    generateBundle(_options, bundle) {
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== "chunk") continue;
        const offender = Object.keys(chunk.modules).find((id) => pattern.test(id));
        if (offender) this.error(`forbidden package in the dashboard bundle: ${offender}`);
      }
    },
  };
}

export default defineConfig(({ command }) => {
  if (command === "build" && process.env.TOMTOM_API_KEY) {
    throw new Error(
      "TOMTOM_API_KEY is set in the frontend build environment. The collector's key must never " +
        "reach a browser; tiles use the separate, domain-restricted TOMTOM_TILE_KEY.",
    );
  }
  return {
    plugins: [forbidPackages()],
    oxc: { jsx: { runtime: "automatic", importSource: "preact" } },
    define: {
      __TOMTOM_TILE_KEY__: JSON.stringify(process.env.TOMTOM_TILE_KEY ?? ""),
    },
    server: {
      proxy: { "/api": "http://127.0.0.1:8000" },
    },
    build: { target: "es2022", sourcemap: true },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
    },
  };
});
