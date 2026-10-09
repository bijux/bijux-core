#!/usr/bin/env node
/** Install the locked build graph without writing dependency caches into source. */
import { copyFile, lstat, mkdir, realpath, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

async function install() {
  if (Number(process.versions.node.split(".")[0]) < 22) throw new Error("Node 22 or newer required");
  const args = process.argv.slice(2);
  if (args.length !== 2 || args[0] !== "--artifact-root") throw new Error("Expected --artifact-root artifacts/DIR");
  const cwd = await realpath(process.cwd());
  const output = path.resolve(args[1]);
  const boundary = path.join(cwd, "artifacts") + path.sep;
  if (!output.startsWith(boundary)) throw new Error("Dependency install must remain under the active repository artifacts/");
  await mkdir(output, { recursive: true });
  if (!(await realpath(output)).startsWith(boundary)) throw new Error("Dependency artifact symlink escapes artifacts/");
  const source = path.dirname(fileURLToPath(import.meta.url));
  const dependencies = path.join(output, "build");
  const cache = path.join(output, "npm-cache");
  for (const directory of [dependencies, cache]) {
    await mkdir(directory, { recursive: true });
    if (!(await realpath(directory)).startsWith(boundary)) throw new Error("Dependency install/cache symlink escapes artifacts/");
  }
  for (const filename of ["package.json", "package-lock.json"]) {
    const destination = path.join(dependencies, filename);
    const existing = await lstat(destination).catch((error) => { if (error.code === "ENOENT") return null; throw error; });
    if (existing && (!existing.isFile() || existing.nlink !== 1)) throw new Error("Dependency manifest destination is not an unlinked regular file");
    await copyFile(path.join(source, filename), destination);
  }
  const result = spawnSync("npm", ["ci", "--prefix", dependencies, "--ignore-scripts", "--no-audit", "--cache", cache], { stdio: "inherit" });
  if (result.error || result.status !== 0) throw new Error("Pinned npm ci failed");
  const audit = spawnSync("npm", ["audit", "--prefix", dependencies, "--json", "--cache", cache], { encoding: "utf8" });
  if (audit.error) throw new Error("npm audit could not execute");
  await writeFile(path.join(output, "npm-audit.json"), audit.stdout);
  if (audit.status !== 0) throw new Error("npm audit rejected the pinned graph; inspect the retained artifact report");
  const report = JSON.parse(audit.stdout);
  if (report.metadata?.vulnerabilities?.total !== 0) throw new Error("npm audit did not certify an empty advisory result");
}

install().catch((error) => { console.error(`Diagram install rejected: ${error.message}`); process.exitCode = 1; });
