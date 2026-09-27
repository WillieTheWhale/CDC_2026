// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
// One shared, cached load of route evidence for the map and the panels.
"use client";
import { useEffect, useState } from "react";
import { DEMO, routeEvidence } from "./api";
import {
  emptyRouteEvidence,
  fixtureRouteEvidence,
  indexRouteEvidence,
  type RouteEvidenceIndex,
} from "./route-evidence";

export interface RouteEvidenceState {
  index: RouteEvidenceIndex;
  status: "loading" | "ready" | "error";
}
let cached: RouteEvidenceState | null = DEMO
  ? { index: indexRouteEvidence(fixtureRouteEvidence), status: "ready" }
  : null;
let pending: Promise<RouteEvidenceState> | null = null;
function load(): Promise<RouteEvidenceState> {
  if (cached) return Promise.resolve(cached);
  pending ??= routeEvidence()
    .then((records) => (cached = { index: indexRouteEvidence(records), status: "ready" as const }))
    // Connected but unreachable: show no evidence rather than the fixture, and
    // let a later mount retry.
    .catch(() => {
      pending = null;
      return { index: emptyRouteEvidence, status: "error" as const };
    });
  return pending;
}

export function useRouteEvidence(): RouteEvidenceState {
  const [state, setState] = useState<RouteEvidenceState>(
    () => cached ?? { index: emptyRouteEvidence, status: "loading" },
  );
  useEffect(() => {
    let active = true;
    void load().then((next) => active && setState((prev) => (prev.index === next.index && prev.status === next.status ? prev : next)));
    return () => {
      active = false;
    };
  }, []);
  return state;
}
