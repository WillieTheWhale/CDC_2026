// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Bounded DOJ document-to-person review queue. Never publish these candidates automatically.
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const api = "https://www.justice.gov/api/v1/press_releases.json";
const terms = ["Sinaloa Cartel", "Jalisco New Generation", "Clan del Golfo", "Gulf Cartel", "Los Zetas", "Cártel de Jalisco Nueva Generación"];
const maxDocuments = 300;
const pageSize = 50;
const delayMs = 350; // DOJ documentation warns that >4 requests/second may be blocked.
const outputIndex = process.argv.indexOf("--output");
const output = outputIndex < 0 ? undefined : process.argv[outputIndex + 1];
if (!output) throw new Error("Usage: node scripts/import-doj-people-review.mjs --output data/people/candidates/doj-pilot.json");

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
function decodeHtml(input) {
  const named = { amp: "&", quot: '"', apos: "'", nbsp: " ", lt: "<", gt: ">", ndash: "–", mdash: "—", rsquo: "’", lsquo: "‘", ldquo: "“", rdquo: "”" };
  return input.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (whole, entity) => {
    if (entity.startsWith("#x")) return String.fromCodePoint(Number.parseInt(entity.slice(2), 16));
    if (entity.startsWith("#")) return String.fromCodePoint(Number.parseInt(entity.slice(1), 10));
    return named[entity.toLowerCase()] ?? whole;
  });
}
function plainText(html) {
  return decodeHtml(String(html ?? "")
    .replace(/<\/(?:p|li|h[1-6]|div)>/gi, "\n")
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<[^>]*>/g, " "))
    .replace(/[\t ]+/g, " ").replace(/ *\n+ */g, "\n").trim();
}
function sentences(text) {
  return text.split(/\n+/).flatMap((paragraph) => paragraph.split(/(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ“])/u)).map((s) => s.trim()).filter(Boolean);
}
const nameToken = String.raw`[A-ZÁÉÍÓÚÑ][\p{L}'’.-]+`;
const namePattern = String.raw`(${nameToken}(?:\s+(?:${nameToken}|de|del|la|De|Del|La)){1,3})`;
const actionPattern = String.raw`(?:,\s*(?:\d{2,3}|[^,.;]{1,70}),)?\s+(was sentenced|were sentenced|has been sentenced|was convicted|was found guilty|pleaded guilty|pled guilty|has pleaded guilty|was indicted|was charged|has been charged|was arrested|has been arrested)`;
const eventRegex = new RegExp(String.raw`\b${namePattern}${actionPattern}\b`, "gu");
const badNameWords = /\b(?:After|Before|When|El|Department|Justice|Attorney|Office|Cartel|District|Court|Judge|United|States|Mexican|Federal|Drug|Trafficking|Police|Authorities|Members|Leader|Defendant|Individual|Today|Yesterday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Angels|Strike|Force)\b/u;
const drugContext = /\b(?:drug|narcotic|cocaine|methamphetamine|meth|fentanyl|heroin|marijuana|cannabis|opioid)\w*\b/iu;
const eventType = (verb) => {
  const v = verb.toLowerCase();
  if (v.includes("sentenced")) return "sentencing_reported";
  if (v.includes("convicted") || v.includes("found guilty")) return "conviction_reported";
  if (v.includes("guilty")) return "guilty_plea_reported";
  if (v.includes("indicted") || v.includes("charged")) return "charge_reported";
  return "arrest_reported";
};

const documents = new Map();
const queryCounts = {};
let requests = 0;
for (const term of terms) {
  let page = 0;
  let count;
  do {
    if (requests) await sleep(delayMs);
    const params = new URLSearchParams({ pagesize: String(pageSize), page: String(page), fields: "title,date,url,body,uuid" });
    params.set("parameters[title]", term);
    const response = await fetch(`${api}?${params}`);
    if (!response.ok) throw new Error(`DOJ API returned ${response.status} for ${term}, page ${page}`);
    const body = await response.json();
    requests += 1;
    count = Number(body.metadata?.resultset?.count);
    if (!Number.isInteger(count)) throw new Error(`Missing DOJ result count for ${term}`);
    queryCounts[term] = count;
    for (const article of body.results ?? []) {
      if (article.uuid && article.url?.startsWith("https://")) documents.set(article.uuid, article);
    }
    page += 1;
  } while (page * pageSize < count && documents.size < maxDocuments);
  if (documents.size >= maxDocuments) break;
}

const extracted = [];
for (const article of documents.values()) {
  const publishedAt = Number.isFinite(Number(article.date)) ? new Date(Number(article.date) * 1000).toISOString().slice(0, 10) : null;
  for (const sourceSpan of sentences(plainText(article.body))) {
    // An article title can discover a document, but it cannot make every named person in it a drug-related candidate.
    if (!drugContext.test(sourceSpan)) continue;
    eventRegex.lastIndex = 0;
    for (const match of sourceSpan.matchAll(eventRegex)) {
      const name = match[1].trim();
      const verb = match[2].trim();
      const preceding = sourceSpan.slice(0, match.index).trimEnd();
      // Reject place names after "of/from/in" and nicknames inside quotation marks.
      if (badNameWords.test(name) || name.length > 75 || sourceSpan.length > 600 ||
          /(?:\bof|\bfrom|\bin)\s*$/iu.test(preceding) || /[“"‘']\s*$/u.test(preceding)) continue;
      extracted.push({
        candidateId: `doj-${article.uuid}-${extracted.length + 1}`,
        name,
        tentativeEventType: eventType(verb),
        matchedVerb: verb,
        sourceSpan,
        source: { url: article.url, articleUuid: article.uuid, title: plainText(article.title), publisher: "U.S. Department of Justice", publishedAt },
        eventDate: null,
        reviewState: "needs_human_verification",
      });
    }
  }
}
const result = {
  _about: "AI-assisted: generated with ChatGPT (OpenAI). See docs/AI_USAGE.md. This is an unreviewed DOJ document-to-person queue, not published People data. A matched legal verb is tentative; no organization, relationship, location, drug, image, or event date is inferred.",
  api,
  queryTerms: terms,
  queryCounts,
  requests,
  fetchedUniqueDocuments: documents.size,
  extractedMentions: extracted.length,
  uniqueNameStrings: new Set(extracted.map((item) => item.name.toLocaleLowerCase("en-US"))).size,
  candidates: extracted,
};
const destination = resolve(output);
await mkdir(dirname(destination), { recursive: true });
await writeFile(destination, `${JSON.stringify(result, null, 2)}\n`);
console.log(`DOJ pilot: ${requests} requests, ${documents.size} unique releases, ${extracted.length} tentative event mentions, ${result.uniqueNameStrings} name strings.`);
