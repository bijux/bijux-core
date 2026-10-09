#!/usr/bin/env python3
"""Bind documentation source and the actual MkDocs renderer to a built artifact."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import types

sys.dont_write_bytecode = True

SHA = re.compile(r"[0-9a-f]{40}")
STANDARD_ORIGINS = {"https://github.com/bijux/bijux-std.git", "git@github.com:bijux/bijux-std.git"}


class IdentityError(ValueError):
    """An identity cannot support publication of the selected artifact."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IdentityError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_digest(value: dict) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def publication():
    spec = importlib.util.spec_from_file_location("bijux_publication_identity", Path(__file__).with_name("publication.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    require(result.returncode == 0, "Source identity: required Git operation failed")
    return result.stdout.strip()


def clean_source(root: Path, expected: str) -> dict:
    require(bool(SHA.fullmatch(expected)), "Source identity: full lowercase commit SHA required")
    require(Path(git(root, "rev-parse", "--show-toplevel")).resolve() == root.resolve(),
            "Source identity: select the exact repository root")
    require(git(root, "rev-parse", "HEAD") == expected, "Source identity: checkout HEAD differs")
    require(not git(root, "status", "--porcelain", "--untracked-files=all"),
            "Source identity: tracked or untracked source is dirty")
    return {"sha": expected, "tree": git(root, "rev-parse", "HEAD^{tree}")}


def regular(root: Path, value: str) -> Path:
    path = Path(value)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == value,
            "Identity input: normalized relative path required")
    current = root
    for part in path.parts:
        current /= part
        require(not current.is_symlink(), "Identity input: symlink path forbidden")
    require(current.is_file() and current.stat().st_nlink == 1, "Identity input: unlinked regular file required")
    return current


def artifact(root: Path, value: str) -> Path:
    path = Path(value)
    require(not path.is_absolute() and len(path.parts) > 1 and path.parts[0] == "artifacts"
            and ".." not in path.parts and str(path) == value, "Receipt: relative artifacts/ path required")
    current = root
    for part in path.parts:
        current /= part
        require(not current.is_symlink(), "Receipt: symlink path forbidden")
    if current.exists():
        require(current.is_file() and current.stat().st_nlink == 1, "Receipt: unlinked regular file required")
    return current


def tree_identity(root: Path) -> str:
    files = []
    require(root.is_dir() and not root.is_symlink(), "Standard identity: shared documentation tree missing")
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Standard identity: symlink tree is forbidden")
        if path.is_dir():
            continue
        require(path.is_file(), "Standard identity: nonregular shared input")
        files.append({"path": path.relative_to(root).as_posix(), "sha256": digest(path.read_bytes())})
    require(bool(files), "Standard identity: empty shared tree")
    return json_digest({"files": files})


def fetched_standard(root: Path, expected: str, *, fetch: bool) -> dict:
    clean_source(root, expected)
    origin = git(root, "remote", "get-url", "origin")
    require(origin in STANDARD_ORIGINS, "Standard identity: official bijux-std GitHub origin required")
    if fetch:
        git(root, "fetch", "--quiet", "--depth", "1", "origin", expected)
    require(git(root, "rev-parse", "FETCH_HEAD^{commit}") == expected,
            "Standard identity: exact fetched object differs or is missing")
    clean_source(root, expected)
    tracked = set(git(root, "ls-files", "-z", "--", "shared/bijux-docs").split("\0")) - {""}
    actual = {path.relative_to(root).as_posix() for path in (root / "shared/bijux-docs").rglob("*") if not path.is_dir()}
    require(actual == tracked, "Standard identity: ignored or untracked shared inputs differ from the accepted Git tree")
    return {"sha": expected, "origin": origin, "shared_tree_sha256": tree_identity(root / "shared/bijux-docs")}


def catalogue_derivation(root: Path, recipe: str, expected=None):
    """Only the adjacent reviewed helper may reconstruct catalogue selection."""
    path = Path(__file__).with_name("catalogue_recipe.py")
    require(path.is_file() and not path.is_symlink(), "Catalogue identity: reviewed shared helper required")
    captured = path.read_bytes()
    spec = importlib.util.spec_from_file_location("bijux_catalogue_identity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.derive(root, path.parent.parent, recipe, expected=expected)
    require(path.read_bytes() == captured, "Catalogue identity: helper changed during reconstruction")
    return result


def source_checkpoint(root: Path, source_sha: str, standard_root: str,
                      site_url: str, site_dir: str, build_command: str, verify_command: str, config: str = "mkdocs.yml", source_recipe: str | None = None) -> dict:
    for key in ("BIJUX_STD_LOCAL_VERIFY", "BIJUX_STD_ALLOW_LOCAL_SOURCE"):
        require(os.environ.get(key, "0") != "1", "Publication identity: local verification bypass forbidden")
    boundary = publication()
    boundary.validate_url(site_url)
    boundary.site_directory(root, site_dir)
    source = clean_source(root, source_sha)
    config_path = regular(root, config)
    git(root, "ls-files", "--error-unmatch", config)
    owned_config = {"path": config, "sha256": digest(config_path.read_bytes())}
    pin_path = regular(root, ".github/standards/bijux-std.sha")
    git(root, "ls-files", "--error-unmatch", ".github/standards/bijux-std.sha")
    pin = pin_path.read_text().strip()
    require(bool(SHA.fullmatch(pin)), "Standard identity: tracked exact accepted pin required")
    standard = boundary.site_directory(root, standard_root)
    authority = fetched_standard(standard, pin, fetch=True)
    shared = root / ".bijux/shared/bijux-docs"
    if not shared.is_dir():
        shared = root / "shared/bijux-docs"
    require(tree_identity(shared) == authority["shared_tree_sha256"],
            "Standard identity: consumed shared documentation differs from fetched accepted source")
    require(build_command.strip() and verify_command.strip(), "Publication identity: build and verifier commands required")
    result = {"schema": 1, "scope": "clean-source-and-fetched-standard", "verification_only": False,
            "repository_source": source, "standard": authority,
            "standard_root": standard.relative_to(root).as_posix(),
            "pin_sha256": digest(pin_path.read_bytes()), "shared_root": shared.relative_to(root).as_posix(),
            "site_url": site_url, "site_dir": site_dir, "config": owned_config,
            "build_command_sha256": digest(build_command.encode()),
            "verify_command_sha256": digest(verify_command.encode())}
    if source_recipe:
        derived = catalogue_derivation(root, source_recipe)
        require(derived.record["owner"] == owned_config, "Catalogue identity: tracked configuration owner differs")
        result["derivation"] = derived.record
    return result


def verify_source(root: Path, checkpoint: dict) -> None:
    require(checkpoint.get("schema") == 1 and checkpoint.get("verification_only") is False,
            "Publication identity: qualified source checkpoint required")
    require(clean_source(root, checkpoint["repository_source"]["sha"]) == checkpoint["repository_source"],
            "Source identity: tree changed after capture")
    config = checkpoint.get("config")
    require(isinstance(config, dict) and set(config) == {"path", "sha256"}, "Source identity: owner config checkpoint required")
    git(root, "ls-files", "--error-unmatch", config["path"])
    require(digest(regular(root, config["path"]).read_bytes()) == config["sha256"], "Source identity: owner config changed")
    pin = regular(root, ".github/standards/bijux-std.sha")
    require(digest(pin.read_bytes()) == checkpoint["pin_sha256"], "Standard identity: accepted pin changed")
    require(pin.read_text().strip() == checkpoint["standard"]["sha"], "Standard identity: fetched source differs from tracked accepted pin")
    boundary = publication()
    standard_root = boundary.site_directory(root, checkpoint["standard_root"])
    boundary.validate_url(checkpoint["site_url"])
    boundary.site_directory(root, checkpoint["site_dir"])
    require(checkpoint["shared_root"] in {"shared/bijux-docs", ".bijux/shared/bijux-docs"},
            "Standard identity: unexpected shared source location")
    authority = fetched_standard(standard_root, checkpoint["standard"]["sha"], fetch=False)
    require(authority == checkpoint["standard"], "Standard identity: fetched source changed")
    require(tree_identity(root / checkpoint["shared_root"]) == authority["shared_tree_sha256"],
            "Standard identity: consumed shared source changed")
    if "derivation" in checkpoint:
        record = checkpoint["derivation"]
        require(isinstance(record, dict) and record.get("owner") == config,
                "Catalogue identity: tracked owner checkpoint required")
        catalogue_derivation(root, record.get("recipe"), record)


def renderer(configuration=None, catalogue=None) -> dict:
    # Execute this module with DOCS_PYTHON, the same interpreter as the adjacent build.
    packages = {name: importlib.metadata.version(name) for name in
                ("mkdocs", "mkdocs-material", "Jinja2", "PyYAML", "Markdown", "Pygments", "pymdown-extensions")}
    plugins = {}
    if configuration is not None:
        owners = importlib.metadata.packages_distributions()
        for name, plugin in configuration.plugins.items():
            module = plugin.__name__ if isinstance(plugin, types.ModuleType) else type(plugin).__module__
            distributions = owners.get(module.split(".")[0], [])
            if catalogue is not None and name == "bijux/catalogue-sources":
                require(plugin is catalogue.plugin, "Catalogue identity: foreign renderer plugin")
                loaded = catalogue.helper
            else:
                loaded = plugin if isinstance(plugin, types.ModuleType) else sys.modules.get(module)
            source = Path(loaded.__file__) if loaded is not None and getattr(loaded, "__file__", None) else None
            require(source is not None and source.is_file() and not source.is_symlink(),
                    "Build identity: actual plugin source fingerprint missing")
            plugins[name] = {"module": module, "distributions":
                             {owner: importlib.metadata.version(owner) for owner in sorted(distributions)},
                             "source": {"name": source.name, "sha256": digest(source.read_bytes())}}
            if name == "redirects":
                from mkdocs.structure.files import File, get_files
                mapping = dict(plugin.config.get("redirect_maps", {}))
                documents = {file.src_uri: file for file in get_files(configuration).documentation_pages()}
                routes = []
                for old, new in sorted(mapping.items()):
                    require(isinstance(old, str) and isinstance(new, str), "Build identity: string redirect parameters required")
                    destination = documents.get(new.partition("#")[0])
                    require(destination is not None, "Build identity: redirect target must be an actual internal documentation source")
                    routes.append({"source": old, "path": File(old, "", "", configuration.use_directory_urls).dest_uri,
                                   "declared_target": new, "destination": destination.dest_uri, "url": destination.url})
                plugins[name].update({"redirect_map_sha256": json_digest(mapping), "redirect_maps": mapping,
                                     "use_directory_urls": configuration.use_directory_urls, "routes": routes})
    import material
    templates = Path(material.__file__).parent / "templates"
    material_inputs = [{"path": path.relative_to(templates).as_posix(), "sha256": digest(path.read_bytes())}
                       for path in sorted((templates / "partials/javascripts").rglob("*.html"))]
    require(bool(material_inputs), "Build identity: actual Material policy templates missing")
    return {"python": sys.version.split()[0], "implementation": sys.implementation.name,
            "executable": sys.executable, "environment": sys.prefix,
            "packages": packages, "plugins": plugins, "material_templates": material_inputs}


def configuration_identity(configuration, root: Path) -> str:
    """Bind resolved !ENV values without retaining values that may contain secrets."""
    def normalize(value):
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, (str, Path)):
            return str(value).replace(str(root), "{repository}")
        if hasattr(value, "items"):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [normalize(item) for item in value]
        identity = {"type": type(value).__module__ + "." + type(value).__qualname__}
        if hasattr(value, "config") and value.config is not value:
            identity["config"] = normalize(value.config)
        return identity
    return json_digest(normalize(configuration))


def source_inputs(configuration, root: Path, *, publication_scope: bool, catalogue=None) -> list[dict]:
    directories = [Path(configuration.docs_dir)]
    custom = configuration.theme.get("custom_dir")
    if custom:
        directories.append(Path(custom))
    for module in configuration.hooks.values():
        source = Path(module.__file__)
        require(source.is_relative_to(root), "Build identity: authored hook must belong to the repository")
        relative = source.relative_to(root).as_posix()
        regular(root, relative)
        if publication_scope:
            git(root, "ls-files", "--error-unmatch", relative)
    if catalogue is not None:
        return catalogue.input_records(configuration)
    records = []
    for directory in sorted(set(directories)):
        require(directory.is_relative_to(root), "Build identity: renderer source input must belong to the repository")
        relative = directory.relative_to(root).as_posix()
        fingerprint = tree_identity(directory)
        if publication_scope and not directory.is_relative_to(root / "artifacts"):
            tracked = set(git(root, "ls-files", "-z", "--", relative).split("\0")) - {""}
            actual = {path.relative_to(root).as_posix() for path in directory.rglob("*") if not path.is_dir()}
            require(actual == tracked, "Build identity: ignored renderer source cannot be attributed to the selected commit")
        records.append({"path": relative, "sha256": fingerprint})
    return records


def begin(root: Path, config: str, site_dir: str, site_url: str, source_path: str | None,
          source_recipe: str | None = None) -> dict:
    from mkdocs.config import load_config
    path = regular(root, config)
    actual_source = None
    if source_path:
        actual_source = json.loads(regular(root, source_path).read_text())
        verify_source(root, actual_source)
        record = actual_source.get("derivation")
        require(record is None or isinstance(record, dict), "Catalogue identity: typed derivation record required")
        require(source_recipe is None or record is not None and record.get("recipe") == source_recipe,
                "Catalogue identity: selected recipe differs from source checkpoint")
        source_recipe = record.get("recipe") if record else None
    catalogue = catalogue_derivation(root, source_recipe,
                                     actual_source.get("derivation") if actual_source else None) if source_recipe else None
    if catalogue:
        require(config == catalogue.record["configuration"]["path"], "Catalogue identity: derived config selection differs")
        configuration = catalogue.configuration(root / site_dir)
        owned = catalogue.record["owner"]
    else:
        configuration = load_config(config_file=str(path), site_dir=str(root / site_dir))
        owned = {"path": config, "sha256": digest(path.read_bytes())}
    site_url = site_url or configuration.site_url
    require(isinstance(site_url, str) and bool(site_url), "Build identity: actual config production URL required")
    boundary = publication()
    boundary.validate_url(site_url)
    boundary.site_directory(root, site_dir)
    require(configuration.site_url == site_url, "Build identity: actual MkDocs config production URL differs")
    if actual_source:
        require(actual_source["site_url"] == site_url and actual_source["site_dir"] == site_dir,
                "Build identity: source checkpoint selects another artifact")
        require(actual_source["config"] == owned, "Build identity: owner-selected config differs")
    result = {"schema": 1, "scope": "actual-mkdocs-renderer", "state": "prepared",
              "verification_only": actual_source is None, "site_url": site_url, "site_dir": site_dir,
              "config": owned, "renderer": renderer(configuration, catalogue),
              "resolved_config_sha256": configuration_identity(configuration, root),
              "renderer_inputs": source_inputs(configuration, root, publication_scope=actual_source is not None, catalogue=catalogue),
              "processor_sha256": digest(Path(__file__).read_bytes()),
              "source_checkpoint": actual_source,
              "source_checkpoint_sha256": json_digest(actual_source) if actual_source else None}
    if catalogue:
        result.update(effective_config=catalogue.record["configuration"], derivation=catalogue.record)
    return result


def finish(root: Path, receipt: dict) -> dict:
    require(receipt.get("schema") == 1 and receipt.get("state") == "prepared", "Build identity: prepared receipt required")
    require(digest(regular(root, receipt["config"]["path"]).read_bytes()) == receipt["config"]["sha256"],
            "Build identity: effective renderer configuration changed")
    require(digest(Path(__file__).read_bytes()) == receipt["processor_sha256"], "Build identity: identity processor changed")
    from mkdocs.config import load_config
    record = receipt.get("derivation")
    require(record is None or isinstance(record, dict), "Catalogue identity: typed derivation record required")
    catalogue = catalogue_derivation(root, record.get("recipe"), record) if record else None
    if catalogue:
        require(receipt.get("effective_config") == catalogue.record["configuration"],
                "Catalogue identity: effective configuration differs")
        actual_config = catalogue.configuration(root / receipt["site_dir"])
    else:
        require("effective_config" not in receipt, "Build identity: unreviewed derived configuration")
        actual_config = load_config(config_file=str(root / receipt["config"]["path"]), site_dir=str(root / receipt["site_dir"]))
    require(renderer(actual_config, catalogue) == receipt["renderer"], "Build identity: actual renderer toolchain changed")
    require(configuration_identity(actual_config, root) == receipt["resolved_config_sha256"],
            "Build identity: resolved renderer configuration/environment changed")
    require(source_inputs(actual_config, root, publication_scope=receipt["source_checkpoint"] is not None, catalogue=catalogue) == receipt["renderer_inputs"],
            "Build identity: renderer source inputs changed during build")
    if receipt["source_checkpoint"]:
        verify_source(root, receipt["source_checkpoint"])
        require(receipt.get("derivation") == receipt["source_checkpoint"].get("derivation"),
                "Catalogue identity: build/source derivation differs")
    module = publication()
    site = module.site_directory(root, receipt["site_dir"], exists=True)
    _, bundle = module.public_bundle_identity(site)
    return receipt | {"state": "complete", "bundle_sha256": bundle,
                      "limitations": ["Records the actual adjacent MkDocs build interpreter/configuration; browser/manual/live qualification is separate."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture-source")
    for name in ("source-sha", "standard-root", "site-url", "site-dir", "build-command", "verify-command", "output"):
        capture.add_argument("--" + name, required=True)
    capture.add_argument("--config", default="mkdocs.yml")
    capture.add_argument("--source-recipe", choices=["masterclass-catalogue"])
    prepare = commands.add_parser("begin")
    for name in ("config", "site-dir", "site-url", "output"):
        prepare.add_argument("--" + name, required=True)
    prepare.add_argument("--source-recipe", choices=["masterclass-catalogue"])
    prepare.add_argument("--source-checkpoint", default=os.environ.get("DOCS_SOURCE_IDENTITY"))
    complete = commands.add_parser("finish")
    complete.add_argument("--receipt", required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    try:
        if args.command == "capture-source":
            result = source_checkpoint(root, args.source_sha, args.standard_root, args.site_url, args.site_dir,
                                       args.build_command, args.verify_command, args.config, args.source_recipe)
            output = artifact(root, args.output)
        elif args.command == "begin":
            result = begin(root, args.config, args.site_dir, args.site_url, args.source_checkpoint, args.source_recipe)
            output = artifact(root, args.output)
        else:
            output = artifact(root, args.receipt)
            result = finish(root, json.loads(output.read_text()))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
    except (IdentityError, OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        parser.exit(1, f"Documentation identity rejected: {exc}\n")
    print(json.dumps({"state": result.get("state"), "scope": result["scope"], "verification_only": result["verification_only"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
