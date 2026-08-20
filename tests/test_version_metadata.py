from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = PROJECT_ROOT / "flipbook_version.py"
SPEC = importlib.util.spec_from_file_location("flipbook_version_for_tests", VERSION_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load version module from {VERSION_PATH}")
VERSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERSION)


class VersionMetadataTests(unittest.TestCase):
    def test_version_formats_are_consistent(self) -> None:
        self.assertRegex(VERSION.APP_VERSION, r"^\d+\.\d+$")
        self.assertEqual(VERSION.APP_VERSION_TAG, f"v{VERSION.APP_VERSION}")
        self.assertEqual(VERSION.APP_SEMVER, f"{VERSION.APP_VERSION}.0")

    def test_desktop_web_and_documents_use_the_same_version(self) -> None:
        package = json.loads(
            (PROJECT_ROOT / "web" / "package.json").read_text(encoding="utf-8")
        )
        package_lock = json.loads(
            (PROJECT_ROOT / "web" / "package-lock.json").read_text(encoding="utf-8")
        )
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        handoff = (PROJECT_ROOT / "HANDOFF.md").read_text(encoding="utf-8")

        self.assertEqual(package["version"], VERSION.APP_SEMVER)
        self.assertEqual(package_lock["version"], VERSION.APP_SEMVER)
        self.assertEqual(
            package_lock["packages"][""]["version"], VERSION.APP_SEMVER
        )
        self.assertIn(f"目前版本：**{VERSION.APP_VERSION_TAG}**", readme)
        self.assertIn(
            f"目前產品版本：**{VERSION.APP_VERSION_TAG}**", handoff
        )


if __name__ == "__main__":
    unittest.main()
