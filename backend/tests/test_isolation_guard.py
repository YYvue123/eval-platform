"""Tests for assert_isolated_database — tests must never use the business DB."""
from __future__ import annotations

from tests import isolated_env

import unittest
from pathlib import Path

assert_isolated_database = isolated_env.assert_isolated_database
_ROOT = isolated_env._ROOT


class TestIsolationGuard(unittest.TestCase):
    def test_accepts_isolated_sqlite_path(self) -> None:
        db = _ROOT / "guard.db"
        url = "sqlite+aiosqlite:///" + db.as_posix()
        result = assert_isolated_database(url)
        self.assertEqual(result.resolve(), db.resolve())

    def test_accepts_three_slash_relative_url_under_isolated_root(self) -> None:
        url = "sqlite+aiosqlite:///tests/_isolated/relative.db"
        result = assert_isolated_database(url)
        self.assertEqual(result.resolve(), (_ROOT / "relative.db").resolve())

    def test_rejects_business_db_relative_url(self) -> None:
        with self.assertRaises(RuntimeError):
            assert_isolated_database("sqlite+aiosqlite:///../eval_platform.db")

    def test_rejects_non_sqlite_url(self) -> None:
        with self.assertRaises(RuntimeError):
            assert_isolated_database("postgresql+asyncpg://localhost/eval")


if __name__ == "__main__":
    unittest.main()
