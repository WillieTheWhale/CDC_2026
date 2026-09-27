// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeDataset } from "./people-api";
import { personDisplayStatus } from "../components/people-legal";

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
