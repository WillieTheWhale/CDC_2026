// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
"use client";

// Drilldown drawer for one /api/evidence/value/{id}: value -> formula/version
// -> exact input rows -> source link, edition and original workbook cells.

import { useEffect, useRef, useState } from "react";
import { ExternalLink, X } from "lucide-react";
import { loadEvidenceValue, loadResearchModel } from "@/lib/observed-data";
import {
  marketUnitLabel,
  RESEARCH_MODEL_LABEL,
  type ApiEvidenceInput,
  type ApiEvidenceValue,
} from "@/lib/evidence-api";
import "./evidence-value-detail.css";

function num(value: number | null | undefined) {
  if (value == null) return "Unavailable";
  if (value !== 0 && Math.abs(value) < 1) return value.toLocaleString("en-US", { maximumSignificantDigits: 4 });
  return value.toLocaleString("en-US", { maximumFractionDigits: 3 });
}

function words(value: string) {
  return value.replaceAll("_", " ");
}

function Cells({ input }: { input: ApiEvidenceInput }) {
  const row = input.source_row;
  if (!row?.cells.length) return null;
  return (
    <details className="evd-cells">
      <summary>
        Original cells · {row.sheet}, row {row.row_no} ({row.cells.length})
      </summary>
      <table>
        <thead>
          <tr><th>Col</th><th>Cell text</th><th>Type</th></tr>
        </thead>
        <tbody>
          {row.cells.map((cell) => (
            <tr key={cell.col_no}>
              <td>{cell.col_no}</td>
              <td className={cell.italic ? "italic" : undefined}>
                {cell.value_text || <span className="evd-muted">blank</span>}
                {cell.italic ? " (italic in source)" : ""}
              </td>
              <td>{cell.value_type ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function InputRow({ input }: { input: ApiEvidenceInput }) {
  return (
    <li className="evd-input">
      <div className="evd-input-head">
        <strong>{words(input.role)}</strong>
        <b>
          {num(input.input_value)} {input.input_unit ? marketUnitLabel(input.input_unit) : "unit not stated in source"}
        </b>
      </div>
      <p>
        Observation year {input.observation_year ?? "unspecified"} · source edition{" "}
        {input.publication_year ?? "not stated by source"}
        {input.edition != null && input.edition !== input.publication_year ? ` · annex edition ${input.edition}` : ""}
      </p>
      {input.transform && <p>Transform: {input.transform}</p>}
      {input.world_bank && (
        <p>
          World Bank {input.world_bank.indicator_code} (source {input.world_bank.source_id}) · lastupdated{" "}
          {input.world_bank.lastupdated ?? "unstated"}
          {input.world_bank.lastupdated_note ? ` (${input.world_bank.lastupdated_note})` : ""}
        </p>
      )}
      {input.editions && input.editions.length > 0 && (
        <p>
          Published editions: {input.editions.map((e) => `${e.edition}: ${num(e.kg)} kg`).join(" · ")}
          {input.revision_label ? ` · ${input.revision_label}` : ""}
        </p>
      )}
      <p className="evd-source">
        {input.source_url ? (
          <a href={input.source_url} target="_blank" rel="noreferrer">
            {input.source_title || input.source_id || "Source"} <ExternalLink size={10} />
          </a>
        ) : (
          <span>{input.source_title || "Source link unavailable"}</span>
        )}
        <span className="evd-key">{input.source_key}</span>
      </p>
      <Cells input={input} />
    </li>
  );
}

/** Small note shown whenever data comes from the packaged observed-v2 snapshot. */
export function SnapshotNote({ origin, reason }: { origin: "api" | "snapshot" | null; reason?: string }) {
  if (origin !== "snapshot") return null;
  return (
    <span className="evd-snapshot" role="status" title={reason ? `Live evidence API unavailable: ${reason}` : undefined}>
      Showing packaged snapshot{reason ? " (live evidence API unavailable)" : ""}
    </span>
  );
}

export function EvidenceValueDrawer({ valueId, onClose }: { valueId: string | null; onClose: () => void }) {
  const [value, setValue] = useState<ApiEvidenceValue | null>(null);
  const [modelNote, setModelNote] = useState<string | null>(null);
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!valueId) return;
    let active = true;
    setValue(null);
    setError("");
    setModelNote(null);
    loadEvidenceValue(valueId)
      .then((body) => {
        if (!active) return;
        setValue(body.data);
        if (body.data.kind === "research")
          loadResearchModel()
            .then((model) => { if (active) setModelNote(model.data.interpretation); })
            .catch(() => undefined);
      })
      .catch((cause) => { if (active) setError((cause as Error).message); });
    return () => { active = false; };
  }, [valueId]);
  useEffect(() => {
    if (!valueId) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [valueId, onClose]);
  if (!valueId) return null;
  const research = value?.kind === "research";
  return (
    <div className="evd-overlay" onClick={onClose}>
      <aside
        className="evd-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Evidence value drilldown"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <span className="evd-kicker">
            {value ? (research ? "Research value · retrospective" : "Market derivation · descriptive") : "Evidence value"} · #{valueId}
          </span>
          <button ref={closeRef} className="evd-close" onClick={onClose} aria-label="Close drilldown"><X size={15} /></button>
        </header>
        {error ? (
          <p className="evd-empty">This value could not load: {error}</p>
        ) : !value ? (
          <p className="evd-empty">Loading value, formula and source rows…</p>
        ) : (
          <>
            <h2>{value.label}</h2>
            <p className="evd-value">
              <b>{num(value.value)}</b> {marketUnitLabel(value.unit)}
              <span>{[value.iso3, value.drug, value.year].filter((part) => part != null).join(" · ")}</span>
            </p>
            {research && (
              <p className="evd-flag">
                {RESEARCH_MODEL_LABEL}
                {modelNote ? ` ${modelNote}` : ""}
              </p>
            )}
            {value.market && (
              <p className="evd-note">
                Product {value.market.substance}
                {value.market.form ? ` · ${value.market.form}` : ""}
                {value.market.market_level ? ` · ${value.market.market_level}` : ""}. Descriptive price contrast, not a
                margin, route gradient or corridor signal.
              </p>
            )}
            <dl className="evd-grid">
              <dt>Formula</dt>
              <dd className="evd-mono">{value.formula.expression}</dd>
              <dt>Version</dt>
              <dd>{value.formula.version != null ? `Definition v${value.formula.version}` : "Unversioned market eligibility rule"}</dd>
              {value.formula.selection_rule && (<><dt>Selection</dt><dd>{value.formula.selection_rule}</dd></>)}
              {value.formula.interpretation && (<><dt>Interpretation</dt><dd>{value.formula.interpretation}</dd></>)}
              <dt>Observation year</dt>
              <dd>{value.observation_year ?? "unspecified"}</dd>
              <dt>Source edition</dt>
              <dd>
                {value.source_publication_year ?? "not stated by source"}
                {value.first_publication_year != null &&
                value.last_publication_year != null &&
                value.first_publication_year !== value.last_publication_year
                  ? ` (inputs published ${value.first_publication_year}–${value.last_publication_year})`
                  : ""}
                <small> Publication year of the source, not the collection date.</small>
              </dd>
              <dt>Support</dt>
              <dd>{value.support_count} linked input rows. {value.support_count_basis}</dd>
              <dt>Quality flags</dt>
              <dd>
                {value.quality_flags.length
                  ? value.quality_flags.map((flag) => <span key={flag} className="evd-chip">{words(flag)}</span>)
                  : "None recorded"}
              </dd>
              {value.revision_label && (<><dt>Revision</dt><dd>{value.revision_label}</dd></>)}
              {value.caveat && (<><dt>Caveat</dt><dd>{value.caveat}</dd></>)}
              {value.regression_sample && (
                <>
                  <dt>Model sample</dt>
                  <dd>
                    Seizure year {value.regression_sample.seizure_year} → outcome year {value.regression_sample.outcome_year} ·
                    log(1+kg) {num(value.regression_sample.log1p_seizure_kg)} · homicide {num(value.regression_sample.homicide_per_100k)} per 100,000
                  </dd>
                </>
              )}
              <dt>Source</dt>
              <dd>
                {value.source_url ? (
                  <a href={value.source_url} target="_blank" rel="noreferrer">
                    {value.source_title || "Source"} <ExternalLink size={10} />
                  </a>
                ) : (
                  value.source_title || "Source link unavailable"
                )}
                {value.market?.source.sha256 && <small className="evd-key"> sha256 {value.market.source.sha256.slice(0, 12)}…</small>}
              </dd>
            </dl>
            <h3>Inputs ({value.inputs.length})</h3>
            <ul className="evd-inputs">
              {value.inputs.map((input, index) => <InputRow key={`${input.source_key}:${index}`} input={input} />)}
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}
