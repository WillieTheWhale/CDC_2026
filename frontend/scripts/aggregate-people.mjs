// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import { readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const peopleDir = join(here, "../data/people");
const files = (await readdir(peopleDir)).filter((name) => name.endsWith(".json") && name !== "manifest.json").sort();
const combined = { organizations: [], people: [], connections: [] };
const seen = { organizations: new Set(), people: new Set(), connections: new Set() };
const isCitable = (source) => source && /^https?:\/\//i.test(source.url ?? "") &&
  source.title?.trim() && source.publisher?.trim() && source.language?.trim() && source.claim?.trim();
const sourced = (row) => Array.isArray(row.sources) && row.sources.some(isCitable);

for (const file of files) {
  const network = JSON.parse(await readFile(join(peopleDir, file), "utf8"));
  for (const key of ["organizations", "people", "connections"]) {
    for (const row of network[key] ?? []) {
      if (typeof row.id !== "string" || !row.id.trim() || seen[key].has(row.id)) throw new Error(`Duplicate or missing ${key} id in ${file}: ${row.id ?? "(missing)"}`);
      seen[key].add(row.id);
      if (key === "organizations") {
        if (typeof row.name !== "string" || !Array.isArray(row.regions) || !row.regions.every((value) => typeof value === "string") || !sourced(row)) {
          throw new Error(`Organization ${row.id} in ${file} has malformed regions or no citable source.`);
        }
      } else if (key === "people") {
        if (typeof row.name !== "string" || !["convicted", "charged", "sanctioned", "reported"].includes(row.status) ||
            ![1, 2, 3].includes(row.prominence) || !Array.isArray(row.organizationIds) ||
            !row.organizationIds.every((value) => typeof value === "string") || !Array.isArray(row.regions) ||
            !row.regions.every((region) => region && /^[A-Z]{3}$/.test(region.iso3) && typeof region.label === "string") ||
            !Array.isArray(row.drugs) || !row.drugs.every((value) => typeof value === "string") || !sourced(row)) {
          throw new Error(`Person ${row.id} in ${file} is malformed or has no citable source.`);
        }
      } else if (key === "connections" &&
          (typeof row.fromId !== "string" || typeof row.toId !== "string" ||
           typeof row.label !== "string" || typeof row.type !== "string" || !sourced(row))) {
        throw new Error(`Connection ${row.id} in ${file} is malformed or has no citable source.`);
      }
      combined[key].push(row);
    }
  }
}

const personIds = new Set(combined.people.map((person) => person.id));
for (const connection of combined.connections) {
  if (!personIds.has(connection.fromId) || !personIds.has(connection.toId)) {
    throw new Error(`Connection ${connection.id} refers to a missing person.`);
  }
}

await writeFile(join(peopleDir, "manifest.json"), `${JSON.stringify(combined, null, 2)}\n`);
console.log(`Aggregated ${combined.people.length} sourced people from ${files.length} fixture files.`);
