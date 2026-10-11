#!/usr/bin/env python3
"""Install a source-approved isolated documentation publication renderer."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys

SHARED = Path(__file__).resolve().parents[2]
RECIPES = {"history-media": ("requirements-media.lock", "linux-media-history-publication"),
           "history": ("requirements.lock", "linux-history-publication"),
           "history-legacy": ("requirements-legacy.lock", "linux-legacy-history-publication")}


def owned_directory(root: Path, name: str) -> Path:
    path = Path(name)
    if name != path.as_posix() or path.is_absolute() or not path.parts or path.parts[0] != "artifacts" or any(part in {".", ".."} for part in path.parts):
        raise ValueError("Publication renderer directory must belong to artifacts")
    selected = root / path
    for item in (selected, *selected.parents):
        if item.is_symlink():
            raise ValueError("Publication renderer directory cannot traverse symlinks")
        if item == root:
            break
    if selected.exists():
        raise ValueError("Publication renderer destination already exists; retain and select a fresh destination")
    return selected


def normalize_local_wheel_metadata(renderer: Path, wheels: Path) -> None:
    """Remove only uv's reviewed, non-executable local-file timestamp cache.

    Wheel source bytes remain unchanged. The installed RECORD is maintained so
    physical inventory continues to bind every remaining input without a clock
    value becoming part of publication producer identity.
    """
    site = renderer.parent.parent / "lib/python3.11/site-packages"
    for distribution, version in (("csscompressor", "0.9.5"), ("jsmin", "3.0.1")):
        wheel = wheels / f"{distribution}-{version}-py3-none-any.whl"
        metadata = site / f"{distribution}-{version}.dist-info"
        cache = metadata / "uv_cache.json"
        record = metadata / "RECORD"
        if any(path.is_symlink() or not path.is_file() for path in (wheel, cache, record)) or metadata.is_symlink():
            raise ValueError("Local wheel cache normalization requires regular owned wheel metadata")
        data = cache.read_bytes()
        timestamp = wheel.stat().st_mtime_ns
        expected = {"timestamp": {"secs_since_epoch": timestamp // 1_000_000_000,
                                  "nanos_since_epoch": timestamp % 1_000_000_000},
                    "commit": None, "tags": None, "env": {}, "directories": {}}
        if json.loads(data) != expected or cache.stat().st_mode & 0o111:
            raise ValueError("Local wheel cache differs from reviewed uv timestamp bookkeeping")
        rows = list(csv.reader(io.StringIO(record.read_text())))
        relative = cache.relative_to(site).as_posix()
        digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        selected = [row for row in rows if row and row[0] == relative]
        if selected != [[relative, digest, str(len(data))]]:
            raise ValueError("Local wheel cache requires its exact installed RECORD identity")
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(row for row in rows if row[0] != relative)
        record.write_text(output.getvalue())
        cache.unlink()


def install(root: Path, recipe: str, python: str, name: str) -> Path:
    lock_name, expected_profile = RECIPES[recipe]
    lock = SHARED / "security/runtime" / lock_name
    if not lock.is_file() or lock.is_symlink():
        raise ValueError("Source-owned publication dependency lock required")
    destination = owned_directory(root, name)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                       UV_PYTHON_DOWNLOADS="never", UV_CACHE_DIR=str(root / "artifacts/docs/publication/cache"))
    probe = subprocess.check_output([python, "-c", "import json,platform,sys; print(json.dumps([platform.system(),platform.machine(),platform.python_version(),sys.implementation.name]))"], env=environment, text=True)
    if json.loads(probe) != ["Linux", "x86_64", "3.11.17", "cpython"]:
        raise ValueError("Publication renderer requires the reviewed Linux x86_64 CPython 3.11.17 runtime")
    installer_version = subprocess.check_output(["uv", "--version"], text=True).strip()
    if not re.fullmatch(r"uv 0\.11\.17(?: \([A-Za-z0-9._ -]+\))?", installer_version):
        raise ValueError("Publication renderer requires uv 0.11.17")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([python, "-m", "venv", "--without-pip", str(destination)], env=environment, check=True)
    renderer = destination / "bin/python"
    wheels = []
    if recipe == "history-media":
        wheel_root = destination.parent / (destination.name + "-wheels")
        subprocess.run([python, str(SHARED / "tooling/security/build_publication_wheels.py"),
                        "--python", python, "--directory", wheel_root.relative_to(root).as_posix()],
                       cwd=root, env=environment, check=True)
        wheels = ["--find-links", str(wheel_root / "wheels")]
    subprocess.run(["uv", "pip", "install", "--python", str(renderer), "--require-hashes", "--no-deps",
                    "--only-binary", ":all:", *wheels, "--requirement", str(lock)], env=environment, check=True)
    if recipe == "history-media":
        normalize_local_wheel_metadata(renderer, wheel_root / "wheels")
    subprocess.run(["uv", "pip", "check", "--python", str(renderer)], env=environment, check=True)
    # Installing reviewed wheel bytes does not create admission. The actual
    # interpreter, stdlib, startup, physical package and import closure must match.
    program = """import importlib.util,json,sys
from pathlib import Path
shared=Path(sys.argv[1]); root=Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('bijux_publication_profiles',shared/'security/renderer_profiles.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
selected=module.select(shared,root,publication=True)
if selected['profile_id']!=sys.argv[3]: raise ValueError('Publication renderer selected another source-owned recipe')
print(json.dumps(selected,indent=2))
"""
    accepted = subprocess.check_output([str(renderer), "-c", program, str(SHARED), str(root), expected_profile],
                                       cwd=root, env=environment, text=True)
    (destination.parent / (destination.name + "-admission.json")).write_text(accepted)
    print(renderer)
    return renderer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, choices=sorted(RECIPES))
    parser.add_argument("--python", required=True)
    parser.add_argument("--directory", default="artifacts/docs/publication/python")
    arguments = parser.parse_args()
    try:
        install(Path.cwd().resolve(), arguments.recipe, arguments.python, arguments.directory)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Publication renderer installation refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
