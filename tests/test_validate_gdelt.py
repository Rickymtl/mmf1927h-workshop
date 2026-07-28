from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1] / "code"
sys.path.insert(0, str(CODE_DIR))

import validate_gdelt  # noqa: E402


class ValidateGdeltTests(unittest.TestCase):
    def test_valid_file_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AAPL.csv"
            pd.DataFrame(
                {
                    "date": ["2024-01-01", "2024-01-02"],
                    "tone": [1.0, -1.0],
                    "volume": [2.0, 3.0],
                }
            ).to_csv(path, index=False)
            stats, errors = validate_gdelt.validate_file(
                path, pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")
            )
        self.assertEqual(errors, [])
        self.assertEqual(stats["rows"], 2)

    def test_invalid_file_reports_quality_problems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AAPL.csv"
            pd.DataFrame(
                {
                    "date": ["2024-01-02", "2024-01-02"],
                    "tone": [1.0, None],
                    "volume": [2.5, -1],
                }
            ).to_csv(path, index=False)
            _, errors = validate_gdelt.validate_file(
                path, pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-03")
            )
        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("tone" in error for error in errors))
        self.assertTrue(any("negative volume" in error for error in errors))
        self.assertTrue(any("non-integer" in error for error in errors))

    def test_missing_ticker_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            coverage, failures = validate_gdelt.validate_directory(
                Path(tmp), ["AAPL"], "2024-01-01", "2024-01-02"
            )
        self.assertEqual(coverage, {})
        self.assertEqual(failures, {"AAPL": ["file is missing"]})


if __name__ == "__main__":
    unittest.main()
