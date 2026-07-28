from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1] / "code"
sys.path.insert(0, str(CODE_DIR))

import pull_gdelt  # noqa: E402


class TimelinePointsTests(unittest.TestCase):
    def test_extracts_data(self) -> None:
        payload = {"timeline": [{"series": "Average Tone", "data": [{"date": "x", "value": 1}]}]}
        self.assertEqual(
            pull_gdelt._timeline_points(payload, "timelinetone"),
            [{"date": "x", "value": 1}],
        )

    def test_accepts_empty_timeline(self) -> None:
        self.assertEqual(pull_gdelt._timeline_points({"timeline": []}, "timelinetone"), [])

    def test_rejects_missing_timeline(self) -> None:
        with self.assertRaisesRegex(ValueError, "no 'timeline' field"):
            pull_gdelt._timeline_points({}, "timelinetone")

    def test_rejects_missing_data_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "contains a data list"):
            pull_gdelt._timeline_points({"timeline": [{"series": "x"}]}, "timelinetone")


class RequestTests(unittest.TestCase):
    def test_plain_text_throttle_uses_minimum_cooldown(self) -> None:
        throttled = Mock(
            status_code=200,
            text="Please limit requests to one every 5 seconds.",
            headers={},
        )
        success = Mock(status_code=200, text='{"timeline": []}', headers={})
        success.json.return_value = {"timeline": []}

        with (
            patch.object(pull_gdelt.requests, "get", side_effect=[throttled, success]),
            patch.object(pull_gdelt.random, "uniform", return_value=0),
            patch.object(pull_gdelt.time, "sleep") as sleep,
        ):
            points = pull_gdelt._request(
                "query",
                "timelinetone",
                pd.Timestamp("2024-01-01"),
                pd.Timestamp("2024-01-02"),
                retries=2,
                sleep=6,
            )

        self.assertEqual(points, [])
        sleep.assert_called_once_with(pull_gdelt.MIN_THROTTLE_COOLDOWN)


class ToSeriesTests(unittest.TestCase):
    def test_parses_live_gdelt_date_shape(self) -> None:
        series = pull_gdelt._to_series(
            [
                {"date": "20240101T000000Z", "value": 0},
                {"date": "20240102T000000Z", "value": "-1.1695"},
            ],
            "tone",
        )
        self.assertEqual(
            list(series.index),
            [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        )
        self.assertEqual(list(series), [0.0, -1.1695])

    def test_averages_duplicate_tone_buckets(self) -> None:
        series = pull_gdelt._to_series(
            [
                {"date": "2024-01-01T00:00:00Z", "value": 2},
                {"date": "2024-01-01T12:00:00Z", "value": 4},
            ],
            "tone",
        )
        self.assertEqual(series.iloc[0], 3.0)

    def test_sums_duplicate_volume_buckets(self) -> None:
        series = pull_gdelt._to_series(
            [
                {"date": "2024-01-01T00:00:00Z", "value": 2},
                {"date": "2024-01-01T12:00:00Z", "value": 4},
            ],
            "volume",
        )
        self.assertEqual(series.iloc[0], 6.0)

    def test_rejects_missing_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing field"):
            pull_gdelt._to_series([{"date": "2024-01-01"}], "tone")

    def test_rejects_invalid_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid date/value"):
            pull_gdelt._to_series([{"date": "not-a-date", "value": "bad"}], "tone")

    def test_rejects_negative_volume(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative article count"):
            pull_gdelt._to_series([{"date": "2024-01-01", "value": -1}], "volume")


class ChunkRangeTests(unittest.TestCase):
    def test_ranges_are_inclusive_and_non_overlapping(self) -> None:
        ranges = list(
            pull_gdelt._chunk_ranges(
                pd.Timestamp("2024-01-15"), pd.Timestamp("2024-03-20"), 1
            )
        )
        self.assertEqual(
            ranges,
            [
                (pd.Timestamp("2024-01-15"), pd.Timestamp("2024-02-14")),
                (pd.Timestamp("2024-02-15"), pd.Timestamp("2024-03-14")),
                (pd.Timestamp("2024-03-15"), pd.Timestamp("2024-03-20")),
            ],
        )
        for (_, previous_end), (next_start, _) in zip(ranges, ranges[1:]):
            self.assertEqual(next_start, previous_end + pd.Timedelta(days=1))

    def test_rejects_invalid_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 1"):
            list(
                pull_gdelt._chunk_ranges(
                    pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01"), 0
                )
            )
        with self.assertRaisesRegex(ValueError, "on or before"):
            list(
                pull_gdelt._chunk_ranges(
                    pd.Timestamp("2024-02-01"), pd.Timestamp("2024-01-01"), 1
                )
            )


if __name__ == "__main__":
    unittest.main()
