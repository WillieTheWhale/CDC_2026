// AI-assisted: written with ChatGPT (OpenAI) and Claude Code (Anthropic). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeDataset } from "./people-api";
import { personDisplayStatus } from "../components/people-legal";
import { parsePeopleQuery, queryPeople } from "./people-query";

const source = { url: "https://court.example/judgment", title: "Judgment", publisher: "Court", language: "en", claim: "Final order" };
const base = { id: "p", name: "Example Person", status: "convicted", statusAsOf: "2013-02-13", prominence: 3, organizationIds: [], regions: [], drugs: [], sources: [source] };

test("final full acquittal replaces an obsolete conviction label while the dated history survives", () => {
  const data = normalizeDataset({ organizations: [], connections: [], people: [{ ...base,
    legalHistory: [
      { status: "convicted", date: "2013-02-13", qualifier: "Affirmed on appeal", source },
      { status: "acquitted", date: "2016-07-13", qualifier: "Acquitted on both counts", source },
    ],
  }] });
  assert.deepEqual(data.people[0].legalHistory?.map((claim) => claim.status), ["acquitted", "convicted"]);
  assert.equal(personDisplayStatus(data.people[0]).label, "Acquitted");
});

test("partial reversal does not conceal a surviving conviction", () => {
  const data = normalizeDataset({ organizations: [], connections: [], people: [{ ...base,
    legalHistory: [{ status: "overturned", date: "2016-07-13", qualifier: "One count only", partial: true, source }],
  }] });
  assert.equal(personDisplayStatus(data.people[0]).label, "Historical conviction cited");
});

test("optional invalid entries drop without removing a legacy person", () => {
  const data = normalizeDataset({ organizations: [], connections: [], people: [{ ...base,
    lifeStatus: { value: "deceased", deathDate: "2010-02-30", source },
    legalHistory: [{ status: "charged", date: "2024-14", qualifier: "Invalid month", source }],
  }] });
  assert.equal(data.people.length, 1);
  assert.equal(data.people[0].lifeStatus, undefined);
  assert.deepEqual(data.people[0].legalHistory, []);
});

test("null optional fields are treated as absent, as the backend does, and stripped", () => {
  const data = normalizeDataset({ organizations: [], connections: [], people: [{ ...base,
    lifeStatus: { value: "unknown", deathDate: null, asOf: null, source },
    legalHistory: [{ status: "charged", date: "2011", qualifier: "Indicted", offense: null, jurisdiction: null, partial: null, source }],
  }] });
  assert.deepEqual(data.people[0].lifeStatus, { value: "unknown", source });
  assert.deepEqual(data.people[0].legalHistory, [{ status: "charged", date: "2011", qualifier: "Indicted", source }]);
});

test("legal history sorts newest first across partial dates and keeps offense and partial flags", () => {
  const data = normalizeDataset({ organizations: [], connections: [], people: [{ ...base,
    legalHistory: [
      { status: "charged", date: "2010", qualifier: "Indicted", source },
      { status: "overturned", date: "2016-07-13", qualifier: "Count two quashed", offense: "supply", partial: true, source },
      { status: "convicted", date: "2013-02", qualifier: "Trial verdict", source },
      { status: "not-a-status", date: "2020-01-01", qualifier: "Unknown outcome", source },
      { status: "sentenced", date: "2014-01-01", qualifier: "", source },
    ],
  }] });
  const history = data.people[0].legalHistory ?? [];
  assert.deepEqual(history.map((claim) => claim.date), ["2016-07-13", "2013-02", "2010"]);
  assert.equal(history[0].offense, "supply");
  assert.equal(history[0].partial, true);
});

test("life status never changes legal status, and a charge is never shown as a conviction", () => {
  const data = normalizeDataset({ organizations: [], connections: [], people: [{ ...base, status: "charged", statusAsOf: "2019-05-01",
    lifeStatus: { value: "deceased", deathDate: "2021-03", source },
    legalHistory: [{ status: "charged", date: "2019-05-01", qualifier: "Indictment unsealed", source }],
  }] });
  const person = data.people[0];
  assert.equal(person.status, "charged");
  assert.equal(person.statusAsOf, "2019-05-01");
  assert.equal(person.lifeStatus?.value, "deceased");
  assert.equal(personDisplayStatus(person).label, "Historical charge cited");
  assert.doesNotMatch(personDisplayStatus(person).label, /convict/i);
});

test("a death date is rejected on a life status that is not deceased", () => {
  const data = normalizeDataset({ organizations: [], connections: [], people: [{ ...base,
    lifeStatus: { value: "unknown", deathDate: "2020-01-01", source },
  }] });
  assert.equal(data.people[0].lifeStatus, undefined);
  assert.equal(data.people[0].status, "convicted");
});

test("the fixture People route passes validated life and legal status through unchanged", () => {
  const dataset = normalizeDataset({ organizations: [], connections: [], people: [{ ...base, id: "unlocated-a",
    lifeStatus: { value: "deceased", source },
    legalHistory: [{ status: "convicted", date: "2013-02-13", qualifier: "Trial verdict", source }, { status: "acquitted", date: "2016-07-13", qualifier: "Appeal allowed", source }],
  }] });
  const page = queryPeople(dataset, [], parsePeopleQuery(new URLSearchParams("unlocated=1&limit=5")));
  assert.equal(page.meta.total, 1);
  assert.equal(page.data.people[0].lifeStatus?.value, "deceased");
  assert.deepEqual(page.data.people[0].legalHistory?.map((claim) => claim.status), ["acquitted", "convicted"]);
});
