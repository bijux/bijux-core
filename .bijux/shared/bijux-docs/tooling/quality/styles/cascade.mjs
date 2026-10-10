/* Guard owned stylesheet strategy and declaration exceptions; rendered behavior has separate owners. */
import { createHash } from "node:crypto";
import { readFile, realpath, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const documentation = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const repository = path.resolve(documentation, "../..");
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const strings = (value) => Array.isArray(value) && value.every((entry) => typeof entry === "string" && entry.length);
const identity = (entry) => JSON.stringify([entry.file, entry.conditions, entry.selectors, entry.property]);
const importantIdentity = (entry) => JSON.stringify([identity(entry), entry.value]);
const duplicateIdentity = (entry) => JSON.stringify([identity(entry), entry.values]);

async function regular(filename) {
  if (await realpath(filename) !== path.resolve(filename) || !(await stat(filename)).isFile()) {
    throw new Error(`${filename}: expected an owned regular file without linked path components`);
  }
  return readFile(filename);
}

async function parser(dependencies) {
  const source = path.join(documentation, "tooling/diagrams");
  for (const name of ["package.json", "package-lock.json"]) {
    const [expected, installed] = await Promise.all([regular(path.join(source, name)), regular(path.join(dependencies, name))]);
    if (!expected.equals(installed)) throw new Error(`${dependencies}/${name}: installed diagram manifest differs`);
  }
  const provenance = JSON.parse(await regular(path.join(source, "provenance.json")));
  const lock = JSON.parse(await regular(path.join(source, "package-lock.json")));
  const owned = provenance.bundled_packages.find((entry) => entry.name === "stylis");
  const pinned = lock.packages["node_modules/stylis"];
  if (!owned || owned.version !== pinned.version || owned.integrity !== pinned.integrity || owned.resolved !== pinned.resolved) {
    throw new Error("Stylis parser provenance differs from the exact diagram lock");
  }
  const installed = JSON.parse(await regular(path.join(dependencies, "node_modules/stylis/package.json")));
  if (installed.name !== "stylis" || installed.version !== pinned.version || installed.type !== "module") {
    throw new Error("Installed Stylis parser identity differs from the admitted module");
  }
  const files = provenance.bundled_inputs.filter((entry) => entry.path.startsWith("node_modules/stylis/"));
  if (!files.some((entry) => entry.path === "node_modules/stylis/index.js") || !files.some((entry) => entry.path === "node_modules/stylis/src/Parser.js")) {
    throw new Error("Stylis parser source provenance is incomplete");
  }
  for (const entry of files) {
    const bytes = await regular(path.join(dependencies, entry.path));
    if (bytes.length !== entry.bytes || digest(bytes) !== entry.sha256) throw new Error(`${entry.path}: changed admitted parser source`);
  }
  return { module: await import(pathToFileURL(path.join(dependencies, "node_modules/stylis/index.js"))), version: owned.version, files };
}

function policyRecords(policy) {
  if (!object(policy) || policy.schema !== 1 || Object.keys(policy).sort().join() !== ["duplicate_fallbacks", "important_exceptions", "import_graph", "layer_strategy", "schema", "styles", "token_vocabulary"].sort().join()) {
    throw new Error("Cascade policy: unknown or missing fields/schema");
  }
  if (policy.token_vocabulary !== "style-tokens.json") throw new Error("Cascade policy: unknown token vocabulary ownership");
  const graph = policy.import_graph;
  if (!object(graph) || Object.keys(graph).sort().join() !== "entry,mode,owner,reason" ||
      graph.entry !== "extra.css" || graph.mode !== "ordered-domain-leaves" || graph.owner !== "bijux-std" ||
      typeof graph.reason !== "string" || !graph.reason.trim()) {
    throw new Error("Cascade policy: malformed or unsupported import_graph; only the owned ordered entry and domain leaves are admitted");
  }
  const strategy = policy.layer_strategy;
  if (!object(strategy) || Object.keys(strategy).sort().join() !== "mode,owner,reason" ||
      strategy.mode !== "unlayered" || strategy.owner !== "bijux-std" || typeof strategy.reason !== "string" || !strategy.reason.trim()) {
    throw new Error("Cascade policy: malformed or unsupported layer_strategy; only reviewed unlayered ownership is admitted");
  }
  if (!strings(policy.styles) || new Set(policy.styles).size !== policy.styles.length || policy.styles.some((name) => !/^\d\d-[a-z-]+\.css$/.test(name))) {
    throw new Error("Cascade policy: styles must be unique owned stylesheet names in import order");
  }
  for (const [field, valueField] of [["important_exceptions", "value"], ["duplicate_fallbacks", "values"]]) {
    if (!Array.isArray(policy[field])) throw new Error(`Cascade policy: ${field} must be a list`);
    const seen = new Set();
    for (const record of policy[field]) {
      const expected = ["file", "conditions", "selectors", "property", valueField, "owner", "reason", ...(field === "important_exceptions" ? ["necessity"] : [])];
      if (!object(record) || Object.keys(record).sort().join() !== expected.sort().join() || !policy.styles.includes(record.file) ||
          !strings(record.selectors) || !Array.isArray(record.conditions) || !record.conditions.every((entry) => typeof entry === "string" && entry.startsWith("@")) ||
          typeof record.property !== "string" || !record.property || record.owner !== "bijux-std" || typeof record.reason !== "string" || !record.reason.trim() ||
          (valueField === "value" ? typeof record.value !== "string" || !record.value || typeof record.necessity !== "string" || !record.necessity : !strings(record.values) || record.values.length !== 2)) {
        throw new Error(`Cascade policy: malformed ${field} record`);
      }
      const key = valueField === "value" ? importantIdentity(record) : duplicateIdentity(record);
      if (seen.has(key)) throw new Error(`Cascade policy: duplicate ${field} identity`);
      seen.add(key);
    }
  }
}

function tokenRecords(vocabulary, policy) {
  const fields = (value, names) => object(value) && Object.keys(value).sort().join() === names.sort().join();
  if (!fields(vocabulary, ["schema", "namespace", "owner", "external", "tokens"]) || vocabulary.schema !== 1 ||
      vocabulary.namespace !== "--bijux-" || vocabulary.owner !== "bijux-std" || !Array.isArray(vocabulary.tokens)) {
    throw new Error("Token vocabulary: unknown fields/schema/namespace/owner");
  }
  const external = vocabulary.external;
  if (!fields(external, ["namespace", "owner", "provenance", "runtime_sha256", "runtime_examples", "reason"]) ||
      external.namespace !== "--md-" || external.owner !== "mkdocs-material" || external.provenance !== "tooling/material/runtime-provenance.json" ||
      !/^[a-f0-9]{64}$/.test(external.runtime_sha256) || !strings(external.runtime_examples) || !external.runtime_examples.length ||
      new Set(external.runtime_examples).size !== external.runtime_examples.length ||
      external.runtime_examples.some((name) => !name.startsWith("--md-")) || typeof external.reason !== "string" || !external.reason.trim()) {
    throw new Error("Token vocabulary: malformed external runtime ownership");
  }
  const scopes = { "content-color": "qualified-content-theme", surface: "qualified-content-theme", shadow: "qualified-content-theme",
    geometry: "qualified-content-measure", focus: "shared-shell-focus" };
  const seen = new Set(), bindings = new Set();
  for (const token of vocabulary.tokens) {
    if (!fields(token, ["name", "purpose", "description", "consumer_scope", "bindings"]) ||
        typeof token.name !== "string" || !/^--bijux-[a-z][a-z0-9-]*$/.test(token.name) || seen.has(token.name) ||
        !Object.hasOwn(scopes, token.purpose) || token.consumer_scope !== scopes[token.purpose] ||
        typeof token.description !== "string" || !token.description.trim() || !Array.isArray(token.bindings) || !token.bindings.length) {
      throw new Error("Token vocabulary: malformed token name/purpose/consumer scope/bindings");
    }
    seen.add(token.name);
    for (const binding of token.bindings) {
      if (!fields(binding, ["file", "conditions", "selectors", "value", "role", "reason"]) || !policy.styles.includes(binding.file) ||
          !Array.isArray(binding.conditions) || !binding.conditions.every((condition) => typeof condition === "string" && condition.startsWith("@")) ||
          !strings(binding.selectors) || typeof binding.value !== "string" || !binding.value ||
          !["default", "palette", "responsive", "shell-focus"].includes(binding.role) || typeof binding.reason !== "string" || !binding.reason.trim()) {
        throw new Error("Token vocabulary: malformed owned definition binding");
      }
      const key = importantIdentity({ ...binding, property: token.name });
      if (bindings.has(key)) throw new Error("Token vocabulary: repeated definition binding");
      bindings.add(key);
    }
  }
}

export async function qualify({ styles, policy: policyPath, dependencies }) {
  const policy = JSON.parse(await regular(policyPath));
  policyRecords(policy);
  const vocabularyBytes = await regular(path.join(path.dirname(policyPath), policy.token_vocabulary));
  const vocabulary = JSON.parse(vocabularyBytes);
  tokenRecords(vocabulary, policy);
  const admitted = await parser(dependencies);
  const { compile, tokenize } = admitted.module;
  const runtime = JSON.parse(await regular(path.join(documentation, vocabulary.external.provenance)));
  const runtimeBytes = await regular(path.join(documentation, runtime.output_asset));
  if (runtime.output_sha256 !== vocabulary.external.runtime_sha256 || digest(runtimeBytes) !== runtime.output_sha256) {
    throw new Error("Token vocabulary: stale external runtime source");
  }
  const runtimeText = runtimeBytes.toString();
  if (vocabulary.external.runtime_examples.some((name) => !runtimeText.includes(`.setProperty("${name}"`))) {
    throw new Error("Token vocabulary: external runtime example has no admitted literal writer");
  }
  const decode = (value) => value.replace(/\\([0-9a-f]{1,6})(?:[ \t\r\n\f])?|\\([^\r\n\f])/gi, (_, hex, character) => {
    if (character) return character;
    const point = Number.parseInt(hex, 16);
    return !point || point > 0x10ffff || point >= 0xd800 && point <= 0xdfff ? "\uFFFD" : String.fromCodePoint(point);
  });
  const property = (value) => {
    const decoded = decode(value);
    return decoded.startsWith("--") ? decoded : decoded.toLowerCase();
  };
  const atKeyword = (node) => {
    if (!node.type.startsWith("@")) return "";
    // The parser retains the keyword boundary across comments, unlike its concatenated value.
    if (!node.type.includes("\\")) return node.type.slice(1).toLowerCase();
    // An escaped keyword type can end at the hex escape's terminator. Read the complete
    // escaped identifier from the parsed value before decoding; an escaped space is part
    // of that identifier, not a separator that turns a different keyword into @layer.
    const keyword = /^@((?:\\(?:[0-9a-f]{1,6}[ \t\r\n\f]?|[^\r\n\f])|[a-z0-9_-]|[^\x00-\x7f])+)/i.exec(node.value);
    return keyword ? decode(keyword[1]).toLowerCase() : "";
  };
  const priority = (value) => {
    const tokens = tokenize(value).filter((token) => token.trim());
    return tokens.at(-2) === "!" && decode(tokens.at(-1) || "").toLowerCase() === "important";
  };
  const identifier = /^(?:\\(?:[0-9a-f]{1,6}[ \t\r\n\f]?|[^\r\n\f])|[a-z0-9_-]|[^\x00-\x7f])+/i;
  function valueReferences(value, depth = 0) {
    if (depth > 64) throw new Error("token_value_limit");
    const references = [];
    for (let offset = 0; offset < value.length;) {
      const character = value[offset];
      if (character === '"' || character === "'") {
        const quote = character;
        for (++offset; offset < value.length; offset++) {
          if (value[offset] === "\\") offset++;
          else if (value[offset] === quote) { offset++; break; }
        }
        continue;
      }
      if (value.startsWith("/*", offset)) {
        const end = value.indexOf("*/", offset + 2);
        offset = end < 0 ? value.length : end + 2;
        continue;
      }
      const token = identifier.exec(value.slice(offset));
      if (!token) { offset++; continue; }
      const end = offset + token[0].length;
      if (value[end] !== "(") { offset = end; continue; }
      // Stylis supplies balanced component groups; this walker only identifies var arguments.
      const group = tokenize(value.slice(end))[0];
      if (!group?.startsWith("(") || !group.endsWith(")")) throw new Error("malformed_token_reference");
      const body = group.slice(1, -1);
      if (decode(token[0]).toLowerCase() === "var") {
        const parts = tokenize(body), comma = parts.indexOf(",");
        const argument = parts.slice(0, comma < 0 ? parts.length : comma).join("").trim();
        const nameToken = identifier.exec(argument);
        if (!nameToken || nameToken[0].length !== argument.length) throw new Error("malformed_token_reference");
        const name = decode(argument);
        if (!name.startsWith("--") || name.length === 2) throw new Error("malformed_token_reference");
        const fallback = comma < 0 ? "" : parts.slice(comma + 1).join("");
        references.push({ name, has_fallback: Boolean(fallback.trim()) }, ...valueReferences(fallback, depth + 1));
      } else references.push(...valueReferences(body, depth + 1));
      if (references.length > 1024) throw new Error("token_value_limit");
      offset = end + group.length;
    }
    return references;
  }
  const entry = await regular(path.join(styles, policy.import_graph.entry));
  const imports = compile(entry.toString());
  const names = [], edges = [];
  for (const node of imports) {
    if (node.type === "comm") continue;
    const match = node.type === "@import" && /^@import url\("\.\/([a-z0-9-]+\.css)"\);$/.exec(node.value);
    if (!match) throw new Error(`extra.css:${node.line}:${node.column}: expected only canonical local stylesheet imports`);
    names.push(match[1]);
    edges.push({ file: policy.import_graph.entry, target: match[1], value: node.value, line: node.line, column: node.column });
  }
  if (JSON.stringify(names) !== JSON.stringify(policy.styles)) throw new Error("extra.css: stylesheet import order differs from cascade policy");
  const sourceFiles = { [policy.import_graph.entry]: digest(entry) }, sheets = [], importErrors = [];
  const importGraph = { entry: policy.import_graph.entry, edges, domain_leaves: names };
  function inspectImports(nodes, file, conditions = []) {
    for (const node of nodes) {
      if (atKeyword(node) === "import") {
        importErrors.push({ kind: "unreviewed_import", file, conditions, value: node.value, line: node.line, column: node.column });
      }
      if (Array.isArray(node.children)) {
        inspectImports(node.children, file, node.type.startsWith("@") ? [...conditions, node.value] : conditions);
      }
    }
  }
  // Inspect only owned graph nodes. Never follow an undeclared local or remote edge.
  for (const file of names) {
    const bytes = await regular(path.join(styles, file)), nodes = compile(bytes.toString());
    sourceFiles[file] = digest(bytes);
    sheets.push({ file, nodes });
    inspectImports(nodes, file);
  }
  if (importErrors.length) {
    return { status: "failed", stage: "import_graph", source_files: sourceFiles, styles: names.length,
      declarations: 0, important_declarations: 0, duplicate_fallbacks: 0, import_graph: importGraph,
      layer_strategy: policy.layer_strategy, parser: { name: "stylis", version: admitted.version, files: admitted.files },
      errors: importErrors, diagnostics: [], limits: ["Owned import graph refused before declaration qualification; undeclared destinations were not read or fetched", "Parser lines/columns are source end locations", "Authored consumer extra_css extensions remain outside this shared graph"] };
  }
  const declarations = [], duplicates = [], layers = [];
  function walk(nodes, file, conditions = [], selectors = []) {
    for (const node of nodes) {
      if (atKeyword(node) === "layer") {
        layers.push({ kind: "unreviewed_layer", file, conditions, value: node.value, line: node.line, column: node.column });
      }
      if (node.type === "decl") {
        declarations.push({ file, conditions, selectors, property: property(node.props), value: node.children, important: priority(node.children), line: node.line, column: node.column });
      } else if (Array.isArray(node.children)) {
        const nextConditions = node.type.startsWith("@") ? [...conditions, node.value] : conditions;
        const nextSelectors = node.type === "rule" ? node.props : selectors;
        if (node.type === "rule") {
          const seen = new Map();
          for (const declaration of node.children.filter((child) => child.type === "decl")) {
            const name = property(declaration.props), previous = seen.get(name);
            if (previous) duplicates.push({ file, conditions: nextConditions, selectors: nextSelectors, property: name, values: [previous.children, declaration.children], line: declaration.line, column: declaration.column, earlier_line: previous.line });
            seen.set(name, declaration);
          }
        }
        walk(node.children, file, nextConditions, nextSelectors);
      }
    }
  }
  for (const { file, nodes } of sheets) walk(nodes, file);
  const errors = [...layers], diagnostics = [], usedImportant = new Set(), usedDuplicates = new Set();
  const ownedNamespace = (name) => name.toLowerCase().startsWith(vocabulary.namespace);
  const tokens = new Map(vocabulary.tokens.map((token) => [token.name, token]));
  const bindings = new Map();
  for (const token of vocabulary.tokens) for (const binding of token.bindings) {
    bindings.set(importantIdentity({ ...binding, property: token.name }), { ...binding, property: token.name });
  }
  const usedBindings = new Set(), tokenReferences = [], scopeGraphs = new Map(), scopeSources = new Map();
  for (const declaration of declarations) {
    if (ownedNamespace(declaration.property)) {
      if (!tokens.has(declaration.property)) errors.push({ kind: "unreviewed_token_definition", ...declaration });
      else {
        const key = importantIdentity(declaration);
        if (!bindings.has(key)) errors.push({ kind: "unreviewed_token_binding", ...declaration });
        else if (usedBindings.has(key)) errors.push({ kind: "repeated_token_binding", ...declaration });
        else usedBindings.add(key);
      }
    }
    let references;
    try { references = valueReferences(declaration.value); }
    catch (error) { errors.push({ kind: error.message, ...declaration }); continue; }
    for (const reference of references) {
      const observed = { ...declaration, ...reference };
      tokenReferences.push(observed);
      if (ownedNamespace(reference.name) && !tokens.has(reference.name) && !reference.has_fallback) {
        errors.push({ kind: "unresolved_token_reference", ...observed });
      }
    }
    if (ownedNamespace(declaration.property)) {
      const scope = JSON.stringify([declaration.conditions, declaration.selectors]);
      if (!scopeGraphs.has(scope)) { scopeGraphs.set(scope, new Map()); scopeSources.set(scope, []); }
      scopeSources.get(scope).push(declaration);
      const graph = scopeGraphs.get(scope);
      if (!graph.has(declaration.property)) graph.set(declaration.property, new Set());
      for (const reference of references) if (tokens.has(reference.name)) graph.get(declaration.property).add(reference.name);
    }
  }
  for (const [key, binding] of bindings) if (!usedBindings.has(key)) errors.push({ kind: "stale_token_binding", ...binding });
  // Only exact shared definition scopes are compared; this is not a native inheritance model.
  for (const [scope, graph] of scopeGraphs) {
    const visiting = [], visited = new Set();
    function visit(name) {
      if (visiting.includes(name)) {
        const names = [...visiting.slice(visiting.indexOf(name)), name];
        errors.push({ kind: "token_cycle", scope: JSON.parse(scope), names,
          source_locations: scopeSources.get(scope).filter((declaration) => names.includes(declaration.property)) });
        return;
      }
      if (visited.has(name)) return;
      visiting.push(name);
      for (const target of graph.get(name) || []) if (graph.has(target)) visit(target);
      visiting.pop(); visited.add(name);
    }
    for (const name of graph.keys()) visit(name);
  }
  const important = new Map(policy.important_exceptions.map((record) => [importantIdentity(record), record]));
  const fallback = new Map(policy.duplicate_fallbacks.map((record) => [duplicateIdentity(record), record]));
  for (const declaration of declarations.filter((entry) => entry.important)) {
    const key = importantIdentity(declaration), exception = important.get(key);
    if (!exception) errors.push({ kind: "unreviewed_important", ...declaration });
    else if (usedImportant.has(key)) errors.push({ kind: "repeated_important_exception", ...declaration });
    else { usedImportant.add(key); diagnostics.push({ kind: "important_exception", ...declaration, reason: exception.reason, necessity: exception.necessity }); }
  }
  for (const duplicate of duplicates) {
    const key = duplicateIdentity(duplicate), exception = fallback.get(key);
    if (!exception) errors.push({ kind: "unintended_duplicate", ...duplicate });
    else if (usedDuplicates.has(key)) errors.push({ kind: "repeated_duplicate_fallback", ...duplicate });
    else { usedDuplicates.add(key); diagnostics.push({ kind: "viewport_fallback", ...duplicate, reason: exception.reason }); }
  }
  for (const [key, record] of important) if (!usedImportant.has(key)) errors.push({ kind: "stale_important_exception", ...record });
  for (const [key, record] of fallback) if (!usedDuplicates.has(key)) errors.push({ kind: "stale_duplicate_fallback", ...record });
  const hidden = declarations.filter((entry) => entry.file === "07-utilities.css" && !entry.conditions.length && JSON.stringify(entry.selectors) === JSON.stringify(['[hidden]:not([hidden="until-found"])']) && entry.property === "display");
  if (hidden.length !== 1 || hidden[0].value !== "none!important" || !hidden[0].important) errors.push({ kind: "semantic_hidden_invariant", file: "07-utilities.css", property: "display", expected: 'one unconditional [hidden]:not([hidden="until-found"]) display:none!important' });
  return { status: errors.length ? "failed" : "passed", source_files: sourceFiles, styles: names.length, declarations: declarations.length,
    important_declarations: declarations.filter((entry) => entry.important).length, duplicate_fallbacks: duplicates.length, import_graph: importGraph, layer_strategy: policy.layer_strategy,
    token_vocabulary: { file: policy.token_vocabulary, sha256: digest(vocabularyBytes), owner: vocabulary.owner, names: tokens.size, definition_bindings: bindings.size,
      external_runtime: { owner: vocabulary.external.owner, source: runtime.output_asset, sha256: digest(runtimeBytes), literal_writer_examples: vocabulary.external.runtime_examples } },
    token_references: tokenReferences, parser: { name: "stylis", version: admitted.version, files: admitted.files }, errors, diagnostics,
    limits: ["Owned ordered import graph, unlayered strategy, declaration bindings and token references only; no complete CSS validity, consuming value grammar, native inheritance or computed specificity proof", "Parser lines/columns are source end locations; cycle comparison is bounded to exact conditional/selector definition scopes", "Authored consumer imports/overrides/resources, computed order, themes, responsive modes and manual/live qualification remain separate"] };
}

if (path.resolve(process.argv[1] || "") === fileURLToPath(import.meta.url)) {
  try {
    const { values } = parseArgs({ options: { "styles-dir": { type: "string", default: path.join(documentation, "styles") }, policy: { type: "string", default: path.join(documentation, "config/cascade-contract.json") }, dependencies: { type: "string", default: process.env.BIJUX_DIAGRAM_DEPENDENCIES || path.join(repository, "artifacts/website-security/dependencies/build") } } });
    const result = await qualify({ styles: path.resolve(values["styles-dir"]), policy: path.resolve(values.policy), dependencies: path.resolve(values.dependencies) });
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    if (result.errors.length) process.exitCode = 1;
  } catch (error) {
    process.stderr.write(`ERROR: ${error.message}\nPrepare the existing pinned runtime with make -f shared/bijux-docs/tooling/diagrams/Makefile diagrams-install; a read-only qualified build may be selected with BIJUX_DIAGRAM_DEPENDENCIES.\n`);
    process.exitCode = 1;
  }
}
