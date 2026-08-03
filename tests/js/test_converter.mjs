// Golden parity tests: the JS port must reproduce the Python reference.
// Fixtures come from gen_fixtures.py (Python CLI --json output).
//
//     node --test tests/js/
//
// URLs are compared parameter-by-parameter; coordinates numerically with a
// 1.5e-6 tolerance (Python %.6f and JS toFixed(6) may differ in the last
// digit on rare ties — ~11 cm, irrelevant on the road).

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { parseText, parseBytes, parseLink, convert } from "../../docs/converter.js";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..", "..");
const cases = JSON.parse(readFileSync(join(here, "fixtures", "golden.json"), "utf-8"));

const COORD_PARAMS = new Set(["source", "waypoint", "destination"]);

function assertUrlsMatch(actual, expected) {
  const [aBase, aQuery] = actual.split("?");
  const [eBase, eQuery] = expected.split("?");
  assert.equal(aBase, eBase);
  const aParams = aQuery.split("&");
  const eParams = eQuery.split("&");
  assert.equal(aParams.length, eParams.length, `param count: ${actual} vs ${expected}`);
  for (let i = 0; i < eParams.length; i++) {
    const [aKey, aVal] = aParams[i].split("=");
    const [eKey, eVal] = eParams[i].split("=");
    assert.equal(aKey, eKey, `param ${i} name`);
    if (COORD_PARAMS.has(eKey)) {
      const [aLat, aLon] = aVal.split(",").map(Number);
      const [eLat, eLon] = eVal.split(",").map(Number);
      assert.ok(Math.abs(aLat - eLat) <= 1.5e-6, `${eKey}[${i}] lat ${aLat} vs ${eLat}`);
      assert.ok(Math.abs(aLon - eLon) <= 1.5e-6, `${eKey}[${i}] lon ${aLon} vs ${eLon}`);
    } else {
      assert.equal(aVal, eVal, `param ${eKey}`);
    }
  }
}

async function loadRoute(input) {
  switch (input.kind) {
    case "repo-file": {
      const text = readFileSync(join(ROOT, input.path), "utf-8");
      return parseText(text, input.path.split("/").pop());
    }
    case "text":
      return parseText(input.text, input.fileName);
    case "bytes-b64": {
      const buf = Buffer.from(input.b64, "base64");
      return parseBytes(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), input.fileName);
    }
    case "link":
      return parseLink(input.url);
    default:
      throw new Error(`unknown input kind ${input.kind}`);
  }
}

for (const c of cases) {
  test(c.name, async () => {
    const route = await loadRoute(c.input);
    const result = convert(route, c.options);

    assert.equal(result.total, c.expected.checkpoints_total, "checkpoints_total");
    assert.equal(result.used.length, c.expected.checkpoints_used, "checkpoints_used");
    assertUrlsMatch(result.url, c.expected.url);

    const expNames = c.expected.stops.map((s) => s.name);
    const gotNames = result.used.map((s) => s.name);
    assert.deepEqual(gotNames, expNames, "stop names");
  });
}

test("short google links are rejected with a hint", () => {
  assert.throws(
    () => parseLink("https://maps.app.goo.gl/AbCdEf123"),
    /paste the full/
  );
});

test("unknown text is rejected", () => {
  assert.throws(() => parseText("hello world", "notes.txt"), /Unrecognized route format/);
});
