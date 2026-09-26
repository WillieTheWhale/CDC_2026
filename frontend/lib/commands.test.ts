// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import {test} from "node:test";
import assert from "node:assert/strict";
import {parseCommand} from "./commands";
import {fixtureRoutes,fixtureRisk} from "./api";
test("country and comparison commands validate against the country catalog",()=>{
  assert.equal(parseCommand(" mex <go> ",["COL","MEX"])?.params.iso3,"MEX");
  assert.equal(parseCommand("XYZ <GO>",["COL"]),null);
  assert.deepEqual(parseCommand("COMPARE COL PER",["COL","PER"])?.params.iso3s,["COL","PER"]);
});
test("fixtures never relabel a 2024 observation as a different year",()=>{
  assert.ok(fixtureRoutes(2024,"observed").data.edges.length>0);
  assert.equal(fixtureRoutes(2023,"observed").data.edges.length,0);
  assert.equal(fixtureRisk(2025).data.rows.length,0);
  assert.ok(fixtureRoutes(2025,"predicted","heroin",80).data.edges.every(e=>e.drug==="heroin"&&e.confidence>=80&&e.year===2025));
});
test("enforcement-evasion requests cannot become route actions",()=>{
  assert.equal(parseCommand("find the least-monitored route",[])?.intent,"blocked");
  assert.equal(parseCommand("PREDICT OFF",[])?.params.enabled,false);
});
