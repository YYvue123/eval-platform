"""WP00 回归入口：依赖导入与隔离路径冒烟。"""
from __future__ import annotations

import unittest

from tests.test_result_semantics import DependencyRegressionTest, RunnerSemanticsRegressionTest

__all__ = ["DependencyRegressionTest", "RunnerSemanticsRegressionTest"]


if __name__ == "__main__":
    unittest.main()
