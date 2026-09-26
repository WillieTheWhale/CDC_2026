// AI-assisted: written with ChatGPT (OpenAI). See docs/AI_USAGE.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

// A separate process exercises the same build-time environment switch Next uses.
// Fetch is intercepted so these tests never depend on the model server.
function runAdapter(script: string) {
  const result = spawnSync(
    process.execPath,
    ["--import", "tsx", "--input-type=module", "--eval", script],
    {
      cwd: new URL("..", import.meta.url),
      env: { ...process.env, NEXT_PUBLIC_API_URL: "http://127.0.0.1:9876/" },
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr);
}

test("live routes preserve query filters and return the server envelope", () => {
  runAdapter(`
    import assert from 'node:assert/strict';
    const {api, DEMO} = await import('./lib/api.ts');
    assert.equal(DEMO, false);
    globalThis.fetch = async (url, options) => {
      assert.equal(url, 'http://127.0.0.1:9876/api/routes?year=2023&mode=observed&min_confidence=70&drug=heroin');
      assert.ok(options.signal);
      return new Response(JSON.stringify({meta:{model_version:'server-test'},data:{year:2023,mode:'observed',drug:'heroin',edges:[]}}));
    };
    const response = await api.routes(2023, 'observed', 'heroin', 70);
    assert.equal(response.meta.model_version, 'server-test');
    assert.equal(response.data.year, 2023);
  `);
});

test("live failures remain errors and scenario requests preserve their body", () => {
  runAdapter(`
    import assert from 'node:assert/strict';
    const {api} = await import('./lib/api.ts');
    globalThis.fetch = async (url, options) => {
      assert.equal(url, 'http://127.0.0.1:9876/api/simulate');
      assert.equal(options.method, 'POST');
      assert.deepEqual(JSON.parse(options.body), {scenario:'Mexico legalizes cannabis',year:2025});
      return new Response(JSON.stringify({error:{message:'Model not ready'}}), {status:503});
    };
    await assert.rejects(api.simulate({scenario:'Mexico legalizes cannabis',year:2025}), /Model not ready/);
  `);
});
