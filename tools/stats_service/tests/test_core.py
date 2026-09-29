from unittest import TestCase

from tools.stats_service.core import compute_stats, parse_measurements


class StatsCoreTest(TestCase):
    def test_rejects_parse_non_finite_decimal(self):
        with self.assertRaisesRegex(ValueError, "有限"):
            parse_measurements("9" * 400 + " m")

    def test_parse_then_compute_length(self):
        values = parse_measurements("样本为 100 cm、2 m 和 500 mm")
        result = compute_stats(values, "m")
        self.assertEqual(result["converted"], [1.0, 2.0, 0.5])
        self.assertEqual(result["count"], 3)
        self.assertAlmostEqual(result["mean"], 3.5 / 3)
        self.assertEqual(result["dimension"], "length")

    def test_population_variance(self):
        result = compute_stats(
            [{"value": 1, "unit": "m"}, {"value": 3, "unit": "m"}], "m"
        )
        self.assertEqual(result["variance"], 1.0)

    def test_rejects_mixed_dimensions(self):
        with self.assertRaisesRegex(ValueError, "量纲"):
            compute_stats(
                [{"value": 1, "unit": "m"}, {"value": 1, "unit": "kg"}]
            )

    def test_rejects_non_finite_values(self):
        with self.assertRaisesRegex(ValueError, "有限"):
            compute_stats([{"value": float("nan"), "unit": "m"}])

    def test_rejects_infinity_input(self):
        with self.assertRaisesRegex(ValueError, "有限"):
            compute_stats([{"value": float("inf"), "unit": "m"}])

    def test_rejects_conversion_overflow(self):
        with self.assertRaisesRegex(ValueError, "有限"):
            compute_stats([{"value": 1e308, "unit": "km"}], "mm")

    def test_rejects_empty_values(self):
        with self.assertRaises(ValueError):
            compute_stats([])

    def test_rejects_unknown_unit(self):
        with self.assertRaises(ValueError):
            compute_stats([{"value": 1, "unit": "xyz"}])

    def test_rejects_target_unit_dimension_mismatch(self):
        with self.assertRaisesRegex(ValueError, "量纲"):
            compute_stats([{"value": 1, "unit": "m"}], "kg")
