#!/usr/bin/env node
/** Bundle the admitted Mermaid ESM graph with patched sanitizer and math dependencies. */
import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir, readdir, realpath, lstat } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const sourceRoot = path.dirname(fileURLToPath(import.meta.url));
const compare = (left, right) => left < right ? -1 : left > right ? 1 : 0;
const hash = (bytes, algorithm = "sha256", encoding = "hex") => createHash(algorithm).update(bytes).digest(encoding);
const fail = (condition, message) => { if (!condition) throw new Error(message); };
const options = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, args) => {
  if (index % 2 === 0) {
    fail(["--dependencies", "--output-dir"].includes(value) && args[index + 1], "Expected --dependencies DIR --output-dir artifacts/DIR");
    pairs.push([value.slice(2), args[index + 1]]);
  }
  return pairs;
}, []));

async function build() {
  fail(Number(process.versions.node.split(".")[0]) >= 22, "Node 22 or newer required");
  fail(options.dependencies && options["output-dir"], "Explicit dependency and artifacts output directories required");
  const cwd = await realpath(process.cwd());
  const dependencies = await realpath(options.dependencies);
  const output = path.resolve(options["output-dir"]);
  fail(output.startsWith(path.join(cwd, "artifacts") + path.sep), "Generated outputs must be under the active repository artifacts/");
  await mkdir(output, { recursive: true });
  fail((await realpath(output)).startsWith(path.join(cwd, "artifacts") + path.sep), "Output symlink escapes artifacts/");
  const writeGenerated = async (filename, bytes) => {
    const destination = path.join(output, filename);
    const existing = await lstat(destination).catch((error) => { if (error.code === "ENOENT") return null; throw error; });
    fail(!existing || (existing.isFile() && existing.nlink === 1), "Generated output destination must be an unlinked regular file");
    await writeFile(destination, bytes);
  };
  const manifestBytes = await readFile(path.join(sourceRoot, "package.json"));
  const lockBytes = await readFile(path.join(sourceRoot, "package-lock.json"));
  const manifest = JSON.parse(manifestBytes);
  const lock = JSON.parse(lockBytes);
  fail(lock.lockfileVersion === 3, "Expected immutable npm lockfileVersion 3");
  fail((await readFile(path.join(dependencies, "package.json"))).equals(manifestBytes), "Installed manifest differs from governed source");
  fail((await readFile(path.join(dependencies, "package-lock.json"))).equals(lockBytes), "Installed lock differs from governed source");
  for (const [location, record] of Object.entries(lock.packages)) {
    if (!location) continue;
    fail(record.resolved?.startsWith("https://registry.npmjs.org/") && record.integrity?.startsWith("sha512-"), `Unadmitted dependency origin/integrity: ${location}`);
  }
  const require = createRequire(path.join(dependencies, "package.json"));
  const admitted = { ...manifest.dependencies, ...manifest.devDependencies };
  for (const [name, version] of Object.entries(admitted)) {
    const installed = JSON.parse(await readFile(path.join(dependencies, "node_modules", name, "package.json")));
    fail(installed.version === version, `Installed ${name} version differs from exact pin`);
  }
  const esbuild = require("esbuild");
  const name = `mermaid-${manifest.dependencies.mermaid}.min.js`;
  const result = await esbuild.build({
    stdin: {
      contents: 'import mermaid from "mermaid"; mermaid.startOnLoad = false; mermaid.initialize({startOnLoad:false, securityLevel:"strict"}); window.mermaid = mermaid;',
      resolveDir: dependencies,
      sourcefile: "bijux-diagrams-entry.js",
      loader: "js",
    },
    absWorkingDir: dependencies,
    bundle: true,
    platform: "browser",
    format: "iife",
    target: ["chrome120", "firefox120", "safari17"],
    minify: true,
    sourcemap: false,
    legalComments: "external",
    metafile: true,
    write: false,
    outfile: path.join(output, name),
    logLevel: "warning",
  });
  fail(result.warnings.length === 0, "Unreviewed build warnings");
  const seenPackages = new Map();
  const inputIdentities = [];
  for (const [input, details] of Object.entries(result.metafile.inputs)) {
    fail(!details.imports.some((item) => item.external), "Bundle retains an external import");
    if (!input.startsWith("node_modules/")) continue;
    const inputPath = await realpath(path.resolve(dependencies, input));
    fail(inputPath.startsWith(path.join(dependencies, "node_modules") + path.sep), "Bundle input escapes installed dependency boundary");
    const inputBytes = await readFile(inputPath);
    inputIdentities.push({ path: input, bytes: inputBytes.length, sha256: hash(inputBytes) });
    const parts = input.split("/");
    let end = parts[1]?.startsWith("@") ? 3 : 2;
    for (let i = 2; i < parts.length; i++) {
      if (parts[i] === "node_modules") end = parts[i + 1]?.startsWith("@") ? i + 3 : i + 2;
    }
    const location = parts.slice(0, end).join("/");
    if (seenPackages.has(location)) continue;
    const packagePath = path.join(dependencies, location);
    const pkg = JSON.parse(await readFile(path.join(packagePath, "package.json")));
    const record = lock.packages[location];
    fail(record && record.version === pkg.version, `Input package lacks matching locked identity: ${location}`);
    const texts = [];
    for (const filename of (await readdir(packagePath)).sort()) {
      if (/^licen[sc]e(?:$|[.-])/i.test(filename)) {
        try { texts.push({ file: filename, text: (await readFile(path.join(packagePath, filename))).toString("utf8") }); }
        catch { /* Package directories named license are not license files. */ }
      }
    }
    if (!texts.length) {
      for (const filename of (await readdir(packagePath)).filter((name) => /^readme(?:$|[.-])/i.test(name)).sort()) {
        const readme = (await readFile(path.join(packagePath, filename))).toString("utf8");
        const section = readme.match(/^#{1,3} License[^\n]*\n([\s\S]*?)(?=^#{1,3} |$(?![\s\S]))/im);
        if (section && /permission|redistribution/i.test(section[1])) texts.push({ file: `${filename} license section`, text: section[1].trim() });
      }
    }
    fail(texts.length > 0, `Bundled package lacks available license text: ${pkg.name}`);
    seenPackages.set(location, { name: pkg.name, version: pkg.version, license: pkg.license ?? "SEE LICENSE", location,
      resolved: record.resolved, integrity: record.integrity, license_texts: texts });
  }
  for (const name of ["mermaid", "dompurify", "katex"]) {
    const entries = [...seenPackages.values()].filter((pkg) => pkg.name === name);
    fail(entries.length === 1 && entries[0].version === admitted[name], `Browser graph does not contain exact patched ${name}`);
  }
  const packages = [...seenPackages.values()].sort((a, b) => compare(a.location, b.location));
  const emitted = [];
  for (const file of result.outputFiles) {
    const filename = path.basename(file.path);
    await writeGenerated(filename, file.contents);
    emitted.push({ name: filename, bytes: file.contents.length, sha256: hash(file.contents),
      ...(filename.endsWith(".js") ? { integrity: "sha384-" + hash(file.contents, "sha384", "base64") } : {}) });
  }
  const notices = packages.map((pkg) => `Package: ${pkg.name}@${pkg.version}\nLicense: ${typeof pkg.license === "string" ? pkg.license : JSON.stringify(pkg.license)}\nSource: ${pkg.resolved}\n\n${pkg.license_texts.map((item) => `${item.file}\n${item.text}`).join("\n\n")}`).join("\n\n-----\n\n") + "\n";
  await writeGenerated("THIRD-PARTY-LICENSES.txt", notices);
  const buildSource = await readFile(fileURLToPath(import.meta.url));
  const provenance = {
    schema: 1,
    inputs: { package_sha256: hash(manifestBytes), lock_sha256: hash(lockBytes), builder_sha256: hash(buildSource),
      mermaid: admitted.mermaid, dompurify: admitted.dompurify, katex: admitted.katex, esbuild: esbuild.version,
      source_origin: "https://github.com/mermaid-js/mermaid",
      source_release: "mermaid@11.17.2", source_commit: "dcb694ddb58dc5ad3502e7e903cac05fd812eac3" },
    output: emitted.sort((a, b) => compare(a.name, b.name)),
    license_sha256: hash(notices),
    bundled_inputs: inputIdentities.sort((a, b) => compare(a.path, b.path)),
    bundled_packages: packages.map(({ license_texts, ...identity }) => identity),
    verification_scope: "Exact locked ESM dependency graph bundled locally; upstream signature/provenance verification and browser corpus are separate evidence.",
  };
  await writeGenerated("provenance.json", JSON.stringify(provenance, null, 2) + "\n");
  await writeGenerated("build-receipt.json", JSON.stringify({
    schema: 1, node: process.versions.node, platform: process.platform, architecture: process.arch,
    esbuild: esbuild.version, provenance_sha256: hash(JSON.stringify(provenance, null, 2) + "\n"),
    output: provenance.output,
    scope: "Actual local toolchain; platform-independent content identity is retained in provenance.json.",
  }, null, 2) + "\n");
  console.log(JSON.stringify({ output: provenance.output, licenses: packages.length, provenance: path.join(options["output-dir"], "provenance.json") }));
}

build().catch((error) => { console.error(`Diagram build rejected: ${error.message}`); process.exitCode = 1; });
