// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import type { Country, Edge } from "./types";

type Coordinate = Pick<Country, "lat" | "lon">;

// The API's volume_norm is a seizure-anchored model estimate. It ranks
// corridors within a drug and year; it is not a measured share of world trade.
const strength = (edge: Edge) => edge.volume_norm * (0.5 + edge.confidence / 200);

export function visibleModelRoutes(
  edges: Edge[],
  countries: ReadonlyMap<string, Coordinate>,
  zoom: number,
): Edge[] {
  // Country representative coordinates must disappear before street scale.
  if (zoom >= 6) return [];
  const ranked = edges
    .filter((edge) => {
      const from = countries.get(edge.from);
      const to = countries.get(edge.to);
      return from?.lat != null && from.lon != null && to?.lat != null && to.lon != null;
    })
    .sort((a, b) => strength(b) - strength(a) || a.id.localeCompare(b.id));
  if (zoom >= 3.4) return ranked;

  // At a world view, reverse directions occupy the same screen arc. The
  // stronger one represents the pair until the viewer reaches country scale.
  const paired = new Set<string>();
  const candidates = ranked.filter((edge) => {
    const pair = [edge.from, edge.to].sort().join(":");
    const key = `${edge.drug}:${pair}`;
    if (paired.has(key)) return false;
    paired.add(key);
    return true;
  });
  const world = zoom < 1.7;
  const cellSize = world ? 40 : 25;
  const perCell = world ? 2 : 6;
  const limit = world ? 22 : 70;
  const used = new Map<string, number>();
  const selected: Edge[] = [];
  for (const edge of candidates) {
    const from = countries.get(edge.from)!;
    const cell = `${Math.floor((from.lon! + 180) / cellSize)}:${Math.floor((from.lat! + 90) / cellSize)}`;
    if ((used.get(cell) ?? 0) >= perCell) continue;
    selected.push(edge);
    used.set(cell, (used.get(cell) ?? 0) + 1);
    if (selected.length === limit) break;
  }
  return selected;
}
