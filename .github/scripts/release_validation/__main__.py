"""Invoke the repository-owned release verification adapter."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from release_validation.execution import main

raise SystemExit(main())
