// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
// Count schema-level evidence coverage; this does not judge whether cited claims are true.
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const defaultDir = fileURLToPath(new URL('../data/people/', import.meta.url));
const args = process.argv.slice(2);
const valueOf = (flag, fallback) => {
  const index = args.indexOf(flag);
  return index < 0 ? fallback : args[index + 1];
};
const fixturesDir = valueOf('--fixtures-dir', defaultDir);
const outputPath = valueOf('--output', null);

const totals = { people: 0, associations: 0, evidenced: 0, missing: 0, invalid: 0 };
const byFixture = {};
const byCountry = {};
const missingExamples = [];

for (const name of (await readdir(fixturesDir)).filter((file) => file.endsWith('.json') && file !== 'manifest.json').sort()) {
  const fixture = JSON.parse(await readFile(path.join(fixturesDir, name), 'utf8'));
  const stats = { people: fixture.people?.length ?? 0, associations: 0, evidenced: 0, missing: 0, invalid: 0 };
  totals.people += stats.people;
  for (const person of fixture.people ?? []) {
    const sourceUrls = new Set((person.sources ?? []).filter((source) =>
      typeof source.url === 'string' && /^https?:\/\//.test(source.url) &&
      typeof source.title === 'string' && source.title.trim() &&
      typeof source.publisher === 'string' && source.publisher.trim() &&
      typeof source.language === 'string' && source.language.trim() &&
      typeof source.claim === 'string' && source.claim.trim(),
    ).map((source) => source.url));
    for (const region of person.regions ?? []) {
      stats.associations++;
      const country = byCountry[region.iso3] ??= { associations: 0, evidenced: 0, missing: 0, invalid: 0 };
      country.associations++;
      const evidence = region.evidence;
      const status = evidence == null ? 'missing' :
        typeof evidence.claim === 'string' && evidence.claim.trim() &&
        typeof evidence.sourceUrl === 'string' && sourceUrls.has(evidence.sourceUrl) &&
        (evidence.period == null || typeof evidence.period === 'string' && evidence.period.trim())
          ? 'evidenced' : 'invalid';
      stats[status]++;
      country[status]++;
      if (status !== 'evidenced' && missingExamples.length < 30) {
        missingExamples.push({ fixture: name, personId: person.id, iso3: region.iso3, status });
      }
    }
  }
  byFixture[name] = stats;
  for (const key of Object.keys(totals)) if (key !== 'people') totals[key] += stats[key];
}

const report = {
  _about: 'AI-assisted: generated with ChatGPT (OpenAI). See docs/AI_USAGE.md. Counts region-evidence metadata only; it does not prove the cited country claim.',
  totals, byFixture, byCountry, missingExamples,
};
const output = JSON.stringify(report, null, 2) + '\n';
if (outputPath) await writeFile(outputPath, output);
else process.stdout.write(output);
