#!/usr/bin/env python3
"""Validate Bijux docs contract in MkDocs configuration."""

from __future__ import annotations

import json
import hashlib
import re
import yaml
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration.ordered_assets import validate_effective_assets
from configuration.shell_contract import mapping, registry, validate_canonical_registry, validate_settings

DIAGRAM_POLICY = json.loads((Path(__file__).resolve().parents[2] / "config/mkdocs-baseline.json").read_text())["diagram"]
MERMAID_VENDOR = DIAGRAM_POLICY["vendor"]
MERMAID_SCRIPTS = ("assets/javascripts/mermaid-init.js",)


class MkDocsLoader(yaml.SafeLoader):
    """SafeLoader that tolerates MkDocs python/name tags and rejects shadowed keys."""

    def construct_mapping(self, node, deep=False):
        # Explicit duplicates are ambiguous even if their final value is valid.
        # Merge keys retain normal YAML inheritance; only explicit keys collide.
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise RuntimeError("configuration key must be a scalar") from exc
            if duplicate:
                raise RuntimeError(f"duplicate configuration key {key!r} at line {key_node.start_mark.line + 1}")
        return super().construct_mapping(node, deep=deep)


def _construct_unknown(loader: MkDocsLoader, tag_suffix: str, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


MkDocsLoader.add_multi_constructor("", _construct_unknown)


def load_yaml(path: Path) -> dict:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=MkDocsLoader)
        return mapping({} if value is None else value, str(path), "configuration")
    except Exception as exc:  # pragma: no cover - surfaced in command output
        raise RuntimeError(f"Failed to load {path}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_hub_links(hub_links: list[dict], config_name: str) -> None:
    registry(hub_links, config_name)

def validate_mermaid_contract(config: dict, config_name: str, diagram: dict | None = None) -> None:
    diagram = diagram or DIAGRAM_POLICY
    markdown_extensions = config.get("markdown_extensions") or []
    require(
        isinstance(markdown_extensions, list),
        f"{config_name}: markdown_extensions must be a list",
    )
    mermaid_fence_present = False
    for extension in markdown_extensions:
        if not isinstance(extension, dict):
            continue
        superfences = extension.get("pymdownx.superfences")
        if not isinstance(superfences, dict):
            continue
        custom_fences = superfences.get("custom_fences") or []
        for fence in custom_fences:
            if isinstance(fence, dict) and fence.get("name") == "mermaid":
                require(fence.get("class") == diagram["fence_class"], f"{config_name}: Mermaid fence class must be bijux-diagram to avoid Material external renderer")
                mermaid_fence_present = True
    require(
        mermaid_fence_present,
        f"{config_name}: markdown_extensions must include a pymdownx.superfences mermaid custom fence",
    )

    extra_javascript = config.get("extra_javascript") or []
    require(
        isinstance(extra_javascript, list),
        f"{config_name}: extra_javascript must be a list",
    )
    for script in extra_javascript:
        path = script if isinstance(script, str) else script.get("path", "") if isinstance(script, dict) else ""
        require(not re.search(r"(?:^|/)mermaid(?:[-.]\d[^/]*)?(?:\.min)?\.js(?:[?#]|$)", path), f"{config_name}: Mermaid vendor must be lazy-loaded, not eager extra_javascript")
    for script in MERMAID_SCRIPTS:
        require(
            script in extra_javascript,
            f"{config_name}: extra_javascript must include {script}",
        )

def validate_diagram_asset(repo_root: Path, baseline: dict) -> None:
    diagram = baseline.get("diagram") or {}
    require(diagram.get("fence_class") == "bijux-diagram", "baseline: diagram fence must avoid Material interception")
    require(diagram.get("security_level") == "strict", "baseline: diagram security must be strict")
    require(isinstance(diagram.get("vendor"), str) and re.fullmatch(r"assets/javascripts/vendor/mermaid-[0-9]+\.[0-9]+\.[0-9]+(?:[-.A-Za-z0-9]*)\.js", diagram["vendor"]), "baseline: diagram vendor must identify an owned versioned bundle")
    asset = repo_root / "docs" / diagram["vendor"]
    require(asset.is_file(), f"Missing packaged diagram vendor {asset}")
    require(hashlib.sha256(asset.read_bytes()).hexdigest() == diagram.get("sha256"), "Packaged diagram vendor digest differs from baseline")


def shared_docs_root(repo_root: Path) -> Path:
    local_root = repo_root / "shared/bijux-docs"
    if local_root.is_dir():
        return local_root
    return repo_root / ".bijux/shared/bijux-docs"


def load_canonical_hub_links(repo_root: Path) -> list[dict]:
    path = shared_docs_root(repo_root) / "config/hub-links.json"
    links = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(links, list) and links, f"{path}: expected a non-empty list")
    validate_hub_links(links, str(path))
    return links


def load_mkdocs_baseline(repo_root: Path) -> dict:
    path = shared_docs_root(repo_root) / "config/mkdocs-baseline.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    require(baseline.get("version") == 1, f"{path}: unsupported baseline version")
    return baseline


def configured_names(values: list, config_name: str) -> set[str]:
    names: set[str] = set()
    for value in values:
        if isinstance(value, str):
            names.add(value)
        elif isinstance(value, dict) and len(value) == 1:
            names.add(next(iter(value)))
        else:
            raise RuntimeError(f"{config_name}: expected names or single-key mappings")
    return names


def merge_mappings(parent: dict, child: dict) -> dict:
    """Merge inherited MkDocs mappings while treating lists as replacements."""
    merged = dict(parent)
    for key, child_value in child.items():
        parent_value = merged.get(key)
        if isinstance(parent_value, dict) and isinstance(child_value, dict):
            merged[key] = merge_mappings(parent_value, child_value)
        else:
            merged[key] = child_value
    return merged


def validate_mkdocs_baseline(config: dict, baseline: dict, config_name: str) -> None:
    """Validate shared MkDocs semantics while allowing product-owned additions."""
    required_exclusions = baseline.get('required_exclude_docs') or []
    if required_exclusions:
        exclusions = config.get('exclude_docs')
        require(isinstance(exclusions, str), f'{config_name}: exclude_docs must preserve the implementation boundary')
        rules = [line.strip() for line in exclusions.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        require(rules[-len(required_exclusions):] == required_exclusions,
                f'{config_name}: exclude_docs must end with the canonical implementation exclusions')
    for key in ("strict", "use_directory_urls", "dev_addr", "copyright"):
        require(
            config.get(key) == baseline[key],
            f"{config_name}: {key} must match the shared MkDocs baseline",
        )

    theme = config.get("theme") or {}
    expected_theme = baseline["theme"]
    for key in ("name", "language", "logo", "favicon", "font"):
        require(
            theme.get(key) == expected_theme[key],
            f"{config_name}: theme.{key} must match the shared MkDocs baseline",
        )
    require(
        (theme.get("icon") or {}).get("repo") == expected_theme["repository_icon"],
        f"{config_name}: theme.icon.repo must match the shared MkDocs baseline",
    )
    features = set(theme.get("features") or [])
    for feature in expected_theme["required_features"]:
        require(
            feature in features,
            f"{config_name}: theme.features must include {feature}",
        )

    plugins = configured_names(config.get("plugins") or [], f"{config_name}: plugins")
    extensions = configured_names(
        config.get("markdown_extensions") or [],
        f"{config_name}: markdown_extensions",
    )
    for plugin in baseline["required_plugins"]:
        require(plugin in plugins, f"{config_name}: plugins must include {plugin}")
    for extension in baseline["required_markdown_extensions"]:
        require(
            extension in extensions,
            f"{config_name}: markdown_extensions must include {extension}",
        )

    validate_effective_assets(config, baseline, config_name)


def validate_root_contract(config: dict, config_name: str) -> None:
    validate_settings(config, config_name, "root")


def validate_shared_contract(
    config: dict,
    canonical_hub_links: list[dict],
    config_name: str,
) -> None:
    shared_bijux = validate_settings(config, config_name, "shared")
    validate_canonical_registry(shared_bijux["hub_links"], canonical_hub_links, config_name)
    validate_mermaid_contract(config, config_name)


if __name__ == "__main__":
    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    shared_cfg = load_yaml(repo_root / "mkdocs.shared.yml")
    root_cfg = load_yaml(repo_root / "mkdocs.yml")
    canonical_hub_links = load_canonical_hub_links(repo_root)
    mkdocs_baseline = load_mkdocs_baseline(repo_root)

    # Shared config defines shell policy; root config defines project identity.
    validate_shared_contract(shared_cfg, canonical_hub_links, "mkdocs.shared.yml")
    validate_root_contract(root_cfg, "mkdocs.yml")
    effective_cfg = merge_mappings(shared_cfg, root_cfg)
    validate_settings(effective_cfg, "effective MkDocs configuration", "effective")
    validate_mkdocs_baseline(
        effective_cfg,
        mkdocs_baseline,
        "effective MkDocs configuration",
    )

    validate_mermaid_contract(effective_cfg, "effective MkDocs configuration", mkdocs_baseline["diagram"])
    validate_diagram_asset(repo_root, mkdocs_baseline)

    print("Bijux docs contract validation passed")
