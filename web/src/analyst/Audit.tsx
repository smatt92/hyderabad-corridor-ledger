import { useMemo, useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { Audit as AuditRow, AuditResponse, Corridor, Intervention, Window } from "../api/types";
import { SlopeChart } from "../charts/SlopeChart";
import { FAINT, INK, MID, MONO, RUST, TEXT } from "../lib/color";
import { resolveFloors } from "../lib/floors";
import { addDays, fmtDay, fmtNum, fmtSigned, fmtSignedInterval, fmtWindow, insufficientText, windowDays } from "../lib/format";
import { EM_DASH } from "../lib/route";
import { cache } from "./cache";
import { Notice, SectionHead, Select, StatList } from "./common";

/** The excluded settling period: the days between the end of pre and the start of post. */
function settlingWindow(audit: AuditRow): Window | null {
  const start = addDays(audit.pre_end, 1);
  const end = addDays(audit.post_start, -1);
  return start <= end ? { start, end } : null;
}

function periodText(window: Window, n: number | null): string {
  const days = windowDays(window);
  return `${fmtWindow(window)}${days ? ` · ${days} d` : ""}${n == null ? "" : ` · n = ${n}`}`;
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
  const controlPair = useMemo<[number, number] | null>(
    () => (audit?.control_pre != null && audit.control_post != null ? [audit.control_pre, audit.control_post] : null),
    [audit],
  );

  const head = (
    <SectionHead
      title="Intervention audit"
      sub="Did the works change anything? A difference in differences on the buffer time index: the treated corridor’s change between two fixed periods, minus the mean change of untreated corridors. Each period’s BTI is computed once on its pooled peak-hour calls."
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

  const { intervention, corridor } = res.data;
  const floors = resolveFloors(res.data.floors);
  const q = floors.p95_min_samples;
  const headline = `${intervention.description} — ${corridor.name}`;
  if (!audit) {
    return <div>{head}<Notice kicker="Not audited yet" title={headline}>The metrics pipeline has not produced an audit for this intervention yet.</Notice></div>;
  }

  const pre: Window = { start: audit.pre_start, end: audit.pre_end };
  const post: Window = { start: audit.post_start, end: audit.post_end };
  const settle = settlingWindow(audit);
  const settleText = `${settle ? `${fmtWindow(settle)} · ` : ""}${audit.settle_days} d, excluded`;
  const treatedName = corridor.code ?? corridor.id;
  const pending = audit.status === "post_pending";

  const periods = (
    <div style={{ marginTop: "16px", maxWidth: "58ch" }}>
      <StatList
        items={[
          ["treated corridor", treatedName],
          ["pooled", "successful peak-hour calls, one BTI per period"],
          ["pre period", periodText(pre, audit.n_pre)],
          ["change date", fmtDay(audit.effective_day)],
          ["settling", settleText],
          ["post period", pending ? `${periodText(post, null)} · closes ${fmtDay(audit.post_end)}` : periodText(post, audit.n_post)],
          ["publication floor", `${q} pooled calls per period`],
        ]}
      />
    </div>
  );

  if (audit.status !== "ok") {
    const withheld: Record<Exclude<AuditRow["status"], "ok">, [string, string]> = {
      insufficient_pre: [
        "Audit withheld",
        `The pre period (${fmtWindow(pre)}) holds too few pooled peak-hour calls on ${corridor.name} to compute its buffer time index: ${insufficientText(audit.n_pre, q)}. BTI rests on a 95th percentile, so it is published only from ${q} pooled calls in a period. The periods were fixed when the intervention was declared and are not widened to reach the floor.`,
      ],
      insufficient_post: [
        "Audit withheld",
        `The post period (${fmtWindow(post)}) closed with too few pooled peak-hour calls on ${corridor.name}: ${insufficientText(audit.n_post, q)}. BTI rests on a 95th percentile, so it is published only from ${q} pooled calls in a period. The periods were fixed when the intervention was declared and are not widened to reach the floor.`,
      ],
      post_pending: [
        "Post period still open",
        `The post period runs ${fmtWindow(post)} and ends on ${fmtDay(audit.post_end)}. The audit is published only once it has closed, so its numbers do not move when it is re-read. The ${audit.settle_days} days after the change${settle ? ` (${fmtWindow(settle)})` : ""} are excluded as settling time.`,
      ],
      no_controls: [
        "Audit withheld",
        `No untreated corridor has enough pooled peak-hour calls in both periods (at least ${q} in each), so there is no control to difference against, and none is built from thinner data.`,
      ],
    };
    const [kicker, reason] = withheld[audit.status];
    return (
      <div>
        {head}
        <Notice kicker={kicker} title={headline}>{reason}</Notice>
        {periods}
      </div>
    );
  }

  const confidence = Math.round((1 - audit.alpha) * 100);
  const excludesZero = audit.ci_low != null && audit.ci_high != null && (audit.ci_low > 0 || audit.ci_high < 0);
  const controls = Object.keys(audit.weights).map(code);
  const weight = Object.values(audit.weights)[0];
  const controlsText = controls.length > 6 ? `${controls.slice(0, 6).join(" · ")} · +${controls.length - 6} more` : controls.join(" · ");
  const preDays = windowDays(pre);
  const postDays = windowDays(post);

  return (
    <div>
      {head}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: "28px", alignItems: "start" }}>
        <div>
          {treatedPair && controlPair ? (
            <SlopeChart
              treated={treatedPair}
              control={controlPair}
              treatedLabel={corridor.code ?? corridor.name}
              controlLabel={`Control · mean of ${audit.n_controls}`}
              preLabel={fmtWindow(pre)}
              postLabel={fmtWindow(post)}
              changeDate={fmtDay(audit.effective_day)}
              changeLabel={intervention.description}
            />
          ) : (
            <Notice kicker="Incomplete" title="A period value is missing">The published audit lacks a pre or post BTI for the treated corridor or the control, so no slope is drawn.</Notice>
          )}
        </div>
        <div style={{ maxWidth: "52ch", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ borderLeft: `2px solid ${INK}`, paddingLeft: "14px" }}>
            <div style={{ fontFamily: MONO, fontSize: "11px", color: RUST, letterSpacing: ".1em" }}>{fmtDay(audit.effective_day)}</div>
            <div style={{ fontSize: "15px", fontWeight: 500, margin: "4px 0 6px" }}>{headline}</div>
            <div style={{ fontSize: "13px", lineHeight: 1.55, color: TEXT }}>
              Buffer time index on the treated corridor moved from {fmtNum(audit.treated_pre)} to {fmtNum(audit.treated_post)}; the equal-weight control of {audit.n_controls} untreated {audit.n_controls === 1 ? "corridor" : "corridors"} moved from {fmtNum(audit.control_pre)} to {fmtNum(audit.control_post)}. The estimated effect is the difference between those two changes, {fmtSigned(audit.effect)} BTI, with a {confidence}% bootstrap interval from {fmtSigned(audit.ci_low)} to {fmtSigned(audit.ci_high)}.
            </div>
            <div style={{ fontSize: "12px", lineHeight: 1.55, color: TEXT, marginTop: "10px" }}>
              Method. The periods were fixed when the intervention was declared: {preDays ?? EM_DASH} days before the change ({fmtWindow(pre)}), a {audit.settle_days}-day settling period after it that is excluded{settle ? ` (${fmtWindow(settle)})` : ""}, and {postDays ?? EM_DASH} days after that ({fmtWindow(post)}). BTI is computed once on all pooled peak-hour calls in each period — {audit.n_pre} calls before and {audit.n_post} after on the treated corridor — never as an average of daily BTIs, because averaging daily values would let a change in how densely a period was sampled manufacture an effect. The control values are the equal-weight mean of the untreated corridors’ pooled BTIs. The effect is (treated post − treated pre) − (control post − control pre), in BTI units, and its {confidence}% interval is a percentile bootstrap from {audit.resamples} resamples of calls within each corridor and period. The audit is published only after the post period closed on {fmtDay(audit.post_end)}, so these numbers do not move when the page is re-read: it is a fixed-horizon estimate, not a sequential one. It is not a causal claim beyond the assumption that, without the change, the treated corridor’s BTI would have moved as the controls’ did.
            </div>
          </div>
          <div style={{ borderTop: `1px solid ${FAINT}`, paddingTop: "12px" }}>
            <StatList
              items={[
                ["treated", treatedName],
                ["change date", fmtDay(audit.effective_day)],
                ["pre period", periodText(pre, audit.n_pre)],
                ["settling", settleText],
                ["post period", periodText(post, audit.n_post)],
                ["pooled", "peak-hour calls, one BTI per period"],
                ["publication floor", `${q} pooled calls per period`],
                ["controls", weight == null ? String(audit.n_controls) : `${audit.n_controls} · equal weight ${weight.toFixed(2)} each`],
                ["control corridors", controlsText || EM_DASH],
                ["treated BTI pre → post", `${fmtNum(audit.treated_pre)} → ${fmtNum(audit.treated_post)}`],
                ["control BTI pre → post", `${fmtNum(audit.control_pre)} → ${fmtNum(audit.control_post)}`],
                ["estimated effect", `${fmtSignedInterval(audit.effect, audit.ci_low, audit.ci_high)} BTI`],
                [`${confidence}% bootstrap interval`, `${fmtSigned(audit.ci_low)} to ${fmtSigned(audit.ci_high)}`],
                ["bootstrap resamples", String(audit.resamples)],
                ["interval excludes zero", excludesZero ? "yes" : "no"],
                ["method version", audit.method_version],
              ]}
            />
            {audit.low_confidence ? <div style={{ marginTop: "8px", fontFamily: MONO, fontSize: "10.5px", color: RUST }}>◌ low confidence · more than 15% of the treated corridor’s samples missing</div> : null}
          </div>
          <div style={{ fontSize: "11px", color: MID, lineHeight: 1.5 }}>The annotation is part of the chart, not a tooltip. A reader who prints this page still gets the argument.</div>
        </div>
      </div>
    </div>
  );
}
