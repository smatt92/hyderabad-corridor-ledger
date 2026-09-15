import { describe, expect, it } from "vitest";
import type { Result } from "../api/client";
import type { Collection, Envelope } from "../api/types";
import { COLLECTING_UNPUBLISHED, DATA_SOURCES_URL, NOT_STARTED, POSITIONING, UNKNOWN, WALL_NOT_STARTED, collectionAsOf, siteState } from "./collection";

const WALK: Collection = { status: "not_started", basis: "latest walk of the samples chain", as_of: "2026-09-14T23:58:29+00:00" };

function read(collection: Collection | null | undefined): Result<Envelope> {
  return { ok: true, status: 200, data: { as_of: null, missingness_rate: null, collection } };
}

describe("site state", () => {
  it("never shows a broken connection as an empty ledger, or an empty ledger as a broken connection", () => {
    expect(siteState(null)).toBe("loading");
    expect(siteState({ ok: false, status: null, error: "network error" })).toBe("unreachable");
    expect(siteState({ ok: false, status: 502, error: "could not read corridors" })).toBe("unreachable");
    expect(siteState(read(WALK))).toBe("not_started");
    expect(siteState(read({ status: "unknown", basis: "no chain walk and no published metrics", as_of: null }))).toBe("unknown");
    expect(siteState(read({ status: "collecting", basis: "published metrics", as_of: "2026-09-15T21:45:00+00:00" }))).toBe("collecting");
  });

  it("treats a payload without a collection state as collecting, so published data is never hidden", () => {
    expect(siteState(read(undefined))).toBe("collecting");
  });
});

describe("the not-started page", () => {
  it("keeps the positioning line", () => {
    expect(POSITIONING).toBe("Google tells you the fastest route right now. We tell you the most reliable route at 8:40 on a Tuesday.");
  });

  it("says what is measured, that collection has not started, why, what comes next, and where the record is", () => {
    expect(NOT_STARTED.what).toContain("travel time index");
    expect(NOT_STARTED.status).toContain("Collection has not started");
    expect(NOT_STARTED.why).toContain("TomTom");
    expect(NOT_STARTED.why).toContain("open question");
    expect(NOT_STARTED.next).toContain("about 12 to 14 days");
    expect(NOT_STARTED.next).toContain("24-week pre-period");
    expect(DATA_SOURCES_URL).toBe("https://github.com/smatt92/hyderabad-corridor-ledger/blob/main/docs/data-sources.md");
  });

  it("never describes the data as licensed, and states no measurement", () => {
    const text = [NOT_STARTED.what, NOT_STARTED.status, NOT_STARTED.why, NOT_STARTED.next, UNKNOWN.status, COLLECTING_UNPUBLISHED].join(" ");
    expect(text).not.toMatch(/licensed for|open dataset|live/i);
    expect(text).not.toMatch(/\d+(\.\d+)?\s*%/);
  });

  it("states when the status was established, or that it never was", () => {
    expect(collectionAsOf(WALK)).toMatch(/^status from the latest walk of the samples chain, .+ IST$/);
    expect(collectionAsOf(null)).toBe("no check of the sample log has been recorded");
  });

  it("gives the wall the same three facts in its own register", () => {
    expect(WALL_NOT_STARTED.headline).toBe("COLLECTION NOT STARTED");
    expect(WALL_NOT_STARTED.lines).toEqual(["NO CORRIDOR IS MEASURED YET", "DATA LICENSING WITH THE PROVIDER UNRESOLVED"]);
  });
});
