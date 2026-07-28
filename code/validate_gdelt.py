"""Validate the completeness and shape of locally pulled GDELT CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from paths import HORIZON_END, HORIZON_START, RAW_DIR
from universe import all_tickers

GDELT_DIR = RAW_DIR / "gdelt"
REQUIRED_COLUMNS = ("date", "tone", "volume")


def validate_file(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> tuple[dict, list[str]]:
    """Return coverage statistics and validation errors for one ticker CSV."""
    errors: list[str] = []
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return {"file": str(path)}, [f"cannot read CSV: {exc}"]

    missing_columns = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing_columns:
        return (
            {"file": str(path), "rows": int(len(df))},
            [f"missing column(s): {', '.join(sorted(missing_columns))}"],
        )

    dates = pd.to_datetime(df["date"], errors="coerce")
    tone = pd.to_numeric(df["tone"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")

    if dates.isna().any():
        errors.append(f"{int(dates.isna().sum())} invalid date(s)")
    if tone.isna().any():
        errors.append(f"{int(tone.isna().sum())} invalid/missing tone value(s)")
    if volume.isna().any():
        errors.append(f"{int(volume.isna().sum())} invalid/missing volume value(s)")
    if dates.duplicated().any():
        errors.append(f"{int(dates.duplicated().sum())} duplicate date(s)")
    if not dates.is_monotonic_increasing:
        errors.append("dates are not sorted ascending")
    if (volume.dropna() < 0).any():
        errors.append("negative volume value(s)")
    if not ((volume.dropna() % 1).abs() < 1e-9).all():
        errors.append("non-integer article count(s)")

    valid_dates = dates.dropna()
    first_date = valid_dates.min() if not valid_dates.empty else pd.NaT
    last_date = valid_dates.max() if not valid_dates.empty else pd.NaT
    if pd.isna(first_date) or first_date > start:
        errors.append(f"coverage starts after {start.date()}")
    if pd.isna(last_date) or last_date < end:
        errors.append(f"coverage ends before {end.date()}")
    if not valid_dates.empty and ((valid_dates < start) | (valid_dates > end)).any():
        errors.append("date(s) outside requested window")

    stats = {
        "file": str(path),
        "rows": int(len(df)),
        "first_date": None if pd.isna(first_date) else str(first_date.date()),
        "last_date": None if pd.isna(last_date) else str(last_date.date()),
        "tone_min": None if tone.dropna().empty else float(tone.min()),
        "tone_max": None if tone.dropna().empty else float(tone.max()),
        "volume_min": None if volume.dropna().empty else float(volume.min()),
        "volume_max": None if volume.dropna().empty else float(volume.max()),
    }
    return stats, errors


def validate_directory(
    directory: Path,
    tickers: list[str],
    start: str,
    end: str,
) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Validate all expected ticker files in a GDELT output directory."""
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts > end_ts:
        raise ValueError("start must be on or before end")

    coverage: dict[str, dict] = {}
    failures: dict[str, list[str]] = {}
    for ticker in tickers:
        path = directory / f"{ticker}.csv"
        if not path.exists():
            failures[ticker] = ["file is missing"]
            continue
        stats, errors = validate_file(path, start_ts, end_ts)
        coverage[ticker] = stats
        if errors:
            failures[ticker] = errors
    return coverage, failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=GDELT_DIR)
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--start", default=HORIZON_START)
    parser.add_argument("--end", default=HORIZON_END)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tickers = args.tickers or all_tickers()
    coverage, failures = validate_directory(
        args.directory, tickers, args.start, args.end
    )

    print(
        f"[gdelt validation] {len(coverage)}/{len(tickers)} files found; "
        f"{len(failures)} ticker(s) failed validation"
    )
    for ticker, errors in failures.items():
        print(f"  [FAIL] {ticker}: {'; '.join(errors)}")

    if coverage:
        rows = [stats["rows"] for stats in coverage.values()]
        first_dates = [stats["first_date"] for stats in coverage.values() if stats["first_date"]]
        last_dates = [stats["last_date"] for stats in coverage.values() if stats["last_date"]]
        print(
            f"  rows/ticker: min={min(rows)}, max={max(rows)}; "
            f"coverage={min(first_dates)}..{max(last_dates)}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
