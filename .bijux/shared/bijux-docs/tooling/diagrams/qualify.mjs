#!/usr/bin/env node
/** Exercise the exact diagram bytes in three real browsers without production payloads. */
import { readFile, writeFile, mkdir, realpath } from "node:fs/promises";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import http from "node:http";
import path from "node:path";

const values = Object.fromEntries(process.argv.slice(2).reduce((pairs, item, index, args) => {
  if (index % 2 === 0) {
    if (!["--bundle", "--playwright", "--output"].includes(item) || !args[index + 1]) throw new Error("Expected explicit bundle, Playwright runtime and artifacts output");
    pairs.push([item.slice(2), args[index + 1]]);
  }
  return pairs;
}, []));
const cases = [
  ["flow", "flowchart TD\nA[Start] --> B[Read]"],
  ["sequence", "sequenceDiagram\nReader->>Site: Open guide\nSite-->>Reader: Content"],
  ["class", "classDiagram\nclass Reader\nclass Guide\nReader --> Guide"],
  ["state", "stateDiagram-v2\n[*] --> Reading\nReading --> [*]"],
  ["gantt", "gantt\ndateFormat YYYY-MM-DD\nsection Reading\nGuide :a, 2026-01-01, 2d"],
  ["pie", 'pie\n"Readers": 10\n"Authors": 2'],
  ["math", 'flowchart TD\nA["$$\\sqrt{x^2+y^2}$$"] --> B[Read]'],
  ["html-label", 'flowchart LR\nA["<img src=x onerror=window.__bijuxPayload=1>"] --> B[Read]'],
  ["executable-link", 'flowchart LR\nA[Read]\nclick A "javascript:window.__bijuxPayload=1"'],
  ["directive", '%%{init: {"securityLevel":"loose","dompurifyConfig":{"ADD_ATTR":["onerror"]}}}%%\nflowchart LR\nA["<img src=x onerror=window.__bijuxPayload=1>"]'],
];

async function bounded(promise) {
  let deadline;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      deadline = setTimeout(() => reject(new Error("Diagram case exceeded the 10-second qualification budget")), 10000);
    })]);
  } finally { clearTimeout(deadline); }
}

async function qualify() {
  if (!values.bundle || !values.playwright || !values.output) throw new Error("Three explicit paths required");
  const cwd = await realpath(process.cwd());
  const output = path.resolve(values.output);
  if (!output.startsWith(path.join(cwd, "artifacts") + path.sep)) throw new Error("Qualification report must be under artifacts/");
  const bundle = await readFile(values.bundle);
  const require = createRequire(path.join(path.resolve(values.playwright), "package.json"));
  const { chromium, firefox, webkit } = require("playwright");
  const server = http.createServer((req, response) => {
    if (req.url === "/renderer.js") {
      response.setHeader("Content-Type", "application/javascript");
      response.end(bundle);
    } else if (req.url === "/") {
      response.setHeader("Content-Type", "text/html");
      response.end('<!doctype html><title>Diagram fixture</title><div id="outside">Preserved</div><pre class="mermaid" id="automatic">flowchart TD\nAutomatic--&gt;Forbidden</pre><div id="rendered"></div><script>window.__bijuxPayload=0;window.mermaid_config={startOnLoad:true};</script><script src="/renderer.js"></script>');
    } else { response.statusCode = 404; response.end("Not found"); }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const report = { schema: 1, bundle_sha256: createHash("sha256").update(bundle).digest("hex"), startup: [], cases: [],
    scope: "Pinned dependency API/rendered SVG, actual three browsers, local corpus only; shell lifecycle and product diagram coverage remain separate." };
  try {
    for (const [engine, browserType] of Object.entries({ chromium, firefox, webkit })) {
      const browser = await browserType.launch();
      try {
        const page = await browser.newPage();
        page.setDefaultTimeout(10000);
        await page.goto(`http://127.0.0.1:${server.address().port}/`);
        await page.waitForFunction(() => window.mermaid && typeof window.mermaid.render === "function");
        await page.waitForTimeout(200);
        const startup = await page.evaluate(() => ({ initialize: typeof window.mermaid.initialize, render: typeof window.mermaid.render, automatic: window.mermaid.startOnLoad,
          unscanned: document.querySelector("#automatic").textContent === "flowchart TD\nAutomatic-->Forbidden" && !document.querySelector("#automatic svg") }));
        report.startup.push({ engine, version: browser.version(), ...startup });
        if (startup.automatic !== false || !startup.unscanned) throw new Error("Renderer allows automatic document scan");
        await page.evaluate(() => window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", maxTextSize: 50000, maxEdges: 500,
          secure: ["securityLevel", "startOnLoad", "maxTextSize", "maxEdges", "dompurifyConfig"] }));
        for (let index = 0; index < cases.length; index++) {
          const [name, text] = cases[index];
          const result = await bounded(page.evaluate(async ({ name, text, index }) => {
            const output = await window.mermaid.render(`bijux_dependency_${index}`, text);
            const parsed = new DOMParser().parseFromString(output.svg, "image/svg+xml");
            const svg = parsed.documentElement;
            if (svg.localName !== "svg" || parsed.querySelector("parsererror")) {
              await new Promise((resolve) => setTimeout(resolve, 80));
              const expected = ["html-label", "directive"].includes(name);
              return { passed: expected && window.__bijuxPayload === 0, expected_rejection: expected, reason: "invalid-svg", payload: window.__bijuxPayload };
            }
            document.querySelector("#rendered").replaceChildren(document.importNode(svg, true));
            await new Promise((resolve) => setTimeout(resolve, 80));
            const unsafe = [...svg.querySelectorAll("*")].some((node) => [...node.attributes].some((attr) => attr.name.toLowerCase().startsWith("on") || /^(?:javascript|vbscript):/i.test(attr.value.trim())));
            const math = name !== "math" || !!svg.querySelector("math, .katex, .katex-mathml");
            return { passed: window.__bijuxPayload === 0 && !unsafe && math && !svg.querySelector("script") && document.querySelector("#outside").textContent === "Preserved",
              svg_bytes: output.svg.length, math, outside: document.querySelector("#outside").textContent, payload: window.__bijuxPayload };
          }, { name, text, index }));
          report.cases.push({ engine, version: browser.version(), name, ...result });
        }
        await page.close();
      } finally { await browser.close(); }
    }
  } catch (error) { report.failure = error.message; }
  finally { await new Promise((resolve) => server.close(resolve)); }
  report.passed = !report.failure && report.cases.length === 30 && report.cases.every((item) => item.passed);
  await mkdir(path.dirname(output), { recursive: true });
  await writeFile(output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({ passed: report.passed, cases: report.cases.length, bundle_sha256: report.bundle_sha256, output: values.output }));
  if (!report.passed) process.exitCode = 1;
}

qualify().catch((error) => { console.error(`Diagram qualification failed: ${error.message}`); process.exitCode = 1; });
