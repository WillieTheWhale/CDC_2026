// AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
// Route details for one estimated local-flow arrow: the full chain (corridor
// origin country -> entry city -> onward cities), drug, strength, distance and
// wave, plus the modeled corridors that feed it with links to their published
// evidence. Estimates only: not observed, never used in any score.
"use client";
import { useEffect, useId, useRef, useState } from "react";
import type { Edge } from "@/lib/types";
import { drugColor, drugLabel } from "@/lib/api";
import { evidenceForEdge } from "@/lib/route-evidence";
import { useRouteEvidence } from "@/lib/route-evidence-store";
import {
  ESTIMATE_BASIS,
  corridorLabel,
  flowLine,
  pickLabel,
  routeSteps,
  waveLabel,
  type EstimatedFlow,
} from "@/lib/estimated-flows";
import "./estimated-route-detail.css";

export default function EstimatedRouteDetail({
  flow,
  flows,
  edges,
  onClose,
}: {
  flow: EstimatedFlow;
  flows: EstimatedFlow[];
  edges: Edge[];
  onClose: () => void;
}) {
  const [open, setOpen] = useState(true);
  const id = useId();
  const close = useRef<HTMLButtonElement>(null);
  const { index } = useRouteEvidence();
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  // Focus the panel's close button when a route opens; Esc closes from anywhere.
  useEffect(() => {
    close.current?.focus({ preventScroll: true });
  }, [flow]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  const steps = routeSteps(flow, flows);
  const departure = flow.pick === "departure";
  return (
    <section
      className="estimated-route-detail"
      role="dialog"
      aria-modal="false"
      aria-labelledby={`${id}-title`}
      style={{ ["--drug" as string]: drugColor[flow.drug] }}
    >
      <button ref={close} type="button" className="erd-close" aria-label="Close route details (Esc)" onClick={onClose}>
        ×
      </button>
      <b id={`${id}-title`}>Estimated local flow</b>
      <p className="erd-line">{flowLine(flow)}</p>
      <button
        type="button"
        className="erd-toggle"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={() => setOpen((v) => !v)}
      >
        Route details <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div id={`${id}-body`} className="erd-body">
          <ol className="erd-chain" aria-label="Estimated route, origin first">
            {steps.map((s, i) => (
              <li key={i} className={`erd-step ${s.kind}`}>
                <span className="erd-place">{s.label}</span>
                <small>
                  {s.kind === "origin"
                    ? departure
                      ? "corridor origin"
                      : "corridor origin (modeled)"
                    : s.kind === "entry"
                      ? departure
                        ? "departure city (faces the corridor)"
                        : "entry city (modeled corridors deliver here)"
                      : [
                          `${s.km} km`,
                          s.strength != null ? `strength ${s.strength.toFixed(2)}` : null,
                          s.generation ? `wave ${s.generation}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                </small>
              </li>
            ))}
          </ol>
          <dl className="erd-facts">
            <dt>Drug</dt>
            <dd>{drugLabel[flow.drug] ?? flow.drug}</dd>
            <dt>Strength</dt>
            <dd>{flow.strength.toFixed(2)} (0–1 within drug and year)</dd>
            <dt>Distance</dt>
            <dd>{Math.round(flow.km)} km, great circle</dd>
            <dt>Wave</dt>
            <dd>{waveLabel(flow)}</dd>
          </dl>
          <p className="erd-why">{pickLabel[flow.pick]}</p>
          <h4>{departure ? "Modeled corridors leaving this country" : "Modeled corridors feeding this route"}</h4>
          {flow.corridors.length ? (
            <ul className="erd-corridors">
              {flow.corridors.map((c) => {
                const edge = edges.find((e) => e.id === c.id);
                const records = evidenceForEdge(index, edge ?? { id: c.id }).slice(0, 2);
                return (
                  <li key={c.id}>
                    <span>
                      {corridorLabel(c)} · volume {c.volumeNorm.toFixed(2)}
                    </span>
                    {records.length ? (
                      records.map((r) =>
                        r.source.url ? (
                          <a key={r.id} href={r.source.url} target="_blank" rel="noreferrer">
                            {r.source.publisher} · {r.source_locator} ↗
                          </a>
                        ) : (
                          <small key={r.id}>{r.source.publisher} · {r.source_locator}</small>
                        ),
                      )
                    ) : (
                      <small>No linked published route record.</small>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="erd-why">Corridor details are not in this snapshot.</p>
          )}
        </div>
      )}
      <small className="erd-basis">{ESTIMATE_BASIS}</small>
    </section>
  );
}
