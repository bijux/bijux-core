from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(os.environ.get("BIJUX_DOCS_NAVIGATION_MODULE", Path(__file__).resolve().parents[1] / "navigation_sanity.py"))
spec = importlib.util.spec_from_file_location("bijux_core_navigation_sanity", SOURCE)
navigation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(navigation)


class NavigationContextTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("BIJUX_DOCS_TEST_ARTIFACTS", Path.cwd() / "artifacts/docs-navigation-tests"))
        root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.directory.cleanup)
        self.page = Path(self.directory.name) / "index.html"

    def validate(self, html):
        self.page.write_text(html, encoding="utf-8")
        return navigation.validate_file(self.page)

    def test_exact_current_page_is_accepted(self):
        self.assertEqual(self.validate('<a data-bijux-site-path="/" aria-current="page" href="./">Home</a>'), [])

    def test_current_parent_location_is_accepted(self):
        self.assertEqual(self.validate('<a data-bijux-site-path="/bijux-cli/" aria-current="location" href="../../">CLI Handbook</a>'), [])

    def test_two_current_context_owners_are_rejected(self):
        issues = self.validate('<a data-bijux-site-path="/" aria-current="page">Home</a><a data-bijux-site-path="/bijux-cli/" aria-current="location">CLI</a>')
        self.assertTrue(any('found 2' in issue for issue in issues))

    def test_missing_current_owner_is_rejected(self):
        self.assertTrue(any('found 0' in issue for issue in self.validate('<a data-bijux-site-path="/">Home</a>')))

    def test_unsupported_current_token_does_not_count(self):
        for token in ('true', 'false', 'step', 'date'):
            with self.subTest(token=token):
                self.assertTrue(any('found 0' in issue for issue in self.validate(f'<a data-bijux-site-path="/" aria-current="{token}">Home</a>')))

    def test_duplicate_inactive_destination_is_still_rejected(self):
        issues = self.validate('<a data-bijux-site-path="/" aria-current="page">Home</a><a data-bijux-site-path="/bijux-cli/">CLI</a><a data-bijux-site-path="/bijux-cli/">CLI</a>')
        self.assertTrue(any('duplicate site-tab path' in issue for issue in issues))

    def test_visible_detail_accepts_current_parent_location(self):
        html = '<div data-bijux-detail-strip><a data-bijux-detail-path="/bijux-cli/interfaces/" aria-current="location">Interfaces</a></div>'
        self.assertEqual(self.validate(html), [])

    def test_visible_course_accepts_current_parent_location(self):
        html = '<div data-bijux-course-strip><a data-bijux-course-path="/course/" aria-current="location">Course</a></div>'
        self.assertEqual(self.validate(html), [])

    def test_visible_detail_missing_owner_is_rejected(self):
        self.assertTrue(any('found 0' in issue for issue in self.validate('<div data-bijux-detail-strip><a data-bijux-detail-path="/bijux-cli/">CLI</a></div>')))

    def test_hidden_detail_retains_existing_no_current_requirement(self):
        self.assertEqual(self.validate('<div data-bijux-detail-strip hidden><a data-bijux-detail-path="/bijux-cli/">CLI</a></div>'), [])

    def test_missing_actual_local_link_is_still_rejected(self):
        self.page.write_text('<a href="missing/">Missing</a>', encoding='utf-8')
        self.assertTrue(any('no published target' in issue for issue in navigation.validate_local_links(self.page.parent, 'https://bijux.io/bijux-core/')))


if __name__ == "__main__":
    unittest.main()
