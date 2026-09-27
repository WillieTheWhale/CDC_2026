// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// DOJ releases and attachment rosters enter a review queue only; never publish them to the People manifest.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { extractArticle, extractPdfRoster, plainText } from './doj-review-extract.mjs';

const api = 'https://www.justice.gov/api/v1/press_releases.json';
const defaultTerms = ['drug trafficking', 'fentanyl', 'methamphetamine', 'cocaine', 'narcotics', 'Sinaloa Cartel', '33 Alleged Members', '50 Individuals Charged With Drug Trafficking', 'Drug Trafficking Organization Faces Federal Charges', 'Nineteen Defendants from Western Pennsylvania'];
const args = process.argv.slice(2);
function flag(name, fallback) { const i = args.indexOf(name); return i < 0 ? fallback : args[i + 1]; }
function positiveInteger(name, fallback) { const value = Number(flag(name, fallback)); if (!Number.isSafeInteger(value) || value < 1) throw new Error(`${name} must be a positive integer`); return value; }
const output = flag('--output', null);
if (!output) throw new Error('Usage: node scripts/import-doj-people-review.mjs --output PATH --state /tmp/doj-crawl-state.json [--resume] [--max-documents 700] [--max-pages-per-term 2] [--max-attachments 30]');
const statePath = flag('--state', null);
if (!statePath) throw new Error('--state is required; keep the body checkpoint outside published People fixtures, for example /tmp/doj-crawl-state.json');
const terms = flag('--terms', defaultTerms.join('|')).split('|').map((x) => x.trim()).filter(Boolean);
const pageSize = 50;
const maxDocuments = positiveInteger('--max-documents', 700);
const maxPagesPerTerm = positiveInteger('--max-pages-per-term', 2);
const maxAttachments = positiveInteger('--max-attachments', 30);
const delayMs = 350; // DOJ says more than four requests per second may degrade service or be blocked.
const resume = args.includes('--resume');
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const checkpointPath = resolve(statePath);
const outputPath = resolve(output);
function withoutEmbeddedImages(article, state) {
  const body = String(article.body ?? '');
  let imagesRemoved = 0;
  const cleaned = body.replace(/<img\b[^>]*>/gi, () => { imagesRemoved++; return ''; });
  state.embeddedImagesRemoved = (state.embeddedImagesRemoved ?? 0) + imagesRemoved;
  state.embeddedMediaBytesRemoved = (state.embeddedMediaBytesRemoved ?? 0) + Buffer.byteLength(body) - Buffer.byteLength(cleaned);
  return { uuid: article.uuid, url: article.url, title: article.title, date: article.date, body: cleaned, attachment: article.attachment };
}
let lastRequestAt = 0;
async function request(url) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const wait = delayMs - (Date.now() - lastRequestAt);
    if (wait > 0) await sleep(wait);
    lastRequestAt = Date.now();
    const response = await fetch(url, { headers: { 'User-Agent': 'TRACE-public-research-review/1.0' } });
    if (response.ok) return response;
    if (response.status !== 429 && response.status < 500) throw new Error(`DOJ returned ${response.status}: ${url}`);
    if (attempt === 3) throw new Error(`DOJ returned ${response.status} after retries: ${url}`);
    const retryAfter = Number(response.headers.get('retry-after'));
    await sleep(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1000 : (attempt + 1) * 2000);
  }
}
async function saveState(state) {
  await mkdir(dirname(checkpointPath), { recursive: true });
  const temporary = `${checkpointPath}.tmp`;
  await writeFile(temporary, `${JSON.stringify(state)}\n`);
  await rename(temporary, checkpointPath);
}
let state;
if (resume) {
  state = JSON.parse(await readFile(checkpointPath, 'utf8'));
  if (state.version !== 2 || JSON.stringify(state.terms) !== JSON.stringify(terms)) throw new Error('Checkpoint version or terms do not match this crawl');
  state.embeddedImagesRemoved ??= 0;
  state.embeddedMediaBytesRemoved ??= 0;
  for (const [uuid, article] of Object.entries(state.documents)) state.documents[uuid] = withoutEmbeddedImages(article, state);
  await saveState(state);
} else {
  state = { version: 2, terms, nextPage: {}, queryCounts: {}, requests: 0, documents: {}, attachmentRows: {}, attachmentScans: 0, attachmentErrors: [], embeddedImagesRemoved: 0, embeddedMediaBytesRemoved: 0 };
  await saveState(state);
}
for (const term of terms) {
  for (let page = state.nextPage[term] ?? 0; page < maxPagesPerTerm && Object.keys(state.documents).length < maxDocuments; page++) {
    if (Number.isSafeInteger(state.queryCounts[term]) && page * pageSize >= state.queryCounts[term]) break;
    const url = new URL(api);
    url.searchParams.set('parameters[title]', term);
    url.searchParams.set('fields', 'title,date,url,body,uuid,attachment');
    url.searchParams.set('pagesize', String(pageSize));
    url.searchParams.set('page', String(page));
    url.searchParams.set('sort', 'date');
    url.searchParams.set('direction', 'DESC');
    const response = await request(url);
    const body = await response.json();
    state.requests++;
    const count = Number(body.metadata?.resultset?.count);
    if (!Number.isSafeInteger(count)) throw new Error(`Missing DOJ result count for ${term}`);
    state.queryCounts[term] = count;
    for (const article of body.results ?? []) {
      if (article.uuid && /^https:\/\/www\.justice\.gov\//.test(article.url ?? '') && !state.documents[article.uuid]) state.documents[article.uuid] = withoutEmbeddedImages(article, state);
    }
    state.nextPage[term] = page + 1;
    await saveState(state);
    if ((page + 1) * pageSize >= count) break;
  }
}
function publishedAt(article) {
  const seconds = Number(article.date);
  return Number.isFinite(seconds) && seconds > 0 ? new Date(seconds * 1000).toISOString().slice(0, 10) : null;
}
const documents = Object.values(state.documents).sort((a, b) => String(a.uuid).localeCompare(String(b.uuid)));
const candidates = [];
const seen = new Map();
let syndicatedDuplicatesCollapsed = 0;
function add(article, row, attachmentUrl = null) {
  const key = [row.kind, row.name.normalize('NFKC').toLocaleLowerCase('en-US'), row.sourceSpan, row.allegedOffenseSpan ?? '', plainText(article.title), publishedAt(article), attachmentUrl ?? ''].join('|');
  const duplicate = seen.get(key);
  if (duplicate) {
    if (duplicate.source.articleUrl !== article.url) {
      duplicate.alternateArticleUrls ??= [];
      if (!duplicate.alternateArticleUrls.includes(article.url)) duplicate.alternateArticleUrls.push(article.url);
      syndicatedDuplicatesCollapsed++;
    }
    return;
  }
  const candidate = {
    candidateId: `doj-${createHash('sha256').update(key).digest('hex').slice(0, 20)}`,
    name: row.name,
    kind: row.kind,
    tentativeEventType: row.tentativeEventType,
    ...(row.matchedVerb ? { matchedVerb: row.matchedVerb } : {}),
    sourceSpan: row.sourceSpan,
    ...(row.rosterContext ? { rosterContext: row.rosterContext } : {}),
    ...(row.allegedOffenseSpan ? { allegedOffenseSpan: row.allegedOffenseSpan } : {}),
    ...(row.page ? { attachmentPage: row.page } : {}),
    source: { url: attachmentUrl ?? article.url, articleUrl: article.url, articleUuid: article.uuid, title: plainText(article.title), publisher: 'U.S. Department of Justice', publishedAt: publishedAt(article) },
    eventDate: null,
    reviewState: 'needs_human_verification',
    ...(row.kind === 'pdf_roster' ? { reviewFlags: ['PDF text layout and full identity require manual confirmation'] } : row.kind === 'html_table_roster' && !row.allegedOffenseSpan ? { reviewFlags: ['Table lists a defendant in group case context; individual charge requires verification'] } : {}),
  };
  seen.set(key, candidate);
  candidates.push(candidate);
}
for (const article of documents) for (const row of extractArticle(article)) add(article, row);
const attachmentArticles = documents.filter((article) => Array.isArray(article.attachment) && article.attachment.length)
  .sort((a, b) => Number(/list of all defendants|list of defendants|list of all charged/iu.test(b.body ?? '')) - Number(/list of all defendants|list of defendants|list of all charged/iu.test(a.body ?? '')) || String(a.uuid).localeCompare(String(b.uuid)));
for (const article of attachmentArticles) {
  for (const attachment of article.attachment) {
    const id = String(attachment?.file?.id ?? '');
    if (!/^\d+$/.test(id)) continue;
    if (Object.hasOwn(state.attachmentRows, id)) {
      for (const row of state.attachmentRows[id]) add(article, row, `https://www.justice.gov/media/${id}/dl`);
      continue;
    }
    if (state.attachmentScans >= maxAttachments) continue;
    const attachmentUrl = `https://www.justice.gov/media/${id}/dl`;
    state.attachmentScans++;
    try {
      const response = await request(attachmentUrl);
      const size = Number(response.headers.get('content-length'));
      if (!response.headers.get('content-type')?.toLowerCase().includes('pdf') || size > 5_000_000) {
        state.attachmentRows[id] = [];
      } else {
        const buffer = Buffer.from(await response.arrayBuffer());
        if (buffer.length > 5_000_000) throw new Error('PDF exceeds 5 MB review cap');
        const raw = execFileSync('pdftotext', ['-raw', '-', '-'], { input: buffer, encoding: 'utf8', timeout: 15_000, maxBuffer: 6_000_000 });
        state.attachmentRows[id] = extractPdfRoster(raw);
      }
    } catch (error) {
      state.attachmentRows[id] = [];
      state.attachmentErrors.push({ attachmentUrl, reason: error instanceof Error ? error.message : String(error) });
    }
    for (const row of state.attachmentRows[id]) add(article, row, attachmentUrl);
    await saveState(state);
  }
}
const uniqueNames = new Set(candidates.map((row) => row.name.normalize('NFKC').toLocaleLowerCase('en-US')));
const kinds = Object.fromEntries(['sentence', 'html_roster', 'html_table_roster', 'pdf_roster'].map((kind) => [kind, candidates.filter((row) => row.kind === kind).length]));
const result = {
  _about: 'AI-assisted: generated with ChatGPT (OpenAI). See docs/AI_USAGE.md. Unreviewed DOJ candidates only; no person, allegation, location, role, edge, photo, or event is auto-published. Release dates are not event dates. Names and PDF layout require manual identity/status review.',
  api, queryTerms: terms, queryCounts: state.queryCounts, nextPage: state.nextPage,
  requests: state.requests, fetchedUniqueDocuments: documents.length, attachmentScans: state.attachmentScans, attachmentErrors: state.attachmentErrors,
  extractedMentions: candidates.length, syndicatedDuplicatesCollapsed, byKind: kinds, uniqueNameStrings: uniqueNames.size,
  candidates: candidates.sort((a, b) => a.source.articleUuid.localeCompare(b.source.articleUuid) || a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name) || a.candidateId.localeCompare(b.candidateId)),
};
await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`);
console.log(`DOJ review: ${state.requests} API requests, ${documents.length} unique releases, ${state.attachmentScans} attachment scans, ${candidates.length} review mentions (${JSON.stringify(kinds)}), ${uniqueNames.size} name strings.`);
