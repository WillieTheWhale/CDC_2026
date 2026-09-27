// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Produces review candidates only. Never import this output into the published People manifest.
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const sourceUrl = "https://www.treasury.gov/ofac/downloads/sdn.csv";
const allowedTags = new Set(["SDNT", "SDNTK", "ILLICIT-DRUGS-EO14059"]);

function argument(flag) {
  const index = process.argv.indexOf(flag);
  return index < 0 ? undefined : process.argv[index + 1];
}

// OFAC uses quoted CSV fields, commas inside names and remarks, and CRLF records.
function parseCsv(input) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < input.length; i += 1) {
    const char = input[i];
    if (char === '"') {
      if (quoted && input[i + 1] === '"') {
        field += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      row.push(field.trim());
      field = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && input[i + 1] === "\n") i += 1;
      row.push(field.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (quoted) throw new Error("Unclosed quoted CSV field");
  if (field || row.length) {
    row.push(field.trim());
    if (row.some(Boolean)) rows.push(row);
  }
  return rows;
}

const input = argument("--input");
const output = argument("--output");
const snapshotDate = argument("--snapshot-date");
if (!input || !output || !/^\d{4}-\d{2}-\d{2}$/.test(snapshotDate ?? "")) {
  throw new Error("Usage: node scripts/import-ofac-people.mjs --input sdn.csv --snapshot-date YYYY-MM-DD --output data/people/candidates/ofac.json");
}
const rows = parseCsv((await readFile(input, "utf8")).replace(/^\uFEFF/, "").replace(/\u001A\s*$/, ""));
const candidates = [];
const seen = new Set();
for (const row of rows) {
  // OFAC's SDN.CSV has exactly 12 columns; reject a changed format rather than silently shifting fields.
  if (row.length !== 12) throw new Error(`Unexpected SDN.CSV row width: ${row.length}`);
  const [entryNumber, name, type, programs] = row;
  if (!/^\d+$/.test(entryNumber) || !name || seen.has(entryNumber)) throw new Error(`Invalid or duplicate entry number: ${entryNumber}`);
  seen.add(entryNumber);
  if (type.trim().toLowerCase() !== "individual") continue;
  const programTags = programs.split(";").map((tag) => tag.trim()).filter((tag) => allowedTags.has(tag));
  if (!programTags.length) continue;
  candidates.push({
    candidateId: `ofac-sdn-${entryNumber}`,
    ofacEntryNumber: entryNumber,
    name,
    programTags,
    source: {
      url: sourceUrl,
      title: "Specially Designated Nationals and Blocked Persons List (SDN.CSV)",
      publisher: "U.S. Department of the Treasury, Office of Foreign Assets Control",
      snapshotDate,
      claim: `OFAC's ${snapshotDate} SDN.CSV snapshot lists this individual under ${programTags.join(", ")}. This program listing alone does not establish a drug-trafficking role, group membership, conviction, or relationship.`,
    },
    reviewState: "needs_independent_profile_evidence",
  });
}
candidates.sort((a, b) => Number(a.ofacEntryNumber) - Number(b.ofacEntryNumber));
const document = {
  _about: "AI-assisted: generated with ChatGPT (OpenAI). See docs/AI_USAGE.md. Review queue only; excluded from the published People manifest. No relationships, geographic associations, images, role labels, or drug specifics are inferred from OFAC program tags.",
  sourceUrl,
  snapshotDate,
  filters: { type: "individual", programTags: [...allowedTags] },
  totalSdnRows: rows.length,
  candidateCount: candidates.length,
  candidates,
};
const destination = resolve(output);
await mkdir(dirname(destination), { recursive: true });
await writeFile(destination, `${JSON.stringify(document, null, 2)}\n`);
console.log(`Wrote ${candidates.length} OFAC narcotics-program individual review candidates from ${rows.length} SDN rows to ${destination}`);
