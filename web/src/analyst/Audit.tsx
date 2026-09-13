import { useState } from "preact/hooks";
import { useApi } from "../api/hooks";
import type { AuditResponse, Corridor, Intervention } from "../api/types";
import { SlopeChart } from "../charts/SlopeChart";
import { FAINT, INK, MID, MONO, RUST, TEXT } from "../lib/color";
import { fmtDay, fmtNum, fmtSigned } from "../lib/format";
import { cache } from "./cache";
import { Notice, SectionHead, Select, StatList } from "./common";

export function Audit({ interventions, corridors }: { interventions: Intervention[]; corridors: Corridor[] }) {
  const [id, setId] = useState(interventions[0]?.id ?? "");
  const res = useApi<AuditResponse>(cache, id ? `/api/interventions/${encodeURIComponent(id)}/audit` : null);
  const code = (cid: string) => corridors.find((c) => c.id === cid)?.code ?? cid;

  const head = (
    <SectionHead
      title="Intervention audit"
      sub="Did the works change anything? Treated corridor against a synthetic control: untreated corridors weighted to match its pre-period daily buffer time index."
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

  const { intervention, corridor, audit } = res.data;
  const headline = `${intervention.description} — ${corridor.name}`;
  if (!audit) {
    return <div>{head}<Notice kicker="Not audited yet" title={headline}>The metrics pipeline has not produced an audit for this intervention yet.</Notice></div>;
  }
  if (audit.status !== "ok") {
    const reason = {
      insufficient_pre: `Only ${audit.n_pre} pre-period days have data. A synthetic control needs at least 14 before it can be matched.`,
      no_controls: "No untreated corridor has complete data across the pre-period, so no synthetic control can be built without filling gaps — and gaps are never filled.",
      no_post: `The post-period has no usable days yet. The ${audit.settle_days} days after the change are excluded as settling time.`,
    }[audit.status];
    return <div>{head}<Notice kicker="Audit withheld" title={headline}>{reason}</Notice></div>;
  }

  const confidence = Math.round((1 - audit.alpha) * 100);
  const excludesZero = audit.cs_low != null && audit.cs_high != null && (audit.cs_low > 0 || audit.cs_high < 0);
  const weights = Object.entries(audit.weights)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([cid, w]) => `${code(cid)} ${w.toFixed(2)}`)
    .join(" · ");

  return (
    <div>
      {head}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: "28px", alignItems: "start" }}>
        <div>
          <SlopeChart
            treated={[audit.treated_pre!, audit.treated_post!]}
            synthetic={[audit.synthetic_pre!, audit.synthetic_post!]}
            treatedLabel={corridor.code ?? corridor.name}
            changeDate={fmtDay(audit.effective_day)}
            changeLabel={intervention.description}
          />
        </div>
        <div style={{ maxWidth: "48ch", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ borderLeft: `2px solid ${INK}`, paddingLeft: "14px" }}>
            <div style={{ fontFamily: MONO, fontSize: "11px", color: RUST, letterSpacing: ".1em" }}>{fmtDay(audit.effective_day)}</div>
            <div style={{ fontSize: "15px", fontWeight: 500, margin: "4px 0 6px" }}>{headline}</div>
            <div style={{ fontSize: "13px", lineHeight: 1.55, color: TEXT }}>
              Buffer time index on the treated corridor moved from {fmtNum(audit.treated_pre)} to {fmtNum(audit.treated_post)}, while the synthetic control — anchored to the same pre-period value by construction — moved to {fmtNum(audit.synthetic_post)}. The estimated effect is the gap between the two post-period values, {fmtSigned(audit.effect)} BTI, with an always-valid {confidence}% confidence sequence from {fmtSigned(audit.cs_low)} to {fmtSigned(audit.cs_high)}, so it can be read every day without inflating error. The {audit.settle_days} days after the change are excluded as a settling period. This is not a causal claim beyond the matching assumption.
            </div>
          </div>
          <div style={{ borderTop: `1px solid ${FAINT}`, paddingTop: "12px" }}>
            <StatList
              items={[
                ["treated", corridor.code ?? corridor.id],
                ["change date", fmtDay(audit.effective_day)],
                ["pre window", `${audit.n_pre} d`],
                ["post window", `${audit.n_post} d`],
                ["controls weighted", String(audit.n_controls)],
                ["largest weights", weights || "—"],
                ["pre-period fit RMSE", fmtNum(audit.pre_rmse, 3)],
                ["settling excluded", `${audit.settle_days} d`],
                ["estimated effect", `${fmtSigned(audit.effect)} BTI`],
                [`${confidence}% conf. sequence`, `${fmtSigned(audit.cs_low)} to ${fmtSigned(audit.cs_high)}`],
                ["interval excludes zero", excludesZero ? "yes" : "no"],
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
