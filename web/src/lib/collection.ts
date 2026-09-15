import type { Result } from "../api/client";
import type { Collection, Envelope } from "../api/types";
import { fmtIst } from "./format";

/**
 * The states every view tells apart. Zero rows and a broken connection mean
 * different things and never look the same, for the same reason a gap is drawn
 * as a gap and never interpolated: an absence is shown with its reason.
 *
 * - unreachable: the API or its database could not be read. The degraded state.
 * - not_started: the database was read, and nothing has been collected.
 * - unknown: the database was read, but nothing says whether collection has started.
 * - collecting: the normal views, with their counts and visible gaps.
 */
export type SiteState = "loading" | "unreachable" | "not_started" | "unknown" | "collecting";

export function siteState<T extends Envelope>(result: Result<T> | null): SiteState {
  if (result === null) return "loading";
  if (!result.ok) return "unreachable";
  const status = result.data.collection?.status;
  if (status === "not_started") return "not_started";
  if (status === "unknown") return "unknown";
  return "collecting";
}

/** When the status was established, and from what, or that it never was. */
export function collectionAsOf(collection: Collection | null | undefined): string {
  if (!collection?.as_of) return "no check of the sample log has been recorded";
  return `status from the ${collection.basis}, ${fmtIst(collection.as_of)}`;
}

export const POSITIONING =
  "Google tells you the fastest route right now. We tell you the most reliable route at 8:40 on a Tuesday.";

export const DATA_SOURCES_URL = "https://github.com/smatt92/hyderabad-corridor-ledger/blob/main/docs/data-sources.md";

export const NOT_STARTED = {
  kicker: "Collection not started",
  title: "Nothing has been measured yet",
  what:
    "The ledger is built to time fixed road corridors in Hyderabad at scheduled times every day, and to publish how reliable each one is: how much slower than free flow it runs (the travel time index), and how much extra time its worst trips demand (the buffer and planning time indices). Every measurement goes into a hash-chained log, so anyone can check that the record has not been rewritten, and whether road works changed a corridor's travel times can be tested independently.",
  status: "Collection has not started. No corridor is active, and the log holds no measurements.",
  why:
    "The travel times would come from TomTom's routing service. Whether TomTom's terms allow storing those results and publishing statistics derived from them is an open question with TomTom, and nothing is collected until it is settled.",
  next:
    "Once collection starts, hourly travel times appear after the first nightly run. The buffer and planning time indices need 200 pooled peak-hour calls per corridor, about 12 to 14 days at 30-minute sampling. An intervention audit needs a 24-week pre-period before the change it examines.",
  link: "The full record of data sources and the licensing question",
} as const;

export const UNKNOWN = {
  kicker: "Collection status unknown",
  title: "Nothing is published",
  status:
    "The database is reachable, but no walk of the sample log has been recorded and no metrics are published, so this page cannot say whether collection has started.",
} as const;

export const COLLECTING_UNPUBLISHED =
  "Collection has started, but no nightly metrics run has published results yet. Hourly travel times appear after the first run, and the buffer and planning time indices after about 12 to 14 days of peak-hour calls at 30-minute sampling.";

export const WALL_NOT_STARTED = {
  headline: "COLLECTION NOT STARTED",
  unknown: "COLLECTION STATUS UNKNOWN",
  lines: ["NO CORRIDOR IS MEASURED YET", "DATA LICENSING WITH THE PROVIDER UNRESOLVED"],
} as const;
