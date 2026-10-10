from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest

from bijux_cli_py import check_python_runtime_supported

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_pyproject() -> dict[str, object]:
    pyproject = _project_root() / "pyproject.toml"
    return tomllib.loads(pyproject.read_text(encoding="utf-8"))


def _load_cargo_manifest() -> dict[str, object]:
    manifest = _project_root() / "Cargo.toml"
    return tomllib.loads(manifest.read_text(encoding="utf-8"))


def _load_package_readme() -> str:
    return _project_root().joinpath("README.md").read_text(encoding="utf-8")


def _runtime_binary() -> str:
    override = os.environ.get("BIJUX_BIN")
    if override:
        return override

    workspace_root = _project_root().parents[1]
    runtime_names = ("bijux.exe", "bijux") if os.name == "nt" else ("bijux",)
    workspace_candidates: list[Path] = []
    for base in (
        workspace_root / "artifacts" / "rust" / "target" / "debug",
        workspace_root / "artifacts" / "rust" / "target" / "release",
        workspace_root / "target" / "debug",
        workspace_root / "target" / "release",
    ):
        for runtime_name in runtime_names:
            workspace_candidates.append(base / runtime_name)
    for candidate in workspace_candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    for name in runtime_names:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    raise RuntimeError("bijux runtime binary not found")


def test_script_entrypoint_name_and_target_are_stable() -> None:
    pyproject = _load_pyproject()
    scripts = pyproject["project"]["scripts"]
    assert scripts == {"bijux": "bijux_cli_py.cli:main"}


def test_maturin_module_name_matches_package_layout() -> None:
    pyproject = _load_pyproject()
    module_name = pyproject["tool"]["maturin"]["module-name"]
    assert module_name == "bijux_cli_py._native"


def test_python_dash_m_and_binary_help_parity() -> None:
    runtime = _runtime_binary()
    direct = subprocess.run([runtime, "--help"], capture_output=True, text=True, check=False)
    env = os.environ.copy()
    package_root = _project_root() / "python"
    env["PYTHONPATH"] = str(package_root)
    module = subprocess.run(
        [sys.executable, "-m", "bijux_cli_py", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert direct.returncode == module.returncode
    assert direct.stdout.strip() == module.stdout.strip()


def test_project_metadata_is_consistent_for_wheel_builds() -> None:
    pyproject = _load_pyproject()
    project = pyproject["project"]
    assert project["name"] == "bijux-cli"
    assert "version" not in project
    assert "version" in project["dynamic"]
    assert project["readme"]["content-type"] == "text/markdown"
    assert project["readme"]["file"] == "README.md"
    assert project["requires-python"] == ">=3.11"
    assert (
        project["description"]
        == "Python package for installing and launching the Bijux command runtime for automation, plugins, and interactive workflows"
    )
    authors = project["authors"]
    assert authors == [{"name": "Bijan Mousavi", "email": "bijan@bijux.io"}]
    maintainers = project["maintainers"]
    assert maintainers == [{"name": "Bijan Mousavi", "email": "bijan@bijux.io"}]
    keywords = set(project["keywords"])
    assert {"bijux", "cli", "python", "automation", "plugins", "interactive"} <= keywords
    classifiers = set(project["classifiers"])
    assert "Operating System :: POSIX :: Linux" in classifiers
    assert "Operating System :: MacOS :: MacOS X" in classifiers
    assert "Programming Language :: Python :: 3.14" in classifiers
    assert "Framework :: Pytest" not in classifiers


def test_python_package_readme_describes_package_scope() -> None:
    package_readme = _load_package_readme()
    assert "# bijux-cli Python Package" in package_readme
    assert "Python distribution for installing and launching the Bijux" in package_readme
    assert "crates/bijux-cli-python/CHANGELOG.md" in package_readme


def test_native_extension_uses_abi3_for_supported_python_range() -> None:
    manifest = _load_cargo_manifest()
    pyo3 = manifest["dependencies"]["pyo3"]
    features = set(pyo3["features"])
    assert "abi3-py311" in features
    assert "extension-module" not in features


def test_source_distribution_supports_metadata_generation_from_the_published_layout() -> None:
    if importlib.util.find_spec("build") is None:
        pytest.skip("python build module is not installed in the active interpreter")

    project_root = _project_root()
    with tempfile.TemporaryDirectory() as temp_dir:
        build_env = os.environ.copy()
        build_env["PATH"] = os.pathsep.join(
            [str(Path(sys.executable).parent), build_env.get("PATH", "")]
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--sdist",
                "--no-isolation",
                "--outdir",
                temp_dir,
                str(project_root),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=build_env,
        )

        assert result.returncode == 0, result.stderr or result.stdout

        sdist_path = next(Path(temp_dir).glob("bijux_cli-*.tar.gz"))
        metadata_dir = Path(temp_dir) / "dist-info"
        extracted_dir = Path(temp_dir) / "extracted"
        extracted_dir.mkdir()
        subprocess.run(
            ["tar", "-xzf", str(sdist_path), "-C", str(extracted_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        sdist_root = next(extracted_dir.iterdir())
        assert (sdist_root / "README.md").read_text(encoding="utf-8") == _load_package_readme()
        maturin_bin = Path(sys.executable).with_name("maturin")
        metadata = subprocess.run(
            [
                str(maturin_bin),
                "pep517",
                "write-dist-info",
                "--metadata-directory",
                str(metadata_dir),
                "--interpreter",
                sys.executable,
            ],
            cwd=sdist_root,
            capture_output=True,
            text=True,
            check=False,
        )

        assert metadata.returncode == 0, metadata.stderr or metadata.stdout


def test_optional_dependency_groups_match_current_repo_workflows() -> None:
    pyproject = _load_pyproject()
    optional = pyproject["project"]["optional-dependencies"]

    assert set(optional) == {"build", "docs", "lint", "security", "test"}

    assert optional["test"] == [
        "pytest>=9.0.3,<10.0",
        "pytest-cov>=6.2.1,<7.0",
        "pytest-timeout>=2.4.0,<3.0",
    ]
    assert optional["lint"] == ["ruff>=0.6.8,<1.0"]
    assert optional["security"] == [
        "bandit>=1.7.10,<2.0",
        "pip-audit>=2.7.3,<3.0",
    ]
    assert optional["docs"] == [
        "mkdocs>=1.6.1,<2.0",
        "mkdocs-autorefs>=1.4.4,<2.0",
        "mkdocs-git-revision-date-localized-plugin>=1.5.3,<2.0",
        "mkdocs-glightbox>=0.3,<1.0",
        "mkdocs-include-markdown-plugin>=7.2.1,<8.0",
        "mkdocs-material[imaging]>=9.7.5,<10.0",
        "mkdocs-minify-plugin>=0.7,<1.0",
        "mkdocs-redirects>=1.2,<2.0",
    ]
    assert optional["build"] == [
        "build>=1.4.0,<2.0",
        "twine>=6.1.0,<8.0",
        "maturin>=1.9.4,<2.0",
    ]


def test_optional_dependencies_drop_legacy_python_only_tooling() -> None:
    pyproject = _load_pyproject()
    optional = pyproject["project"]["optional-dependencies"]
    flattened = {dep.split(">=", 1)[0].split("[", 1)[0] for deps in optional.values() for dep in deps}

    for legacy in {
        "commitizen",
        "deptry",
        "hypothesis",
        "hypothesis-jsonschema",
        "interrogate",
        "mkdocs-gen-files",
        "mkdocs-literate-nav",
        "mkdocstrings",
        "mypy",
        "mutmut",
        "pexpect",
        "pydocstyle",
        "pytest-asyncio",
        "pytest-benchmark",
        "pytest-mock",
        "pytest-rerunfailures",
        "radon",
        "vulture",
        "codespell",
    }:
        assert legacy not in flattened

    assert any(
        dep.startswith("mkdocs-material[imaging]")
        for dep in pyproject["project"]["optional-dependencies"]["docs"]
    )


def test_project_urls_expose_python_and_rust_runtime_surfaces() -> None:
    pyproject = _load_pyproject()
    urls = pyproject["project"]["urls"]

    assert urls == {
        "Homepage": "https://bijux.io/bijux-core/bijux-cli/",
        "Repository": "https://github.com/bijux/bijux-core",
        "Issues": "https://github.com/bijux/bijux-core/issues",
        "Documentation": "https://bijux.io/bijux-core/bijux-cli/",
        "Changelog": "https://github.com/bijux/bijux-core/blob/main/crates/bijux-cli-python/CHANGELOG.md",
        "Security": "https://github.com/bijux/bijux-core/security/policy",
        "Discussions": "https://github.com/bijux/bijux-core/discussions",
        "Rust Runtime Crate": "https://crates.io/crates/bijux-cli",
        "Rust Runtime Docs": "https://docs.rs/bijux-cli",
    }


def test_maturin_sdist_includes_core_release_documents() -> None:
    pyproject = _load_pyproject()
    include = pyproject["tool"]["maturin"]["include"]
    include_paths = {(entry["path"], entry["format"]) for entry in include}
    assert ("README.md", "sdist") in include_paths
    assert ("CHANGELOG.md", "sdist") in include_paths
    assert ("LICENSE", "sdist") in include_paths
    assert ("NOTICE", "sdist") in include_paths


def test_runtime_support_helper_matches_python_requirement_floor() -> None:
    pyproject = _load_pyproject()
    assert pyproject["project"]["requires-python"] == ">=3.11"
    assert check_python_runtime_supported((3, 11))
    assert not check_python_runtime_supported((3, 10))
