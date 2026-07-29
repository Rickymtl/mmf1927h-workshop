"""Unit tests for cleaning.impute — missing-data policy (#12)."""

import sys
import unittest
from pathlib import Path

# Allow running from repo root.
_code_dir = Path(__file__).resolve().parent.parent / "code"
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

import pandas as pd

from cleaning.impute import (
    _is_structural_zero,
    _STRUCTURAL_STARTS,
    apply_price_policy,
    apply_trends_policy,
    apply_gdelt_policy,
    build_imputation_report,
)


class TestStructuralZero(unittest.TestCase):
    def test_ceg_before_listing(self):
        self.assertTrue(_is_structural_zero("CEG", pd.Timestamp("2021-08-01")))

    def test_ceg_after_listing(self):
        self.assertFalse(_is_structural_zero("CEG", pd.Timestamp("2022-01-20")))

    def test_non_structural_ticker(self):
        self.assertFalse(_is_structural_zero("AAPL", pd.Timestamp("2021-08-01")))


class TestPricePolicy(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            {
                "date": ["2021-08-02", "2021-08-03", "2022-01-19", "2022-01-20"],
                "ticker": ["AAPL", "AAPL", "CEG", "CEG"],
                "daily_return": [None, 0.01, None, 0.02],
            }
        )

    def test_returns_dataframe_shape(self):
        out, _ = apply_price_policy(self.df)
        self.assertEqual(len(out), 4)
        self.assertIn("daily_return", out.columns)

    def test_first_row_nan_preserved(self):
        out, _ = apply_price_policy(self.df)
        self.assertTrue(pd.isna(out.loc[0, "daily_return"]))

    def test_ceg_first_row_nan(self):
        out, _ = apply_price_policy(self.df)
        self.assertTrue(pd.isna(out.loc[2, "daily_return"]))

    def test_ceg_prelisting_ensured_nan(self):
        df = pd.DataFrame(
            {
                "date": ["2021-09-01"],
                "ticker": ["CEG"],
                "daily_return": [0.05],
            }
        )
        out, _ = apply_price_policy(df)
        self.assertTrue(pd.isna(out.loc[0, "daily_return"]))

    def test_report_keys(self):
        _, report = apply_price_policy(self.df)
        for key in ["source", "mechanism", "method", "max_gap"]:
            self.assertIn(key, report)


class TestTrendsPolicy(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            {
                "date": [
                    "2021-08-01",  # CEG pre-listing zero
                    "2022-01-19",  # AAPL genuine zero
                    "2022-01-20",  # AAPL normal
                    "2022-01-19",  # CEG post-listing zero
                    "2022-01-20",  # CEG post-listing normal
                ],
                "ticker": ["CEG", "AAPL", "AAPL", "CEG", "CEG"],
                "search_interest_rescaled": [0.0, 0.0, 1.5, 0.0, 2.0],
            }
        )

    def test_structural_zero_recoded_to_nan(self):
        out, _ = apply_trends_policy(self.df)
        self.assertTrue(pd.isna(out.loc[0, "search_interest_rescaled"]))

    def test_genuine_zero_preserved(self):
        out, _ = apply_trends_policy(self.df)
        self.assertEqual(out.loc[1, "search_interest_rescaled"], 0.0)

    def test_post_listing_zero_preserved(self):
        out, _ = apply_trends_policy(self.df)
        self.assertEqual(out.loc[3, "search_interest_rescaled"], 0.0)

    def test_no_recode_flag(self):
        out, _ = apply_trends_policy(self.df, recode_structural_zeros=False)
        self.assertEqual(out.loc[0, "search_interest_rescaled"], 0.0)

    def test_report_caveat(self):
        _, report = apply_trends_policy(self.df)
        self.assertIn("caveat", report)
        self.assertIn("modeling assumption", report["caveat"])


class TestGdeltPolicy(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            {
                "date": ["2021-08-02", "2021-08-03"],
                "ticker": ["AAPL", "AAPL"],
                "tone": [1.5, None],
                "volume": [10, None],
            }
        )

    def test_zero_method_fills_nan(self):
        out, _ = apply_gdelt_policy(self.df, method="zero")
        self.assertEqual(out.loc[1, "tone"], 0.0)
        self.assertEqual(out.loc[1, "volume"], 0)

    def test_nan_method_leaves_nan(self):
        out, _ = apply_gdelt_policy(self.df, method="nan")
        self.assertTrue(pd.isna(out.loc[1, "tone"]))

    def test_invalid_method_raises(self):
        with self.assertRaises(ValueError):
            apply_gdelt_policy(self.df, method="forward_fill")


class TestImputationReport(unittest.TestCase):
    def test_combines_sources(self):
        dummy = {"source": "test"}
        combined = build_imputation_report(dummy, dummy, dummy)
        self.assertTrue(combined["rubin_taxonomy_applied"])
        self.assertIn("prices", combined["sources"])
        self.assertIn("trends", combined["sources"])
        self.assertIn("gdelt", combined["sources"])


if __name__ == "__main__":
    unittest.main()
