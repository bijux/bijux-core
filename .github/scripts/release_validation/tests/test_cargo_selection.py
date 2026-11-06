"""Prove Cargo partition selection retains unified features and colliding target names."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class CargoSelectionTests(unittest.TestCase):
    def test_workspace_selectors_preserve_feature_unification_and_duplicate_names(self):
        artifacts = ROOT / 'artifacts/release-validation-parallelism/cargo-controls'
        artifacts.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=artifacts) as folder:
            root = Path(folder)
            (root / 'Cargo.toml').write_text('[workspace]\nmembers=["foundation","consumer","observer"]\nresolver="2"\n')
            for name in ('foundation', 'consumer', 'observer'):
                package = root / name;(package / 'src').mkdir(parents=True)
                manifest = f'[package]\nname="{name}"\nversion="0.1.0"\nedition="2021"\n'
                if name == 'foundation':
                    manifest += '[features]\nwide=[]\n'
                    (package / 'src/lib.rs').write_text('pub const WIDE: bool = cfg!(feature="wide");\n')
                else:
                    manifest += '[dependencies]\nfoundation={path="../foundation"}\n'
                    (package / 'src/lib.rs').write_text('pub fn selected() {}\n')
                    (package / 'tests').mkdir()
                    (package / 'tests/scoped.rs').write_text('#[test]\nfn unified_workspace_feature() { assert!(foundation::WIDE); }\n')
                (package / 'Cargo.toml').write_text(manifest)
            environment = dict(os.environ, CARGO_TARGET_DIR=str(root / 'target'), CARGO_HOME=str(root / 'cargo-home'),
                               CARGO_INCREMENTAL='0')
            def run(*arguments):
                return subprocess.run(['cargo', *arguments], cwd=root, env=environment,
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(run('generate-lockfile', '--offline').returncode, 0)
            complete = run('test', '--workspace', '--all-features', '--test', 'scoped', '--offline', '--locked')
            self.assertEqual(complete.returncode, 0, complete.stderr)
            self.assertEqual(complete.stdout.count('1 passed; 0 failed'), 2)
            weakened = run('test', '-p', 'consumer', '--all-features', '--test', 'scoped', '--offline', '--locked')
            self.assertNotEqual(weakened.returncode, 0)
            self.assertIn('foundation::WIDE', weakened.stdout)


if __name__ == '__main__':
    unittest.main()
