"""Observe physical Python startup/import inputs; never approve a renderer profile."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
import sys
import sysconfig
import types

MAXIMUM_FILES = 200000
MAXIMUM_FILE_BYTES = 256 * 1024 * 1024
VOLATILE_METADATA = {"RECORD", "INSTALLER", "direct_url.json", "REQUESTED"}


class RuntimeObservationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RuntimeObservationError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def file_record(path: Path, relative: str):
    """Bind observed bytes to a stable regular target and its selected link."""
    try:
        selected = path.lstat()
        target = path.resolve(strict=True)
        before = target.stat()
        require(stat.S_ISREG(before.st_mode),
                "Runtime observation requires a regular target: " + relative)
        require(before.st_size <= MAXIMUM_FILE_BYTES,
                "Runtime file exceeds observation limit: " + relative)
        value = hashlib.sha256()
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            require(stat.S_ISREG(opened.st_mode) and
                    (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                    "Runtime target changed before observation: " + relative)
            total = 0
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total += len(chunk)
                require(total <= MAXIMUM_FILE_BYTES,
                        "Runtime file exceeds observation limit: " + relative)
                value.update(chunk)
            completed = os.fstat(stream.fileno())
        after = path.stat()
        current = path.lstat()
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        require(identity(before) == identity(opened) == identity(completed) == identity(after)
                and identity(selected) == identity(current)
                and path.resolve(strict=True) == target,
                "Runtime input or selected target changed during observation: " + relative)
        result = {"path": relative, "bytes": before.st_size, "sha256": value.hexdigest()}
        if stat.S_ISLNK(selected.st_mode):
            result["resolved_target"] = str(target)
        return result
    except (OSError, RuntimeError) as error:
        raise RuntimeObservationError("Runtime target unavailable: " + relative) from error


def inventory(root: Path, *, exclude_site_packages=False):
    require(root.is_dir() and not root.is_symlink(), "Select a regular runtime root")
    records, caches, links = [], [], []
    for directory, directories, names in os.walk(root, followlinks=False):
        current = Path(directory)
        if exclude_site_packages:
            directories[:] = [name for name in directories if name != "site-packages"]
        for name in list(directories):
            path = current / name
            if path.is_symlink():
                # Record unresolved directory inputs explicitly; do not silently
                # traverse another authority or certify complete closure.
                links.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "kind": "directory",
                        "target": os.readlink(path),
                        "target_exists": path.exists(),
                    }
                )
                directories.remove(name)
        for name in names:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                links.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "target": os.readlink(path),
                        "target_exists": path.exists(),
                    }
                )
                if not path.is_file():
                    continue
            if current.name.endswith(".dist-info") and name in VOLATILE_METADATA:
                continue
            record = file_record(path, relative)
            (caches if path.suffix == ".pyc" else records).append(record)
            require(
                len(records) + len(caches) + len(links) <= MAXIMUM_FILES,
                "Runtime observation file limit exceeded",
            )
    records.sort(key=lambda item: item["path"])
    caches.sort(key=lambda item: item["path"])
    links.sort(key=lambda item: item["path"])
    return {
        "files_count": len(records),
        "files_sha256": digest(canonical(records)),
        "files": records,
        "bytecode_count": len(caches),
        "bytecode_sha256": digest(canonical(caches)),
        "bytecode": caches,
        "links": links,
    }


def snapshot(packages, *, roots=None, stdlib=None, executable=None):
    roots = sorted(
        set(
            roots
            if roots is not None
            else (
                Path(sysconfig.get_path(name)).resolve()
                for name in ("purelib", "platlib")
            )
        )
    )
    stdlib = (
        Path(stdlib)
        if stdlib is not None
        else Path(sysconfig.get_path("stdlib")).resolve()
    )
    executable = (
        Path(executable) if executable is not None else Path(sys.executable).resolve()
    )
    executable_record = file_record(executable, "python-executable")
    listed = {item["path"] for package in packages for item in package["files"]}
    physical, startup = [], []
    for index, root in enumerate(roots):
        label = "site-packages:" + str(index)
        values = inventory(root)
        present = {item["path"] for item in values["files"]}
        values.update(
            root=label,
            outside_locked_inventory=sorted(present - listed),
            missing_locked_inventory=sorted(listed - present),
        )
        physical.append(values)
        for record in values["files"]:
            if record["path"].endswith(".pth") or record["path"] in (
                "sitecustomize.py",
                "usercustomize.py",
            ):
                startup.append({"root": label, **record})
    standard = inventory(stdlib, exclude_site_packages=True)
    standard["root"] = "stdlib"
    for record in standard["files"]:
        if record["path"] in ("sitecustomize.py", "usercustomize.py"):
            startup.append({"root": "stdlib", **record})
    known = [
        (root, "site-packages:" + str(index)) for index, root in enumerate(roots)
    ] + [(stdlib, "stdlib")]

    def origin(path):
        path = Path(path).resolve()
        for root, label in known:
            if path.is_relative_to(root):
                return {"root": label, "path": path.relative_to(root).as_posix()}
        return {"root": "outside-observed-runtime", "path": str(path)}

    import_paths = [origin(value or os.getcwd()) for value in sys.path]
    loaded = []
    for name, module in sorted(list(sys.modules.items())):
        file = getattr(module, "__file__", None)
        paths = getattr(module, "__path__", None)
        if file:
            loaded.append({"module": name, "origin": origin(file)})
        elif paths:
            loaded.append(
                {"module": name, "namespace": [origin(path) for path in paths]}
            )
    return {
        "scope": "observed-physical-python-runtime",
        "verification_only": True,
        "admission_created": False,
        "executable": executable_record,
        "stdlib": standard,
        "physical_roots": physical,
        "startup_inputs": sorted(
            startup, key=lambda item: (item["root"], item["path"])
        ),
        "import_paths": import_paths,
        "loaded_modules": loaded,
        "startup_runtime": {
            "customization_modules": [item for item in loaded if item["module"] in
                                      {"sitecustomize", "usercustomize", "apport_python_hook"}],
            "exception_hook_is_interpreter_default": (sys.excepthook is sys.__excepthook__
                and type(sys.excepthook) is types.BuiltinFunctionType
                and sys.excepthook.__self__ is sys and sys.excepthook.__name__ == "excepthook"),
            "exception_hook": {
                "module": getattr(sys.excepthook, "__module__", None),
                "name": getattr(sys.excepthook, "__qualname__", None),
                "origin": origin(sys.excepthook.__code__.co_filename)
                          if hasattr(sys.excepthook, "__code__") else None,
            },
        },
        "limitations": [
            "Observation does not approve a renderer or certify startup behavior.",
            "Directory symlinks are retained as unresolved closure inputs, never silently admitted.",
            "Recorded bytecode is not proof that it matches source or was the executable actually loaded.",
            "Current interpreter and stdlib are observed; dynamic linker libraries and future plugin imports need separate qualification.",
            "Loaded names and file origins do not prove every in-memory callback or namespace is unmodified.",
            "Only this process snapshot is observed; absent consumer plugins/hooks are not admitted.",
        ],
    }
