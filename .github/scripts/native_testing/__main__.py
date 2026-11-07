"""Invoke native test verification without loading ambient packages."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native_testing.execution import main
raise SystemExit(main())
