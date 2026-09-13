import { Cache } from "../api/client";

/** Analyst mode reads each path once per session; metrics change daily. */
export const cache = new Cache();
