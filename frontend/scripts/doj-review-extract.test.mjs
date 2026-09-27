// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { extractArticle, extractPdfRoster } from './doj-review-extract.mjs';

test('semicolon defendant roster yields separate unpublished names with exact entry spans', () => {
  const article = { title: 'Six individuals charged in cocaine trafficking case', body: '<p>The defendants indicted are: Ana María Rivera, a.k.a. “Ana”; Brian James Carter; Carmen Luz Díaz; Daniel José Gómez; Elena Pérez Silva; and Felipe Ortiz Morales.</p>' };
  const rows = extractArticle(article).filter((row) => row.kind === 'html_roster');
  assert.equal(rows.length, 6);
  assert.equal(rows[0].name, 'Ana María Rivera');
  assert.equal(rows[0].sourceSpan, 'Ana María Rivera, a.k.a. “Ana”');
  assert.equal(rows[5].name, 'Felipe Ortiz Morales');
  assert.ok(rows.every((row) => row.eventDate === null && row.tentativeEventType === 'charge_roster_review'));
});

test('PDF roster parser keeps names and charges, not residence or age, in review spans', () => {
  const raw = `Name Place ofResidence Age Charges\nJOSE ANTONIO\nMORALES NIEVES\naka“Flaco”\nLuquillo, PR 45\n■ Conspiracy to Distribute\nControlled Substances\nNANCY RIOS-VALENTIN Philadelphia, PA 33\n■ Conspiracy to Distribute\nControlled Substances\n`;
  const rows = extractPdfRoster(raw);
  assert.deepEqual(rows.map((row) => row.name), ['JOSE ANTONIO MORALES NIEVES', 'NANCY RIOS-VALENTIN']);
  assert.ok(rows.every((row) => !/Luquillo|Philadelphia|\b45\b|\b33\b/.test(row.sourceSpan + row.allegedOffenseSpan)));
  assert.deepEqual(extractPdfRoster('Unrelated attachment'), []);
});

test('HTML charge tables yield names and person-specific allegation spans without ages', () => {
  const names = ['Eric L. Robinson, 55', 'Jonhy Chacon-Hernandez, 28', 'Genaro Tapia, 25', 'Monte D. Scruggs, 44', 'Richard N. Irwin, II, 39'];
  const body = `<p>Five defendants charged in a cocaine trafficking case.</p><table><tr><td>Defendant</td><td>Charge(s)</td></tr>${names.map((name) => `<tr><td>${name}</td><td>Conspiracy to distribute controlled substances</td></tr>`).join('')}</table>`;
  const rows = extractArticle({ title: 'Drug trafficking organization faces charges', body });
  assert.equal(rows.filter((row) => row.kind === 'html_table_roster').length, 5);
  assert.equal(rows[4].name, 'Richard N. Irwin II');
  assert.equal(rows[4].sourceSpan, 'Richard N. Irwin, II');
  assert.equal(rows[4].allegedOffenseSpan, 'Conspiracy to distribute controlled substances');
});
