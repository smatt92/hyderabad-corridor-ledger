import type { ComponentChildren, JSX } from "preact";
import { useMemo, useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { Audit as AuditRow, AuditDonor, AuditResponse, AuditSensitivity, Corridor, Intervention } from "../api/types";
import { BlockChart } from "../charts/BlockChart";
import { PlaceboRanks } from "../charts/PlaceboRanks";
import { SlopeChart } from "../charts/SlopeChart";
import {
  type BlockRow, NO_INTERVAL, NO_SEQUENTIAL_TEST, auditPeriods, blockRows, donorStatusText, donorWeightText, estimatorStatement,
  fmtRate, fmtSettling, incompletePreComparison, orderDonors, placeboFloor, placeboResolutionText, postPeriodOpen, rankStdEffects,
  selectionBiasText, sensitivityStatement, sensitivityStatusText, settlingWindow, statusNotice, variantText,
} from "../lib/audit";
import { CARD, FAINT, INK, MID, MONO, RULE, RUST, SOFT, TEXT } from "../lib/color";
import { meetsFloor, resolveFloors } from "../lib/floors";
import { fmtCount, fmtDay, fmtNum, fmtSigned, fmtWindow } from "../lib/format";
import { EM_DASH } from "../lib/route";
import { cache } from "./cache";
import { Notice, SectionHead, Select, StatList, smallCaps } from "./common";

const SUB =
  "Did the works change anything? A synthetic control on the buffer time index: the treated corridor against a weighted blend of donor corridors fitted on its pre-change blocks, tested with placebo runs on every donor and cross-checked against the equal-weight mean of the same donors.";

const th: JSX.CSSProperties = {
  fontSize: "9.5px",
  letterSpacing: ".12em",
  textTransform: "uppercase",
  color: SOFT,
  fontWeight: 500,
  textAlign: "left",
  padding: "0 12px 6px 0",
  borderBottom: `1px solid ${FAINT}`,
  whiteSpace: "nowrap",
  verticalAlign: "bottom",
};
const thRight: JSX.CSSProperties = { ...th, textAlign: "right" };

function cell(extra: JSX.CSSProperties = {}): JSX.CSSProperties {
  return { padding: "7px 12px 7px 0", fontFamily: MONO, fontSize: "11.5px", fontVariantNumeric: "tabular-nums", verticalAlign: "top", color: TEXT, ...extra };
}

function num(extra: JSX.CSSProperties = {}): JSX.CSSProperties {
  return cell({ textAlign: "right", whiteSpace: "nowrap", ...extra });
}

const prose: JSX.CSSProperties = { fontFamily: "inherit", fontSize: "12px", lineHeight: 1.45 };

function count(n: number | null | undefined): string {
  return n != null && Number.isFinite(n) ? String(n) : EM_DASH;
}

function yesNo(v: boolean | null | undefined): string {
  return v == null ? EM_DASH : v ? "yes" : "no";
}

function Section({ title, sub, children }: { title: string; sub?: ComponentChildren; children: ComponentChildren }) {
  return (
    <section style={{ marginTop: "34px", borderTop: `1px solid ${FAINT}`, paddingTop: "16px" }}>
      <div style={{ ...smallCaps, color: MID }}>{title}</div>
      {sub ? <p style={{ margin: "4px 0 12px", fontSize: "12.5px", color: TEXT, maxWidth: "76ch", lineHeight: 1.5 }}>{sub}</p> : <div style={{ height: "10px" }} />}
      {children}
    </section>
  );
}

/** A finding stated in words. Alert statements are rust-ruled so they cannot be skimmed past. */
function Statement({ alert, headline, detail }: { alert: boolean; headline: string; detail: string }) {
  return (
    <div style={{ borderLeft: `3px solid ${alert ? RUST : FAINT}`, background: alert ? "#f6ede4" : "transparent", padding: "8px 12px", fontSize: "13px", lineHeight: 1.55, color: TEXT, maxWidth: "80ch" }}>
      <div style={{ fontWeight: 600, color: alert ? RUST : INK, marginBottom: "2px" }}>{headline}</div>
      <div>{detail}</div>
    </div>
  );
}

/** Until the post period closes, the gap column says in its header that a gap is descriptive, not a test. */
function BlockTable({ rows, floor, postOpen }: { rows: BlockRow[]; floor: number; postOpen: boolean }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "680px" }}>
        <thead>
          <tr>
            <th style={th}>period</th>
            <th style={th}>block</th>
            <th style={th}>dates</th>
            <th style={th}>state</th>
            <th style={thRight}>treated calls</th>
            <th style={thRight}>treated BTI</th>
            <th style={thRight}>synthetic BTI</th>
            <th style={thRight}>{postOpen ? "gap · descriptive, not a test" : "gap"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={8} style={cell({ color: MID })}>No blocks were published.</td>
            </tr>
          ) : null}
          {rows.map((r, i) => (
            <tr key={`${r.period}-${r.block ?? i}`} style={{ borderBottom: `1px solid ${RULE}` }}>
              <td style={cell({ color: MID })}>{r.period}</td>
              <td style={cell()}>{r.block ?? EM_DASH}</td>
              <td style={cell({ whiteSpace: "nowrap" })}>{r.start && r.end ? fmtWindow({ start: r.start, end: r.end }) : EM_DASH}</td>
              <td style={cell({ color: r.complete ? TEXT : MID })}>{r.complete ? "complete" : "open"}</td>
              <td style={num({ color: r.complete && !meetsFloor(r.n, floor) ? RUST : TEXT })}>{fmtCount(r.n, floor)}</td>
              <td style={num()}>{fmtNum(r.treated)}</td>
              <td style={num()}>{fmtNum(r.synthetic)}</td>
              <td style={num()}>{fmtSigned(r.gap)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DonorTable({ donors, floor }: { donors: AuditDonor[]; floor: number }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "980px" }}>
        <thead>
          <tr>
            <th style={th}>corridor</th>
            <th style={thRight}>weight</th>
            <th style={th}>in the donor pool</th>
            <th style={thRight}>pre calls</th>
            <th style={thRight}>post calls</th>
            <th style={thRight}>pre missing</th>
            <th style={thRight}>short pre blocks</th>
            <th style={thRight}>thinnest pre block</th>
            <th style={thRight}>pre BTI</th>
            <th style={thRight}>post BTI</th>
          </tr>
        </thead>
        <tbody>
          {donors.map((d) => {
            const w = d.included && d.weight != null && Number.isFinite(d.weight) ? d.weight : null;
            const ink = d.included ? INK : MID;
            const thin = d.min_pre_block_n != null && !meetsFloor(d.min_pre_block_n, floor);
            return (
              <tr key={d.corridor_id} style={{ borderBottom: `1px solid ${RULE}` }}>
                <td style={cell({ color: ink, whiteSpace: "nowrap" })}>{d.code ?? d.corridor_id}</td>
                <td style={num({ color: ink })}>
                  {w !== null ? (
                    <span style={{ display: "inline-block", width: "44px", height: "6px", background: RULE, marginRight: "8px", verticalAlign: "middle" }}>
                      <span style={{ display: "block", height: "6px", width: `${Math.min(1, Math.max(0, w)) * 100}%`, background: INK }} />
                    </span>
                  ) : null}
                  {donorWeightText(d)}
                </td>
                <td style={cell({ ...prose, minWidth: "30ch", maxWidth: "48ch", color: d.included ? INK : d.exclusion === "same_pair" ? RUST : TEXT })}>{donorStatusText(d, floor)}</td>
                <td style={num({ color: ink })}>{count(d.n_pre)}</td>
                <td style={num({ color: ink })}>{count(d.n_post)}</td>
                <td style={num({ color: ink })}>{fmtRate(d.pre_missing_rate)}</td>
                <td style={num({ color: (d.short_pre_blocks ?? 0) > 0 ? RUST : ink })}>{count(d.short_pre_blocks)}</td>
                <td style={num({ color: thin ? RUST : ink })}>{d.min_pre_block_n == null ? EM_DASH : fmtCount(d.min_pre_block_n, floor)}</td>
                <td style={num({ color: ink })}>{fmtNum(d.pre_bti)}</td>
                <td style={num({ color: ink })}>{fmtNum(d.post_bti)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SensitivityTable({ rows }: { rows: AuditSensitivity[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "1080px" }}>
        <thead>
          <tr>
            <th style={th}>variant</th>
            <th style={thRight}>block floor</th>
            <th style={thRight}>short blocks allowed</th>
            <th style={th}>outcome</th>
            <th style={thRight}>donors</th>
            <th style={thRight}>fit blocks</th>
            <th style={thRight}>effect · no interval</th>
            <th style={thRight}>equal-weight effect</th>
            <th style={th}>placebo test</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={9} style={cell({ color: MID })}>No sensitivity variants were published.</td>
            </tr>
          ) : null}
          {rows.map((r, i) => (
            <tr key={`${r.variant}-${i}`} style={{ borderBottom: `1px solid ${RULE}` }}>
              <td style={cell({ ...prose, minWidth: "26ch", maxWidth: "40ch", color: INK, fontWeight: r.variant === "base" ? 600 : 400 })}>{variantText(r.variant)}</td>
              <td style={num()}>{count(r.block_floor)}</td>
              <td style={num()}>{count(r.max_short_blocks)}</td>
              <td style={cell({ color: r.status === "ok" ? TEXT : RUST })}>{sensitivityStatusText(r.status)}</td>
              <td style={num()}>{count(r.n_donors)}</td>
              <td style={num()}>{count(r.n_fit_blocks)}</td>
              <td style={num()}>{fmtSigned(r.effect)}</td>
              <td style={num()}>{fmtSigned(r.equal_effect)}</td>
              <td style={cell({ whiteSpace: "nowrap" })}>{placeboResolutionText(r.placebo_p_value, r.placebo_rank, r.n_placebos, placeboFloor(r.n_placebos))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Method({ a, floor }: { a: AuditRow; floor: number }) {
  return (
    <p style={{ margin: 0, fontSize: "12px", lineHeight: 1.65, color: TEXT, maxWidth: "88ch" }}>
      <span style={{ fontWeight: 600, color: INK }}>Method.</span> The periods are whole blocks of {a.block_days} days, recorded when the intervention was declared:{" "}
      {a.pre_blocks} pre blocks ({fmtWindow({ start: a.pre_start, end: a.pre_end })}), a settling period of {a.settle_days} days after the change on {fmtDay(a.effective_day)} (
      {fmtSettling(settlingWindow(a))}) that is excluded, and {a.post_blocks} post blocks ({fmtWindow({ start: a.post_start, end: a.post_end })}). Each block’s buffer time index is
      computed once on that block’s pooled peak-hour calls and is used only when the block holds at least {floor} calls, the floor for a 95th percentile. Donor weights are
      fitted on the treated corridor’s demeaned pre-block BTI series: they are non-negative and sum to one, and the difference in level between the treated corridor and its
      donors is absorbed as a fixed shift. The donor pool excludes every treated corridor; the treated corridor’s own pair, because traffic diverting onto the paired alternate
      is a consequence of the intervention, so that corridor is contaminated, not a control; corridors with a pre block below the floor; and, once the post period has closed,
      corridors with too few post-period calls. The headline effect is (treated post − synthetic post) − (treated pre − synthetic pre), each BTI pooled once over its whole
      period, published as a point estimate. {NO_INTERVAL} Placebo runs repeat the procedure with each donor as the treated corridor. Each run’s standardised effect is its
      |effect| divided by its own held-out pre-period RMSPE, the error when each pre block is predicted by weights fitted on the other pre blocks. The treated corridor’s
      standardised effect is ranked among the placebos’, ties counting against it, and the permutation p-value is (1 + placebos at least as large) / (1 + placebos), so it
      can never fall below 1 / (1 + placebos); the effect is called extreme when p ≤ {a.alpha}. A run whose held-out pre error is zero has no standardised effect and is not
      ranked. The post/pre RMSPE ratio is published only as a description of fit. The equal-weight mean of the same donors over the same periods is a cross-check, and the
      two estimates are said to disagree only when their signs are opposite. The audit is rerun with stricter and looser completeness thresholds for donor pre blocks to show
      how far the estimate depends on that choice; the dependence is material when a variant’s effect has the opposite sign or its placebo verdict differs from the
      headline’s. {NO_SEQUENTIAL_TEST} Until the post period closes the headline stays unpublished, and a post block’s gap between treated and
      synthetic BTI is descriptive, not a test. This is not a causal claim beyond the assumption that, without the change, the treated corridor’s BTI would have followed its
      synthetic control.
    </p>
  );
}

export function Audit({ interventions, corridors }: { interventions: Intervention[]; corridors: Corridor[] }) {
  const [id, setId] = useState(interventions[0]?.id ?? "");
  const res = useApi<AuditResponse>(cache, id ? `/api/interventions/${encodeURIComponent(id)}/audit` : null);
  const code = (cid: string) => corridors.find((c) => c.id === cid)?.code ?? cid;
  const audit = res?.ok ? res.data.audit : null;
  const treatedPair = useMemo<[number, number] | null>(
    () => (audit?.treated_pre != null && audit.treated_post != null ? [audit.treated_pre, audit.treated_post] : null),
    [audit],
  );
  const syntheticPair = useMemo<[number, number] | null>(
    () => (audit?.synthetic_pre != null && audit.synthetic_post != null ? [audit.synthetic_pre, audit.synthetic_post] : null),
    [audit],
  );

  const head = (
    <SectionHead
      title="Intervention audit"
      sub={SUB}
      right={
        interventions.length ? (
          <Select label="Intervention" value={id} options={interventions.map((iv) => ({ value: iv.id, label: `${iv.description} · ${code(iv.corridor_id)}` }))} onChange={setId} />
        ) : null
      }
    />
  );

  if (interventions.length === 0) {
    return <div>{head}<Notice kicker="Nothing to audit" title="No interventions are declared">No before/after comparison is drawn until an intervention is declared.</Notice></div>;
  }
  if (res === null) return <div>{head}<div style={{ fontFamily: MONO, fontSize: "12px", color: MID }}>loading…</div></div>;
  if (!res.ok) return <div>{head}<Notice kicker="Degraded" title="Audit unavailable">The read API returned: {res.error}.</Notice></div>;

  const data = res.data;
  const { intervention, corridor } = data;
  const floors = resolveFloors(data.floors);
  const q = floors.p95_min_samples;
  const headline = `${intervention.description} — ${corridor.name}`;
  if (!audit) {
    return <div>{head}<Notice kicker="Not audited yet" title={headline}>The metrics pipeline has not produced an audit for this intervention yet.</Notice></div>;
  }

  const treatedName = corridor.code ?? corridor.id;
  const rows = { pre: blockRows(data.blocks?.pre, "pre"), post: blockRows(data.blocks?.post, "post") };
  const allRows = [...rows.pre, ...rows.post];
  const postOpen = postPeriodOpen(audit);
  const donors = orderDonors(data.donors);
  const placebos = data.placebos ?? [];
  const sensitivityRows = data.sensitivity ?? [];
  const settling = settlingWindow(audit);
  const donorCode = new Map(donors.map((d) => [d.corridor_id, d.code]));
  const label = (cid: string) => (cid === corridor.id ? corridor.code ?? corridor.name : donorCode.get(cid) ?? code(cid));
  const excludedForPre = audit.n_excluded_incomplete_pre;

  const blocksSection = (
    <Section
      title="Blocks"
      sub={
        `Blocks of ${audit.block_days} days. Each block’s BTI is pooled over that block’s peak-hour calls and used only from ${q} calls. The change and the excluded settling period are drawn at their dates.` +
        (postOpen ? " The post period has not closed, so a post block’s gap between treated and synthetic BTI is descriptive, not a test." : "")
      }
    >
      {allRows.some((r) => r.treated !== null || r.synthetic !== null) ? (
        <BlockChart
          rows={allRows}
          preStart={audit.pre_start}
          preEnd={audit.pre_end}
          settling={settling}
          postStart={audit.post_start}
          postEnd={audit.post_end}
          effectiveDay={audit.effective_day}
          floor={q}
          treatedLabel={treatedName}
          syntheticLabel={`${count(audit.n_donors)} ${audit.n_donors === 1 ? "donor" : "donors"}`}
        />
      ) : (
        <div style={{ fontSize: "12.5px", color: MID }}>No block BTI has been published yet.</div>
      )}
      <div style={{ marginTop: "16px" }}>
        <BlockTable rows={allRows} floor={q} postOpen={postOpen} />
      </div>
    </Section>
  );

  const donorSection = (
    <Section
      title="Donor pool"
      sub={`Every candidate corridor with its published weight. Weights are non-negative and sum to one over the ${count(audit.n_donors)} included ${audit.n_donors === 1 ? "donor" : "donors"}; an excluded corridor carries no weight. An opaque counterfactual is not evidence, so no row is left out.`}
    >
      <div style={{ marginBottom: "14px" }}>
        <Statement alert={excludedForPre == null || excludedForPre > 0} headline={incompletePreComparison(audit)} detail={selectionBiasText(q)} />
      </div>
      <DonorTable donors={donors} floor={q} />
    </Section>
  );

  const sensitivity = sensitivityStatement(audit);
  const sensitivitySection = (
    <Section
      title="Sensitivity · completeness threshold"
      sub="The audit rerun under other rules for how complete a donor’s pre blocks must be. The strict variants require every pre block at 1.25× or 1.5× the floor; the relaxed variant admits donors with one short pre block and fits only on the blocks every donor has. The dependence is material when a variant’s effect has the opposite sign or its placebo verdict differs from the headline’s. Effects are point estimates with no interval."
    >
      <div style={{ marginBottom: "14px" }}>
        <Statement alert={sensitivity.tone === "material"} headline={sensitivity.headline} detail={sensitivity.detail} />
      </div>
      <SensitivityTable rows={sensitivityRows} />
    </Section>
  );

  const methodSection = (
    <Section title="Method">
      <Method a={audit} floor={q} />
    </Section>
  );

  const lowConfidence = audit.low_confidence ? (
    <div style={{ marginTop: "8px", fontFamily: MONO, fontSize: "10.5px", color: RUST }}>◌ low confidence · more than 15% of the treated corridor’s samples missing</div>
  ) : null;

  if (audit.status !== "ok") {
    const notice = statusNotice(audit, corridor.name, q, rows) ?? {
      kicker: "Audit withheld",
      body: `The audit reported status “${String(audit.status)}”, which this page does not know how to read, so no estimate is shown.`,
    };
    return (
      <div>
        {head}
        <Notice kicker={notice.kicker} title={headline}>{notice.body}</Notice>
        {audit.status === "post_partial" ? (
          <div style={{ marginTop: "16px", maxWidth: "64ch" }}>
            <StatList
              items={[
                ["completed post blocks", `${audit.post_blocks_complete} of ${audit.post_blocks}`],
                ["sequential test", "none · the audit reports once, after the post period closes"],
                ["post-block gaps", "descriptive, not a test"],
                ["headline effect", `${EM_DASH} waits for the post period to close on ${fmtDay(audit.post_end)}`],
              ]}
            />
          </div>
        ) : null}
        <div style={{ marginTop: "16px", maxWidth: "64ch" }}>
          <StatList items={[["treated corridor", treatedName], ...auditPeriods(audit, q)]} />
          {lowConfidence}
        </div>
        {blocksSection}
        {donors.length ? donorSection : null}
        {sensitivityRows.length ? sensitivitySection : null}
        {methodSection}
      </div>
    );
  }

  const estimators = estimatorStatement(audit);
  const resolution = placeboResolutionText(audit.placebo_p_value, audit.placebo_rank, audit.n_placebos, audit.placebo_p_floor);
  const ranked = rankStdEffects({ corridor_id: corridor.id, stdEffect: audit.std_effect }, placebos);

  return (
    <div>
      {head}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: "28px", alignItems: "start" }}>
        <div>
          {treatedPair && syntheticPair ? (
            <SlopeChart
              treated={treatedPair}
              synthetic={syntheticPair}
              treatedLabel={treatedName}
              syntheticLabel={`Synthetic · ${count(audit.n_donors)} ${audit.n_donors === 1 ? "donor" : "donors"}`}
              preLabel={fmtWindow({ start: audit.pre_start, end: audit.pre_end })}
              postLabel={fmtWindow({ start: audit.post_start, end: audit.post_end })}
              changeDate={fmtDay(audit.effective_day)}
              changeLabel={intervention.description}
            />
          ) : (
            <Notice kicker="Incomplete" title="A period value is missing">The published audit lacks a pre or post BTI for the treated corridor or its synthetic control, so no slope is drawn.</Notice>
          )}
        </div>
        <div style={{ maxWidth: "56ch", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ borderLeft: `2px solid ${INK}`, paddingLeft: "14px" }}>
            <div style={{ fontFamily: MONO, fontSize: "11px", color: RUST, letterSpacing: ".1em" }}>{fmtDay(audit.effective_day)}</div>
            <div style={{ fontSize: "15px", fontWeight: 500, margin: "4px 0 10px" }}>{headline}</div>
            <div style={smallCaps}>synthetic-control effect on BTI</div>
            <div style={{ fontFamily: MONO, fontSize: "28px", fontWeight: 500, color: INK, lineHeight: 1.25, fontVariantNumeric: "tabular-nums" }}>{fmtSigned(audit.effect)}</div>
            <div style={{ fontFamily: MONO, fontSize: "11.5px", color: MID }}>
              point estimate · no interval · the inference is the placebo rank below
            </div>
            <div style={{ fontSize: "13px", lineHeight: 1.55, color: TEXT, marginTop: "10px" }}>
              Pooled over each whole period, the treated corridor’s BTI moved from {fmtNum(audit.treated_pre)} to {fmtNum(audit.treated_post)} and its synthetic control’s from{" "}
              {fmtNum(audit.synthetic_pre)} to {fmtNum(audit.synthetic_post)}. The effect is (treated post − synthetic post) − (treated pre − synthetic pre). The synthetic control
              blends {count(audit.n_donors)} donor {audit.n_donors === 1 ? "corridor" : "corridors"}, each with the weight published in the donor pool below. {NO_INTERVAL}
            </div>
            <div style={{ marginTop: "14px", border: `1.5px solid ${INK}`, background: CARD, padding: "12px 14px" }}>
              <div style={{ fontFamily: MONO, fontSize: "10.5px", letterSpacing: ".16em", textTransform: "uppercase", color: RUST }}>Placebo test · verdict</div>
              <div style={{ fontSize: "15.5px", fontWeight: 500, lineHeight: 1.45, color: INK, margin: "6px 0" }}>
                {audit.placebo_verdict ?? `${EM_DASH} no placebo verdict was published`}
              </div>
              <div style={{ fontFamily: MONO, fontSize: "11.5px", color: MID }}>{resolution}</div>
            </div>
            {estimators.tone === "disagree" ? (
              <div style={{ marginTop: "12px" }}>
                <Statement alert headline={estimators.headline} detail={estimators.detail} />
              </div>
            ) : null}
            {sensitivity.tone === "material" ? (
              <div style={{ marginTop: "12px" }}>
                <Statement alert headline={sensitivity.headline} detail={sensitivity.detail} />
              </div>
            ) : null}
          </div>
          <div style={{ borderTop: `1px solid ${FAINT}`, paddingTop: "12px" }}>
            <StatList
              items={[
                ["treated corridor", treatedName],
                ...auditPeriods(audit, q),
                ["donors", count(audit.n_donors)],
                ["treated BTI pre → post", `${fmtNum(audit.treated_pre)} → ${fmtNum(audit.treated_post)}`],
                ["synthetic BTI pre → post", `${fmtNum(audit.synthetic_pre)} → ${fmtNum(audit.synthetic_post)}`],
                ["estimated effect", `${fmtSigned(audit.effect)} BTI · point estimate, no interval`],
                ["RMSPE pre / post", `${fmtNum(audit.pre_rmspe, 3)} / ${fmtNum(audit.post_rmspe, 3)}`],
                ["RMSPE ratio, post / pre · describes fit, not the test", fmtNum(audit.rmspe_ratio)],
                [
                  "pre RMSPE, one block held out",
                  `${fmtNum(audit.cv_pre_rmspe, 3)}${audit.pre_fit_overfit ? " · in-sample fit far tighter: the weights may be fitting noise" : ""}`,
                ],
                [
                  "standardised effect, |effect| ÷ held-out pre RMSPE · the tested statistic",
                  audit.std_effect == null || !Number.isFinite(audit.std_effect) ? `${EM_DASH} unranked` : fmtNum(audit.std_effect),
                ],
                ["active donors", audit.n_active_donors == null ? "—" : String(audit.n_active_donors)],
                ["placebo test", resolution],
                ["extreme among placebos", yesNo(audit.placebo_extreme)],
                ["method version", audit.method_version],
              ]}
            />
            {lowConfidence}
          </div>
        </div>
      </div>

      {blocksSection}

      <Section
        title="Placebo runs"
        sub="The same procedure repeated with each donor as the treated corridor. Bars are standardised effects, |effect| ÷ held-out pre RMSPE, largest first. A placebo at least as large as the treated corridor’s counts against the effect; a run whose standardised effect could not be computed is listed unranked, not as zero. Ranking the raw |effect| would call a corridor significant just because it is volatile anyway, and the in-sample post/pre RMSPE ratio breaks when the pre fit is exact, because its denominator is then zero. Dividing each corridor’s |effect| by its own held-out pre-period error, measured on pre blocks its weights were not fitted to, avoids both."
      >
        <div style={{ fontFamily: MONO, fontSize: "12px", color: INK, marginBottom: "10px" }}>{resolution}</div>
        {placebos.length === 0 ? <div style={{ fontSize: "12.5px", color: MID, marginBottom: "8px" }}>No placebo runs were published.</div> : null}
        <PlaceboRanks rows={ranked} label={label} />
      </Section>

      <Section
        title="Cross-check · equal-weight donors"
        sub="The equal-weight mean of the same donors over the same periods, a point estimate with no interval. It is not the headline; it shows how far the headline depends on the fitted weights. The two disagree only when their signs are opposite; the gap between them is stated either way."
      >
        <div style={{ marginBottom: "12px" }}>
          <Statement alert={estimators.tone === "disagree"} headline={estimators.headline} detail={estimators.detail} />
        </div>
        <div style={{ maxWidth: "64ch" }}>
          <StatList
            items={[
              ["equal-weight control BTI pre → post", `${fmtNum(audit.equal_control_pre)} → ${fmtNum(audit.equal_control_post)}`],
              ["equal-weight effect", `${fmtSigned(audit.equal_effect)} BTI`],
              ["synthetic-control effect", `${fmtSigned(audit.effect)} BTI`],
              ["estimator gap, synthetic − equal", `${fmtSigned(audit.estimator_gap)} BTI`],
              ["opposite signs, so the estimators disagree", yesNo(audit.estimators_disagree)],
            ]}
          />
        </div>
      </Section>

      {donorSection}
      {sensitivitySection}
      {methodSection}
    </div>
  );
}
