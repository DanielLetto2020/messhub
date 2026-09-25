"""Номер версии: 1.0.<номер коммита с нуля>; в пакете — из файла VERSION."""
import re
import unittest
from unittest import mock

import common  # noqa: F401 — пути программы во временной папке
import version


class VersionTest(unittest.TestCase):
    def test_format(self):
        self.assertRegex(version.__version__, r"^1\.0\.\d+(\+unknown)?$")

    def test_git_count(self):
        with mock.patch.object(version.subprocess, "run") as run:
            run.side_effect = [mock.Mock(stdout=version.ROOT + "\n"), mock.Mock(stdout="42\n")]
            self.assertEqual(version._from_git(), "1.0.41")          # 42 коммита → 1.0.41
            run.side_effect = [mock.Mock(stdout=version.ROOT + "\n"), mock.Mock(stdout="42\n")]
            self.assertEqual(version.next_version(), "1.0.42")

    def test_foreign_repo_ignored(self):
        with mock.patch.object(version.subprocess, "run", return_value=mock.Mock(stdout="/some/other/repo\n")):
            self.assertIsNone(version._from_git())

    def test_stamp_wins(self):
        m = mock.mock_open(read_data="1.0.77\n")
        with mock.patch("builtins.open", m):
            self.assertEqual(version._stamped(), "1.0.77")
        self.assertTrue(re.match(r"^\d+\.\d+$", version.SERIES))


if __name__ == "__main__":
    unittest.main()
