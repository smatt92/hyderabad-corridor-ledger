import { describe, expect, it } from "vitest";
import { refuseForbiddenEnv } from "../../vite.config";

// Vercel gives every service in a project the same variables, so this build is the gate
// that keeps the service key and the collector's TomTom key off the deployment entirely.
describe("the build environment", () => {
  it("fails the build when the Supabase service key is present", () => {
    expect(() => refuseForbiddenEnv({ SUPABASE_SERVICE_KEY: "set" })).toThrow(/SUPABASE_SERVICE_KEY is set in the build environment/);
  });

  it("fails the build when the collector's TomTom key is present", () => {
    expect(() => refuseForbiddenEnv({ TOMTOM_API_KEY: "set" })).toThrow(/TOMTOM_API_KEY is set in the build environment/);
  });

  it("builds with the variables a deployment is meant to have", () => {
    const env = { SUPABASE_URL: "https://example.supabase.co", SUPABASE_PUBLISHABLE_KEY: "publishable", TOMTOM_TILE_KEY: "tiles", VERCEL: "1" };
    expect(() => refuseForbiddenEnv(env)).not.toThrow();
  });
});
