"""Load one root/version processor closure from captured source, never bytecode."""
import hashlib
import importlib.abc
import importlib.util
import sys


def load_processors(path, captured, prefix):
    if "__init__" not in captured:
        raise ValueError("Owned processors require captured package initialization source")
    fingerprint = b"\0".join(source.name.encode() + b":" + hashlib.sha256(content).digest()
                              for source, content in captured.values())
    namespace = hashlib.sha256(str(path).encode() + b"\0" + fingerprint).hexdigest()
    name = prefix + namespace
    if name not in sys.modules:
        # Only this private package entry recognizes its captured source closure.
        # Absolute entry identity survives ordinary import cache invalidation.
        entry = str(path / ".bijux-captured-processors" / name)
        class CapturedProcessorLoader(importlib.abc.Loader):
            def __init__(self, source, content):
                self.source, self.content = source, content

            def create_module(self, spec):
                return None

            def exec_module(self, module):
                module.__file__ = str(self.source)
                exec(compile(self.content, str(self.source), "exec"), module.__dict__)

        class CapturedProcessorFinder(importlib.abc.PathEntryFinder):
            def find_spec(self, fullname, target=None):
                prefix = name + "."
                if not fullname.startswith(prefix):
                    return None
                owned = fullname[len(prefix):]
                if owned not in captured or "." in owned or owned == "__init__":
                    return None
                source, content = captured[owned]
                return importlib.util.spec_from_loader(fullname, CapturedProcessorLoader(source, content),
                                                      origin=str(source))

        source, content = captured["__init__"]
        spec = importlib.util.spec_from_loader(name, CapturedProcessorLoader(source, content),
                                              origin=str(source), is_package=True)
        spec.submodule_search_locations = [entry]
        module = importlib.util.module_from_spec(spec)
        sys.path_importer_cache[entry] = CapturedProcessorFinder()
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            sys.path_importer_cache.pop(entry, None)
            raise
    return importlib.import_module(name + ".integration")
