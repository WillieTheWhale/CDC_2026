// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
export type PeopleViewMode = "map" | "graph" | "unlocated";

export function peopleRequestViewport({ mode, searching, selectedCountry, zoom, bounds }: {
  mode: PeopleViewMode;
  searching: boolean;
  selectedCountry: string | null;
  zoom: 1 | 2 | 3;
  bounds?: [number, number, number, number];
}) {
  const browseAllTiers = mode !== "map" || searching || selectedCountry !== null;
  return {
    zoom: browseAllTiers ? 3 as const : zoom,
    bounds: browseAllTiers ? undefined : bounds,
  };
}
