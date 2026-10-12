#!/usr/bin/env python3
"""Run canonical source capture, reconstruction and Pages bundle admission."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

SHARED = Path(__file__).resolve().parents[2]
EVIDENCE = "artifacts/website-security/"
SOURCE = EVIDENCE + "source-identity.json"
MANIFEST = EVIDENCE + "publication.json"


def arguments(command: str, options: argparse.Namespace, source_sha: str) -> list[str]:
    security = SHARED / "security"
    if command == "capture":
        standard = options.standard_root or os.environ.get("BIJUX_STD_ROOT")
        if not standard:
            raise ValueError("Capture requires the independently fetched accepted BIJUX_STD_ROOT")
        selected = Path(standard)
        if selected.is_absolute():
            try:
                standard = selected.relative_to(Path.cwd().resolve()).as_posix()
            except ValueError as error:
                raise ValueError("Accepted standard must belong to the consumer artifacts directory") from error
        result = [str(security / "build_identity.py"), "capture-source", "--source-sha", source_sha,
                  "--standard-root", standard, "--standard-pin", "publication", "--config", options.config, "--site-dir", options.site_dir,
                  "--site-url", options.site_url, "--build-command", options.build_command,
                  "--verify-command", options.verify_command, "--output", SOURCE]
        if options.source_recipe:
            result.extend(["--source-recipe", options.source_recipe])
        return result
    if command == "render":
        result = [str(security / "render_publication.py"), "--config", options.config,
                  "--site-dir", options.site_dir, "--site-url", options.site_url, "--source-identity", SOURCE]
        for name in ("source_recipe", "reader_owner", "interactive_report_owner"):
            value = getattr(options, name)
            if value:
                result.extend(["--" + name.replace("_", "-"), value])
        return result
    if command == "admit":
        return [str(security / "publication.py"), "admit", "--site-dir", options.site_dir,
                "--site-url", options.site_url, "--source-sha", source_sha, "--source-identity", SOURCE,
                "--build-identity", EVIDENCE + "build-identity.json",
                "--verification-report", EVIDENCE + "site-verification.json",
                "--csp-report", EVIDENCE + "csp.json", "--output", MANIFEST]
    if command == "verify":
        return [str(security / "publication.py"), "verify", "--manifest", MANIFEST, "--require-qualified"]
    raise ValueError("Unknown publication operation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "render", "admit", "verify"):
        selected = commands.add_parser(name)
        if name != "verify":
            selected.add_argument("--site-dir", required=True)
            selected.add_argument("--site-url", required=True)
        if name in {"capture", "render"}:
            selected.add_argument("--config", required=True)
            selected.add_argument("--source-recipe", choices=["masterclass-catalogue"])
        if name == "capture":
            selected.add_argument("--standard-root")
            selected.add_argument("--build-command", required=True)
            selected.add_argument("--verify-command", required=True)
        if name in {"render", "admit"}:
            selected.add_argument("--reader-owner")
            selected.add_argument("--interactive-report-owner")
    options = parser.parse_args()
    try:
        source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        expected_sha = os.environ.get("GITHUB_SHA")
        if expected_sha and expected_sha != source_sha:
            raise ValueError("Publication checkout differs from the dispatched accepted source")
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        if options.command == "admit":
            # Admission requires source checks around the exact route/search artifact.
            # A renderer's successful build receipt alone does not attest that boundary.
            environment.update(DOCS_PYTHON=sys.executable, DOCS_SITE_DIR=options.site_dir,
                               DOCS_BUILD_SITE_URL=options.site_url, DOCS_SOURCE_IDENTITY=SOURCE,
                               BIJUX_DOCS_SITE_REPORT=EVIDENCE + "site-verification.json")
            for key in ("BIJUX_DOCS_READER_OWNER", "BIJUX_DOCS_INTERACTIVE_REPORT_OWNER", "BIJUX_DOCS_READER_SOURCE_SHA"):
                environment.pop(key, None)
            if options.reader_owner and options.interactive_report_owner:
                raise ValueError("Passive and interactive publication owners cannot be mixed")
            if options.interactive_report_owner:
                environment.update(BIJUX_DOCS_INTERACTIVE_REPORT_OWNER=options.interactive_report_owner,
                                   BIJUX_DOCS_READER_SOURCE_SHA=source_sha)
            elif options.reader_owner:
                environment.update(BIJUX_DOCS_READER_OWNER=options.reader_owner, BIJUX_DOCS_READER_SOURCE_SHA=source_sha)
            subprocess.run(["bash", str(SHARED / "tooling/scripts/verify_bijux_docs_site.sh")],
                           env=environment, check=True)
        subprocess.run([sys.executable, *arguments(options.command, options, source_sha)],
                       env=environment, check=True)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("Documentation publication refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
