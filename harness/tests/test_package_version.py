from importlib import metadata
import io
import re
import unittest
from contextlib import redirect_stdout

import reg_harness
from reg_harness import cli


class PackageVersionTests(unittest.TestCase):
    def test_distribution_and_runtime_versions_match(self) -> None:
        try:
            installed_version = metadata.version("reg-harness")
        except metadata.PackageNotFoundError:
            self.skipTest("distribution metadata is checked after installation in CI")
        self.assertEqual(installed_version, reg_harness.__version__)

    def test_runtime_version_is_semantic(self) -> None:
        self.assertRegex(reg_harness.__version__, re.compile(r"^\d+\.\d+\.\d+$"))

    def test_cli_version_uses_the_same_version(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            cli.main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertTrue(
            stdout.getvalue().strip().endswith(f" {reg_harness.__version__}")
        )


if __name__ == "__main__":
    unittest.main()
