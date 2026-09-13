import { describe, expect, it } from "vitest";
import type { Audit, AuditBlocks, AuditDonor, AuditPlacebo } from "../api/types";
import {
  CAPABILITY, NO_INTERVAL, NO_SEQUENTIAL_TEST, auditPeriods, blockRows, blockSegments, chanceExtremeCount, chanceExtremeText,
  dayNumber, donorStatusText, donorWeightText, estimatorStatement, exclusionText, fmtRate, fmtSettling, incompletePreComparison,
  orderDonors, placeboResolutionText, placeboTestText, postPeriodOpen, rankStdEffects, selectionBiasText, sensitivityStatement,
  sensitivityStatusText, settlingWindow, statusNotice, thinnestBlock, variantText,
} from "./audit";
import { MINUS } from "./format";
import { EM_DASH } from "./route";

const audit: Audit = {
  status: "ok",
  effective_day: "2026-03-02",
  settle_days: 9,
  pre_start: "2025-09-15",
  pre_end: "2026-03-01",
  settle_start: "2026-03-02",
  settle_end: "2026-03-10",
  post_start: "2026-03-11",
  post_end: "2026-04-07",
  block_days: 14,
  pre_blocks: 12,
  post_blocks: 2,
  post_blocks_complete: 2,
  n_pre: 3280,
  n_post: 560,
  n_donors: 4,
  treated_pre: 0.41,
  treated_post: 0.52,
  synthetic_pre: 0.4,
  synthetic_post: 0.43,
  effect: 0.08,
  pre_rmspe: 0.02,
  post_rmspe: 0.09,
  rmspe_ratio: 3,
  std_effect: 2.4,
  n_placebos: 4,
  placebo_p_value: 0.4,
  placebo_extreme: false,
  placebo_verdict: "Not extreme: 1 of 4 placebo runs show a standardised effect at least as large as the treated corridor's.",
  placebo_rank: 2,
  placebo_p_floor: 0.2,
  n_excluded_incomplete_pre: 9,
  included_pre_missing_rate: 0.06,
  excluded_pre_missing_rate: 0.212,
  included_pre_bti: 0.38,
  excluded_pre_bti: 0.52,
  sensitivity_min_effect: 0.05,
  sensitivity_max_effect: 0.11,
  sensitivity_material: false,
  equal_control_pre: 0.38,
  equal_control_post: 0.39,
  equal_effect: 0.1,
  estimator_gap: -0.02,
  estimators_disagree: false,
  alpha: 0.05,
  low_confidence: false,
  method_version: "audit-sc-1",
};

const blocks = (over: Partial<AuditBlocks> = {}): AuditBlocks => ({
  block: [1, 2, 3],
  block_start: ["2025-12-08", "2025-12-22", "2026-01-05"],
  block_end: ["2025-12-21", "2026-01-04", "2026-01-18"],
  complete: [true, true, true],
  n_treated: [250, 143, 300],
  treated_bti: [0.4, null, 0.42],
  synthetic_bti: [0.39, 0.41, 0.4],
  gap: [0.01, null, 0.02],
  ...over,
});

const donor = (over: Partial<AuditDonor>): AuditDonor => ({
  corridor_id: "c", code: null, included: true, weight: null, exclusion: null, n_pre: 1200, n_post: 400, pre_bti: 0.4, post_bti: 0.41, ...over,
});

const placebo = (corridor_id: string, std_effect: number | null | undefined, poor_pre_fit = false, rmspe_ratio: number | null = 1.5): AuditPlacebo => ({
  corridor_id, effect: 0.01, pre_rmspe: 0.02, cv_pre_rmspe: 0.03, std_effect, post_rmspe: 0.03, rmspe_ratio, poor_pre_fit, weights: {},
});

describe("capability", () => {
  it("states what the audit can and cannot detect, verbatim, including that a 56-day post period is untested", () => {
    expect(CAPABILITY.title).toBe("What this audit can and cannot detect");
    expect(CAPABILITY.body).toBe(
      "With 24 weeks of pre-period, 20 Tier A donor corridors and a 28-day post period, it reliably detects a change in the buffer time index of about 0.20, roughly a third of a typical corridor's value. That is the scale of a flyover or grade separation that removes a corridor's recurring breakdown. It cannot detect a signal retiming or a change of similar size, so a “not extreme” verdict for a small intervention says nothing about whether it worked. Tier B corridors cannot be audited. These figures come from simulation with a 28-day post period; a 56-day post period is untested.",
    );
  });
});

describe("periods", () => {
  it("states every period from its recorded dates, settling included", () => {
    expect(auditPeriods(audit, 200)).toEqual([
      ["pre period", "15 Sep 2025–1 Mar 2026 · 12 blocks of 14 d · n = 3280"],
      ["change date", "2 Mar 2026"],
      ["settling, excluded", "2 Mar–10 Mar 2026 · 9 d"],
      ["post period", "11 Mar–7 Apr 2026 · 2 blocks of 14 d · 2 of 2 complete · n = 560"],
      ["block floor", "200 pooled peak-hour calls per block"],
    ]);
  });

  it("takes the pre period's block count, block length and dates from the payload, never from a default", () => {
    const six = { ...audit, pre_start: "2025-12-08", pre_blocks: 6, n_pre: 1640 };
    expect(auditPeriods(six, 200)[0]).toEqual(["pre period", "8 Dec 2025–1 Mar 2026 · 6 blocks of 14 d · n = 1640"]);
    const weekly = { ...audit, block_days: 7, pre_blocks: 24 };
    expect(auditPeriods(weekly, 200)[0]).toEqual(["pre period", "15 Sep 2025–1 Mar 2026 · 24 blocks of 7 d · n = 3280"]);
    const n = statusNotice({ ...six, status: "insufficient_pre" }, "X", 200, { pre: [], post: [] })!;
    expect(n.body).toContain("8 Dec 2025–1 Mar 2026: 6 blocks of 14 days, 1640 calls pooled in total.");
  });

  it("uses recorded settling dates as they are, even where they do not abut the periods", () => {
    const recorded = { ...audit, settle_start: "2026-03-03", settle_end: "2026-03-09" };
    expect(settlingWindow(recorded)).toEqual({ start: { day: "2026-03-03", inferred: false }, end: { day: "2026-03-09", inferred: false } });
    expect(auditPeriods(recorded, 200)[2]).toEqual(["settling, excluded", "3 Mar–9 Mar 2026 · 9 d"]);
  });

  it("labels a derived settling date INFERRED, and only a derived one", () => {
    const absent = { ...audit, settle_start: undefined, settle_end: null };
    expect(fmtSettling(settlingWindow(absent))).toBe("2 Mar 2026 INFERRED–10 Mar 2026 INFERRED");
    expect(auditPeriods(absent, 200)[2]).toEqual(["settling, excluded", "2 Mar 2026 INFERRED–10 Mar 2026 INFERRED · 9 d"]);
    const half = { ...audit, settle_start: "2026-03-03", settle_end: undefined };
    expect(fmtSettling(settlingWindow(half))).toBe("3 Mar 2026–10 Mar 2026 INFERRED");
    const abutting = { ...audit, settle_start: null, settle_end: null, post_start: "2026-03-02" };
    expect(settlingWindow(abutting)).toBe(null);
    expect(fmtSettling(null)).toBe(EM_DASH);
  });

  it("keeps the post period open until every post block has completed", () => {
    expect(postPeriodOpen(audit)).toBe(false);
    expect(postPeriodOpen({ ...audit, status: "post_partial", post_blocks_complete: 1 })).toBe(true);
    expect(postPeriodOpen({ ...audit, status: "post_pending", post_blocks_complete: 0 })).toBe(true);
  });
});

describe("blocks", () => {
  it("turns columns into rows and keeps what is missing as null", () => {
    const rows = blockRows(blocks({ gap: [0.01], synthetic_bti: [0.39, Number.NaN, 0.4] }), "pre");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toMatchObject({ period: "pre", block: 2, n: 143, treated: null, synthetic: null, gap: null });
    expect(rows[2]).toMatchObject({ gap: null, treated: 0.42 });
    expect(blockRows(null, "post")).toEqual([]);
  });

  it("draws one segment per block with a value and leaves a gap for the rest", () => {
    const rows = blockRows(blocks(), "pre");
    expect(blockSegments(rows, (r) => r.treated)).toEqual([
      { x0: dayNumber("2025-12-08"), x1: dayNumber("2025-12-21") + 1, value: 0.4 },
      { x0: dayNumber("2026-01-05"), x1: dayNumber("2026-01-18") + 1, value: 0.42 },
    ]);
  });

  it("finds the thinnest block, treating an unrecorded count as thinnest", () => {
    expect(thinnestBlock(blockRows(blocks(), "pre"))?.n).toBe(143);
    expect(thinnestBlock(blockRows(blocks({ n_treated: [250, null, 100] }), "pre"))?.block).toBe(2);
    expect(thinnestBlock([])).toBe(null);
  });
});

describe("donors", () => {
  it("says why each corridor is excluded, in plain words", () => {
    expect(exclusionText("treated", 200)).toBe("Excluded: treated by a declared intervention or recorded as treated in the works register, so not a control.");
    expect(exclusionText("under_works", 200)).toBe("Excluded: its road is under construction, so it is not a control.");
    expect(exclusionText("same_pair", 200)).toBe(
      "Excluded: on the treated corridor’s own pair. Traffic diverting onto the paired alternate is a consequence of the intervention, so this corridor is contaminated, not a control.",
    );
    expect(exclusionText("incomplete_pre", 200)).toBe("Excluded: a pre block has fewer than 200 pooled peak-hour calls, below the p95 floor.");
    expect(exclusionText("insufficient_post", 200)).toBe("Excluded: too few pooled peak-hour calls in the post period, which has closed.");
    expect(donorStatusText(donor({ included: true }), 200)).toBe("Included");
    expect(donorStatusText(donor({ included: false }), 200)).toBe("Excluded: no reason was recorded.");
  });

  it("prints a weight only for an included donor, an em dash otherwise", () => {
    expect(donorWeightText(donor({ included: true, weight: 0.4567 }))).toBe("0.457");
    expect(donorWeightText(donor({ included: true, weight: 0 }))).toBe("0.000");
    expect(donorWeightText(donor({ included: true, weight: null }))).toBe(EM_DASH);
    expect(donorWeightText(donor({ included: false, weight: 0.3, exclusion: "same_pair" }))).toBe(EM_DASH);
  });

  it("lists every row: included by weight, then excluded by reason", () => {
    const rows = [
      donor({ corridor_id: "e1", code: "E1", included: false, exclusion: "incomplete_pre" }),
      donor({ corridor_id: "a", code: "A", weight: 0.2 }),
      donor({ corridor_id: "e2", code: "E2", included: false, exclusion: "same_pair" }),
      donor({ corridor_id: "b", code: "B", weight: 0.8 }),
      donor({ corridor_id: "n", code: null, weight: null }),
      donor({ corridor_id: "e3", code: "E3", included: false, exclusion: null }),
      donor({ corridor_id: "e4", code: "E4", included: false, exclusion: "treated" }),
    ];
    expect(orderDonors(rows).map((d) => d.corridor_id)).toEqual(["b", "a", "n", "e4", "e2", "e1", "e3"]);
    expect(orderDonors(null)).toEqual([]);
  });

  it("compares corridors dropped for incomplete pre blocks with the donors kept", () => {
    expect(incompletePreComparison(audit)).toBe("Excluded for incomplete pre blocks: 9 corridors, missing 21% of pre calls vs 6% for donors; pre BTI 0.52 vs 0.38.");
    expect(incompletePreComparison({ ...audit, n_excluded_incomplete_pre: 1, excluded_pre_bti: null })).toBe(
      `Excluded for incomplete pre blocks: 1 corridor, missing 21% of pre calls vs 6% for donors; pre BTI ${EM_DASH} vs 0.38.`,
    );
    const absent = { ...audit, n_excluded_incomplete_pre: undefined, included_pre_missing_rate: undefined, excluded_pre_missing_rate: null, included_pre_bti: undefined, excluded_pre_bti: undefined };
    expect(incompletePreComparison(absent)).toBe(
      `Excluded for incomplete pre blocks: ${EM_DASH} corridors, missing ${EM_DASH} of pre calls vs ${EM_DASH} for donors; pre BTI ${EM_DASH} vs ${EM_DASH}.`,
    );
    expect(selectionBiasText(200)).toBe(
      "A corridor with any pre block below 200 pooled peak-hour calls is dropped from the donor pool. Failed calls cluster at peak hours, so the most congested corridors are the most likely to be dropped, and the donor pool is not a random sample of the network.",
    );
    expect(fmtRate(0.064)).toBe("6%");
    expect(fmtRate(undefined)).toBe(EM_DASH);
  });
});

describe("placebo ranking", () => {
  it("ranks by standardised effect, not the RMSPE ratio: largest first, a tie above the treated corridor", () => {
    // RMSPE ratios run the opposite way, so ranking them would reverse this order
    const ranked = rankStdEffects({ corridor_id: "t", stdEffect: 3 }, [
      placebo("c", 1.2, true, 40),
      placebo("d", null, false, 50),
      placebo("b", 3, false, 0.5),
      placebo("a", 5, false, 0.2),
    ]);
    expect(ranked.map((r) => [r.corridor_id, r.stdEffect, r.rank, r.atLeastTreated])).toEqual([
      ["a", 5, 1, true],
      ["b", 3, 2, true],
      ["t", 3, 3, false],
      ["c", 1.2, 4, false],
      ["d", null, null, false],
    ]);
    expect(ranked.find((r) => r.corridor_id === "c")?.poorPreFit).toBe(true);
  });

  it("treats a null standardised effect as unranked, never as zero", () => {
    const ranked = rankStdEffects({ corridor_id: "t", stdEffect: 0.5 }, [placebo("n", null), placebo("z", 0), placebo("u", undefined), placebo("x", Number.NaN)]);
    expect(ranked.map((r) => [r.corridor_id, r.stdEffect, r.rank])).toEqual([
      ["t", 0.5, 1],
      ["z", 0, 2],
      ["n", null, null],
      ["u", null, null],
      ["x", null, null],
    ]);
  });

  it("leaves the treated row unranked when its held-out pre error is zero, and marks no placebo against it", () => {
    const ranked = rankStdEffects({ corridor_id: "t", stdEffect: null }, [placebo("a", 2), placebo("b", null)]);
    expect(ranked.map((r) => [r.corridor_id, r.rank])).toEqual([["a", 1], ["t", null], ["b", null]]);
    expect(ranked.some((r) => r.atLeastTreated)).toBe(false);
    expect(rankStdEffects({ corridor_id: "t", stdEffect: 1.5 }, null)).toHaveLength(1);
  });

  it("never states a bare p: rank, placebo count and floor go with it", () => {
    expect(placeboResolutionText(2 / 26, 2, 25, 1 / 26)).toBe("p = 0.08 · rank 2 of 26 · 25 placebos, floor 1/26 = 0.038");
    expect(placeboResolutionText(0.5, 1, 1, 0.5)).toBe("p = 0.50 · rank 1 of 2 · 1 placebo, floor 1/2 = 0.500");
    expect(placeboResolutionText(null, undefined, null, undefined)).toBe(`p = ${EM_DASH} · rank ${EM_DASH} of ${EM_DASH} · ${EM_DASH} placebos, floor 1/${EM_DASH} = ${EM_DASH}`);
  });

  it("counts the audits in n + 1 that would read extreme by chance", () => {
    expect(chanceExtremeCount(21, 0.05)).toBe(1);
    expect(chanceExtremeText(21, 0.05)).toBe("1 in 22 read extreme by chance");
    expect(chanceExtremeCount(40, 0.05)).toBe(2);
    expect(chanceExtremeText(40, 0.05)).toBe("2 in 41 read extreme by chance");
    expect(chanceExtremeCount(3, 0.05)).toBe(0);
    expect(chanceExtremeText(3, 0.05)).toBe("no effect can read extreme with 3 placebos");
    // alpha × (n + 1) exactly whole: the 1e-9 keeps floating-point error from dropping it
    expect(chanceExtremeText(19, 0.05)).toBe("1 in 20 read extreme by chance");
    expect(chanceExtremeText(9, 0.1)).toBe("1 in 10 read extreme by chance");
    expect(chanceExtremeText(21, undefined)).toBe("1 in 22 read extreme by chance");
    expect(chanceExtremeText(1, 0.05)).toBe("no effect can read extreme with 1 placebo");
    expect(chanceExtremeCount(null, 0.05)).toBe(null);
  });

  it("puts the chance expectation beside every placebo p line", () => {
    expect(placeboTestText(1 / 22, 1, 21, 1 / 22, 0.05)).toBe("p = 0.05 · rank 1 of 22 · 21 placebos, floor 1/22 = 0.045 · 1 in 22 read extreme by chance");
    expect(placeboTestText(0.5, 2, 3, 0.25, 0.05)).toBe("p = 0.50 · rank 2 of 4 · 3 placebos, floor 1/4 = 0.250 · no effect can read extreme with 3 placebos");
  });
});

describe("estimator cross-check", () => {
  it("says plainly when the estimators have opposite signs, with both point estimates", () => {
    const s = estimatorStatement({ ...audit, estimators_disagree: true, equal_effect: -0.05, estimator_gap: 0.13 });
    expect(s.tone).toBe("disagree");
    expect(s.headline).toBe("The two estimators point in opposite directions.");
    expect(s.detail).toBe(
      `Synthetic control: +0.08 BTI. Equal-weight mean of the same donors: ${MINUS}0.05 BTI. Synthetic minus equal-weight: +0.13 BTI. ` +
        "One has BTI rising against the donors and the other falling, so even the direction of the estimate depends on how the donors are weighted, and neither number should be read without the other.",
    );
  });

  it("states a same-direction and an unassessed comparison without dropping a number", () => {
    const agree = estimatorStatement(audit);
    expect(agree.headline).toBe("The two estimators do not point in opposite directions.");
    expect(agree.detail).toContain(`Synthetic minus equal-weight: ${MINUS}0.02 BTI.`);
    const unassessed = estimatorStatement({ ...audit, estimators_disagree: null, equal_effect: null });
    expect(unassessed.headline).toBe("Agreement between the two estimators was not assessed.");
    expect(unassessed.detail).toContain(`Equal-weight mean of the same donors: ${EM_DASH} BTI.`);
  });
});

describe("sensitivity to the completeness threshold", () => {
  it("says plainly when the estimate depends on the threshold", () => {
    const s = sensitivityStatement({ ...audit, sensitivity_material: true, sensitivity_min_effect: -0.03, sensitivity_max_effect: 0.11 });
    expect(s.tone).toBe("material");
    expect(s.headline).toBe("The estimate depends on the completeness threshold.");
    expect(s.detail).toBe(
      `Across the completeness-threshold variants the synthetic-control effect ranges from ${MINUS}0.03 to +0.11 BTI; the headline is +0.08 BTI. ` +
        "At least one variant’s effect has the opposite sign, or its placebo verdict (extreme at p ≤ 0.05 or not) differs from the headline’s.",
    );
  });

  it("covers a stable and an unassessed result", () => {
    expect(sensitivityStatement(audit).headline).toBe("No completeness-threshold variant flips the effect’s sign or changes the placebo verdict.");
    const absent = sensitivityStatement({ ...audit, sensitivity_material: undefined, sensitivity_min_effect: undefined, sensitivity_max_effect: null });
    expect(absent.headline).toBe("Sensitivity to the completeness threshold was not assessed.");
    expect(absent.detail).toContain(`ranges from ${EM_DASH} to ${EM_DASH} BTI`);
  });

  it("names variants and outcomes in plain words", () => {
    expect(variantText("base")).toBe("Base: every pre block at the floor");
    expect(variantText("strict_125")).toBe("Strict: every pre block at 1.25× the floor");
    expect(variantText("strict_150")).toBe("Strict: every pre block at 1.5× the floor");
    expect(variantText("relaxed_one_block")).toBe("Relaxed: donors may have one short pre block; weights fit only on blocks every donor has");
    expect(variantText("strict_200")).toBe("strict_200");
    expect(sensitivityStatusText("no_controls")).toBe("no donor qualifies");
    expect(sensitivityStatusText("too_few_blocks")).toBe("too few common pre blocks to fit");
    expect(sensitivityStatusText(null)).toBe(EM_DASH);
  });
});

describe("no interval", () => {
  it("renders no interval text from a payload without interval fields", () => {
    for (const key of ["ci_low", "ci_high", "equal_ci_low", "equal_ci_high", "resamples"]) expect(audit).not.toHaveProperty(key);
    const statements = [
      estimatorStatement(audit),
      estimatorStatement({ ...audit, estimators_disagree: true }),
      estimatorStatement({ ...audit, estimators_disagree: null }),
      sensitivityStatement(audit),
      sensitivityStatement({ ...audit, sensitivity_material: true }),
      sensitivityStatement({ ...audit, sensitivity_material: null }),
    ].flatMap((s) => [s.headline, s.detail]);
    const notices = (["insufficient_pre", "insufficient_post", "post_pending", "post_partial", "no_controls"] as const).map(
      (status) => statusNotice({ ...audit, status }, "X", 200, { pre: [], post: [] })?.body ?? "",
    );
    for (const text of [...statements, ...notices, ...auditPeriods(audit, 200).flat()]) {
      expect(text).not.toMatch(/interval|bootstrap|resample|excludes zero|\[/i);
    }
  });

  it("states plainly why no interval is published", () => {
    expect(NO_INTERVAL).toBe(
      "No interval is published. A call-level bootstrap interval held its error rate when corridors drifted little from week to week, but when they drifted more, 20% of no-effect intervals excluded zero and coverage fell to 80–86%, and no observable diagnostic told the two cases apart. The inference is the placebo rank and its smallest attainable p.",
    );
  });
});

describe("status notices", () => {
  const rows = { pre: blockRows(blocks(), "pre"), post: [] };

  it("has no notice when the audit is published", () => {
    expect(statusNotice(audit, "Hitec City–Gachibowli", 200, rows)).toBe(null);
  });

  it("withholds on a thin pre period with dates and the count against the floor", () => {
    const n = statusNotice({ ...audit, status: "insufficient_pre" }, "Hitec City–Gachibowli", 200, rows)!;
    expect(n.kicker).toBe("Audit withheld");
    expect(n.body).toContain("15 Sep 2025–1 Mar 2026: 12 blocks of 14 days, 3280 calls pooled in total.");
    expect(n.body).toContain("Its thinnest pre block, 22 Dec 2025–4 Jan 2026, holds n = 143 / 200.");
    expect(n.body).toContain("used only from 200 pooled peak-hour calls");
  });

  it("withholds on a thin post period once it has closed", () => {
    const n = statusNotice({ ...audit, status: "insufficient_post" }, "Hitec City–Gachibowli", 200, { pre: [], post: [] })!;
    expect(n.body).toContain("closed on 7 Apr 2026");
    expect(n.body).toContain("11 Mar–7 Apr 2026: 2 blocks of 14 days, 560 calls pooled in total.");
  });

  it("names the settling period while the post period is pending, marking an inferred date", () => {
    const n = statusNotice({ ...audit, status: "post_pending", post_blocks_complete: 0, settle_start: "2026-03-03" }, "X", 200, rows)!;
    expect(n.kicker).toBe("Post period still open");
    expect(n.body).toContain("The 9-day settling period, 3 Mar–10 Mar 2026, is excluded.");
    expect(n.body).toContain("0 of 2 have completed");
    expect(n.body).toContain("before it closes on 7 Apr 2026");
    expect(n.body).toContain(NO_SEQUENTIAL_TEST);
    const inferred = statusNotice({ ...audit, status: "post_pending", settle_end: null }, "X", 200, rows)!;
    expect(inferred.body).toContain("The 9-day settling period, 2 Mar 2026–10 Mar 2026 INFERRED, is excluded.");
  });

  it("says the audit reports once, after the post period closes, and labels partial post gaps descriptive", () => {
    const partial = { ...audit, status: "post_partial" as const, post_blocks_complete: 1, effect: null };
    const n = statusNotice(partial, "Hitec City–Gachibowli", 200, rows)!;
    expect(n.kicker).toBe("Post period in progress");
    expect(n.body).toContain("stay unpublished until the post period closes on 7 Apr 2026");
    expect(n.body).toContain(NO_SEQUENTIAL_TEST);
    expect(n.body).toContain("The gaps between Hitec City–Gachibowli and its synthetic control in the completed post blocks are descriptive, not a test.");
    expect(n.body).not.toContain("always-valid");
    expect(n.body).not.toContain("read after every block");
  });

  it("states plainly why there is no sequential test", () => {
    expect(NO_SEQUENTIAL_TEST).toBe(
      "The audit reports once, after the post period closes. There is no sequential test: the block confidence sequence was removed because it rejected no-effect panels far more often than its nominal 5%.",
    );
  });

  it("explains that the treated corridor's own pair is never a donor", () => {
    const n = statusNotice({ ...audit, status: "no_controls", n_donors: 0 }, "Hitec City–Gachibowli", 200, rows)!;
    expect(n.body).toContain("The treated corridor’s own pair is never a donor");
    expect(n.body).toContain("at least 200 pooled peak-hour calls in every pre block (12 blocks of 14 days, 15 Sep 2025–1 Mar 2026)");
  });
});
