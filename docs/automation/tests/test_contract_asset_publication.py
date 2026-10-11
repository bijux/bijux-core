from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "publish_contract_assets.py"
SPEC = importlib.util.spec_from_file_location("bijux_contract_asset_publication", SOURCE)
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)


class ContractSourceRoutingTests(unittest.TestCase):
    def test_valid_parent_link_and_fragment_stay_in_docs(self):
        self.assertEqual(
            publication._source_target("core/interfaces/page.md", "../guide.md#usage"),
            ("core/guide.md", "usage"),
        )

    def test_root_link_is_normalized_inside_docs(self):
        self.assertEqual(
            publication._source_target("core/page.md", "/guide/../index.md#home"),
            ("index.md", "home"),
        )

    def test_traversal_never_inspects_filesystem(self):
        config = {"repo_url": "https://github.com/bijux/bijux-core"}
        for target in (
            "../../SECURITY.md",
            "/../SECURITY.md",
            "../%2e%2e/SECURITY.md",
            "../../",
        ):
            with self.subTest(target=target), patch.object(
                publication.Path, "is_file", side_effect=AssertionError("outside inspection")
            ):
                self.assertIsNone(publication._source_target("core/page.md", target))
                self.assertEqual(
                    publication._published_target(config, "core/page.md", target, set()),
                    target,
                )

    def test_controls_and_backslashes_are_not_source_paths(self):
        for target in (
            "guide\\page.md",
            "guide%5cpage.md",
            "guide\n.md",
            "guide%0a.md",
            "guide\x7f.md",
            "guide%7f.md",
        ):
            with self.subTest(target=target):
                self.assertIsNone(publication._source_target("core/page.md", target))

    def test_external_and_malformed_urls_are_not_source_paths(self):
        for target in ("https://example.org/guide.md", "//example.org/guide.md", "https://[invalid"):
            with self.subTest(target=target):
                self.assertIsNone(publication._source_target("core/page.md", target))

    def test_published_markdown_link_remains_local(self):
        config = {"repo_url": "https://github.com/bijux/bijux-core"}
        self.assertEqual(
            publication._published_target(config, "core/page.md", "guide.md#usage", {"core/guide.md"}),
            "guide.md#usage",
        )

    def test_unpublished_owned_document_routes_to_github(self):
        config = {"repo_url": "https://github.com/bijux/bijux-core", "edit_uri": "edit/main/docs/"}
        with patch.object(publication.Path, "is_file", return_value=True):
            self.assertEqual(
                publication._published_target(config, "core/page.md", "guide.md#usage", set()),
                "https://github.com/bijux/bijux-core/blob/main/docs/core/guide.md#usage",
            )

    def test_published_html_link_preserves_relative_site_routing(self):
        self.assertEqual(
            publication._published_html_target({}, "core/page.md", "guide.md#usage", {"core/guide.md"}),
            "../guide/#usage",
        )


if __name__ == "__main__":
    unittest.main()
