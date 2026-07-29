"""Unit tests for cleaning.winsorize_standardize — #13."""

import sys
import unittest
from pathlib import Path

_code_dir = Path(__file__).resolve().parent.parent / "code"
if str(_code_dir) not in sys.path:
    sys.path.insert(0, str(_code_dir))

import numpy as np
import pandas as pd

from cleaning.winsorize_standardize import (
    winsorize_cross_section,
    rank_standardize,
    sector_neutralize,
    apply_all,
)


def _make_panel(n_tickers: int = 88, n_dates: int = 5) -> pd.DataFrame:
    """Build a realistic mini-panel for testing."""
    rng = np.random.default_rng(42)
    tickers = [f"T{t:03d}" for t in range(n_tickers)]
    sectors = ["IT"] * (n_tickers // 3) + ["Financials"] * (n_tickers // 3) + ["Health Care"] * (n_tickers - 2 * (n_tickers // 3))
    rows = []
    for d in range(n_dates):
        date = pd.Timestamp("2021-08-06") + pd.Timedelta(weeks=d)
        for i, ticker in enumerate(tickers):
            rows.append({
                "date": date,
                "ticker": ticker,
                "sector": sectors[i],
                "weekly_return": rng.normal(0, 0.03),
                "trends_interest": rng.uniform(0.5, 3.0),
            })
    return pd.DataFrame(rows)


class TestWinsorizeCrossSection(unittest.TestCase):
    def setUp(self):
        self.df = _make_panel(n_tickers=50, n_dates=3)

    def test_columns_added(self):
        out = winsorize_cross_section(self.df, ["weekly_return"])
        self.assertIn("weekly_return_wins", out.columns)

    def test_no_modification_to_original(self):
        original = self.df["weekly_return"].copy()
        winsorize_cross_section(self.df, ["weekly_return"])
        pd.testing.assert_series_equal(self.df["weekly_return"], original)

    def test_extreme_outlier_clamped(self):
        df = self.df.copy()
        df.loc[0, "weekly_return"] = 100.0
        out = winsorize_cross_section(df, ["weekly_return"])
        # The winsorized outlier must be strictly less than the raw 100.0.
        self.assertLess(out.loc[0, "weekly_return_wins"], 100.0)


class TestRankStandardize(unittest.TestCase):
    def setUp(self):
        self.df = _make_panel(n_tickers=30, n_dates=2)

    def test_rank_in_01(self):
        out = rank_standardize(self.df, ["weekly_return"])
        col = "weekly_return_rank"
        self.assertTrue((out[col] >= 0.0).all())
        self.assertTrue((out[col] <= 1.0).all())

    def test_rank_per_date(self):
        """Ranks should be in [0, 1] with reasonable spread."""
        out = rank_standardize(self.df, ["weekly_return"])
        col = "weekly_return_rank"
        for _, grp in out.groupby("date"):
            # With N tickers, min rank is 1/N (not 0).
            n = len(grp)
            self.assertAlmostEqual(grp[col].min(), 1.0 / n)
            self.assertAlmostEqual(grp[col].max(), 1.0)


class TestSectorNeutralize(unittest.TestCase):
    def setUp(self):
        self.df = _make_panel(n_tickers=30, n_dates=2)

    def test_neutral_column_added(self):
        out = sector_neutralize(self.df, ["weekly_return"])
        self.assertIn("weekly_return_sector_neutral", out.columns)

    def test_within_sector_mean_zero(self):
        """After neutralization, each sector×date group should have mean ≈ 0."""
        out = sector_neutralize(self.df, ["weekly_return"])
        col = "weekly_return_sector_neutral"
        means = out.groupby(["date", "sector"])[col].mean()
        for m in means:
            self.assertLess(abs(m), 1e-9)


class TestApplyAll(unittest.TestCase):
    def setUp(self):
        self.df = _make_panel(n_tickers=30, n_dates=2)

    def test_full_pipeline_columns(self):
        result, report = apply_all(
            self.df,
            value_columns=["weekly_return", "trends_interest"],
            sector_neutralize_flag=True,
        )
        self.assertIn("weekly_return_wins", result.columns)
        self.assertIn("weekly_return_wins_rank", result.columns)
        self.assertIn("weekly_return_wins_rank_sector_neutral", result.columns)
        self.assertIn("trends_interest_wins", result.columns)

    def test_without_sector_neutralize(self):
        result, _ = apply_all(
            self.df,
            value_columns=["weekly_return"],
            sector_neutralize_flag=False,
        )
        self.assertIn("weekly_return_wins_rank", result.columns)
        self.assertNotIn("weekly_return_wins_rank_sector_neutral", result.columns)

    def test_report_structure(self):
        _, report = apply_all(self.df)
        self.assertEqual(report["step"], "winsorize_standardize")
        self.assertIn("winsorization", report)
        self.assertIn("standardization", report)

    def test_no_matching_columns(self):
        df = pd.DataFrame({"date": ["2021-08-06"], "ticker": ["X"], "other": [1.0]})
        _, report = apply_all(df)
        self.assertIn("error", report)

    def test_dataframe_shape_preserved(self):
        result, _ = apply_all(self.df)
        self.assertEqual(len(result), len(self.df))


if __name__ == "__main__":
    unittest.main()
