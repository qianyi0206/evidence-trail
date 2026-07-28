from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from download_docs import (
    SOURCES,
    preserve_document_policy,
    validate_download_url,
)


class DownloadSecurityTests(unittest.TestCase):
    def test_all_managed_sources_have_pinned_sha256(self) -> None:
        self.assertTrue(SOURCES)
        for source in SOURCES:
            self.assertRegex(source.sha256, r"^[0-9a-f]{64}$")

    def test_http_download_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-HTTPS"):
            validate_download_url("http://documents.un.org/example.pdf")

    def test_non_official_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-official"):
            validate_download_url("https://example.com/document.pdf")

    def test_disabled_policy_survives_content_refresh(self) -> None:
        record = {"source_id": "example", "sha256": "new"}
        preserve_document_policy(record, {"enabled": False, "sha256": "old"})
        self.assertIs(record["enabled"], False)


if __name__ == "__main__":
    unittest.main()
