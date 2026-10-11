"""Execute the finite workflow policy package from captured owning source bytes."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


MODULE_ORDER = ("source_loading", "schema", "yaml_io", "events", "refs", "dependency_prs", "publication",
                "canonical_sources", "source_authority", "verification")


def load_script(path: Path, name: str) -> ModuleType:
    """Execute an explicitly selected owning script from its captured current bytes."""
    path = path.resolve()
    source = path.read_bytes()
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def load_package(bootstrap_source: bytes) -> ModuleType:
    """Bind one package to its resolved source and bypass timestamp bytecode caches."""
    directory = Path(__file__).resolve().parent
    sources = {name + ".py": (directory / (name + ".py")).read_bytes()
               for name in MODULE_ORDER if name != "source_loading"}
    sources["source_loading.py"] = bootstrap_source
    sources["__init__.py"] = (directory / "__init__.py").read_bytes()
    identity = hashlib.sha256(str(directory).encode())
    for filename in sorted(sources):
        identity.update(filename.encode() + b"\0" + sources[filename])
    namespace = "bijux_workflow_execution_" + identity.hexdigest()
    # Compile the same captured bytes used for identity before exposing any module.
    compiled = {filename: compile(source, str(directory / filename), "exec")
                for filename, source in sources.items()}
    for cached_name in tuple(sys.modules):
        if cached_name == namespace or cached_name.startswith(namespace + "."):
            del sys.modules[cached_name]
    package = ModuleType(namespace)
    package.__file__ = str(directory / "__init__.py")
    package.__package__ = namespace
    package.__path__ = [str(directory)]
    package.__spec__ = importlib.util.spec_from_file_location(
        namespace, package.__file__, submodule_search_locations=package.__path__
    )
    sys.modules[namespace] = package
    try:
        for name in MODULE_ORDER:
            qualified_name = namespace + "." + name
            module = ModuleType(qualified_name)
            module.__file__ = str(directory / (name + ".py"))
            module.__package__ = namespace
            module.__spec__ = importlib.util.spec_from_file_location(qualified_name, module.__file__)
            sys.modules[qualified_name] = module
            exec(compiled[name + ".py"], module.__dict__)
            setattr(package, name, module)
        exec(compiled["__init__.py"], package.__dict__)
    except BaseException:
        for loaded_name in tuple(sys.modules):
            if loaded_name == namespace or loaded_name.startswith(namespace + "."):
                del sys.modules[loaded_name]
        raise
    return package
