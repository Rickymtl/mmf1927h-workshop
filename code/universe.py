"""Project universe: the 8 largest US companies per GICS sector.

Static snapshot of approximate market-cap leaders as of mid-2025. This is
*current membership* — it does not account for historical index changes, and
so carries survivorship bias (a Day 2 / point-in-time concern we document
here rather than hide). Each entry maps a ticker to a Google Trends search
keyword (usually the common company name, which behaves better as a search
term than the ticker symbol).
"""

from __future__ import annotations

# sector -> list of (ticker, google_trends_keyword)
SECTORS: dict[str, list[tuple[str, str]]] = {
    "Information Technology": [
        ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "Nvidia"),
        ("AVGO", "Broadcom"), ("ORCL", "Oracle"), ("CRM", "Salesforce"),
        ("AMD", "AMD"), ("CSCO", "Cisco"),
    ],
    "Communication Services": [
        ("GOOGL", "Google"), ("META", "Meta"), ("NFLX", "Netflix"),
        ("TMUS", "T-Mobile"), ("DIS", "Disney"), ("CMCSA", "Comcast"),
        ("VZ", "Verizon"), ("T", "AT&T"),
    ],
    "Consumer Discretionary": [
        ("AMZN", "Amazon"), ("TSLA", "Tesla"), ("HD", "Home Depot"),
        ("MCD", "McDonald's"), ("NKE", "Nike"), ("LOW", "Lowe's"),
        ("SBUX", "Starbucks"), ("BKNG", "Booking.com"),
    ],
    "Consumer Staples": [
        ("WMT", "Walmart"), ("PG", "Procter & Gamble"), ("COST", "Costco"),
        ("KO", "Coca-Cola"), ("PEP", "Pepsi"), ("PM", "Philip Morris"),
        ("MO", "Altria"), ("MDLZ", "Mondelez"),
    ],
    "Financials": [
        ("BRK-B", "Berkshire Hathaway"), ("JPM", "JPMorgan"), ("V", "Visa"),
        ("MA", "Mastercard"), ("BAC", "Bank of America"), ("WFC", "Wells Fargo"),
        ("GS", "Goldman Sachs"), ("MS", "Morgan Stanley"),
    ],
    "Health Care": [
        ("LLY", "Eli Lilly"), ("UNH", "UnitedHealth"), ("JNJ", "Johnson & Johnson"),
        ("MRK", "Merck"), ("ABBV", "AbbVie"), ("TMO", "Thermo Fisher"),
        ("ABT", "Abbott"), ("PFE", "Pfizer"),
    ],
    "Industrials": [
        ("GE", "General Electric"), ("CAT", "Caterpillar"), ("RTX", "Raytheon"),
        ("UNP", "Union Pacific"), ("HON", "Honeywell"), ("BA", "Boeing"),
        ("UPS", "UPS"), ("DE", "John Deere"),
    ],
    "Energy": [
        ("XOM", "Exxon"), ("CVX", "Chevron"), ("COP", "ConocoPhillips"),
        ("SLB", "Schlumberger"), ("EOG", "EOG Resources"), ("MPC", "Marathon Petroleum"),
        ("PSX", "Phillips 66"), ("WMB", "Williams Companies"),
    ],
    "Materials": [
        ("LIN", "Linde"), ("SHW", "Sherwin-Williams"), ("FCX", "Freeport-McMoRan"),
        ("ECL", "Ecolab"), ("NEM", "Newmont"), ("APD", "Air Products"),
        ("DOW", "Dow Chemical"), ("NUE", "Nucor"),
    ],
    "Real Estate": [
        ("PLD", "Prologis"), ("AMT", "American Tower"), ("EQIX", "Equinix"),
        ("WELL", "Welltower"), ("SPG", "Simon Property"), ("PSA", "Public Storage"),
        ("O", "Realty Income"), ("CCI", "Crown Castle"),
    ],
    "Utilities": [
        ("NEE", "NextEra Energy"), ("SO", "Southern Company"), ("DUK", "Duke Energy"),
        ("CEG", "Constellation Energy"), ("SRE", "Sempra"), ("AEP", "American Electric Power"),
        ("D", "Dominion Energy"), ("EXC", "Exelon"),
    ],
}


# --- GDELT query disambiguation ---------------------------------------------
# A Google Trends keyword is a poor news-corpus query: "Apple", "Amazon",
# "Visa", "Target"-style names match fruit, rainforests, travel documents and
# so on. For GDELT we build a stricter boolean query per ticker.
#
# Default template: the company name as an exact phrase, AND at least one
# finance term, so we keep market coverage and drop the noise.
_FINANCE_TERMS = '(stock OR shares OR earnings OR investors OR nasdaq OR nyse)'

# Names that need a more specific phrase than the Trends keyword.
GDELT_QUERY_OVERRIDES: dict[str, str] = {
    "AAPL": '"Apple Inc"',
    "AMZN": '"Amazon.com"',
    "V": '"Visa Inc"',
    "META": '"Meta Platforms"',
    "GOOGL": '(Alphabet OR "Google") ',
    "ORCL": '"Oracle Corp"',
    "DIS": '"Walt Disney"',
    "T": '"AT&T"',
    "O": '"Realty Income"',
    "D": '"Dominion Energy"',
    "GE": '"General Electric"',
    "DOW": '"Dow Inc"',
    "KO": '"Coca-Cola"',
    "PM": '"Philip Morris"',
    "MO": '"Altria"',
    "NKE": '"Nike Inc"',
    "MCD": '"McDonald\'s Corp"',
    "SO": '"Southern Company"',
    "CAT": '"Caterpillar Inc"',
    "UNP": '"Union Pacific"',
    "APD": '"Air Products"',
    "NEM": '"Newmont"',
    "MS": '"Morgan Stanley"',
    "GS": '"Goldman Sachs"',
}


def gdelt_query(ticker: str, finance_filter: bool = True) -> str:
    """Build the GDELT DOC query string for one ticker."""
    base = GDELT_QUERY_OVERRIDES.get(ticker)
    if base is None:
        base = f'"{ticker_to_keyword()[ticker]}"'
    query = f"{base} {_FINANCE_TERMS}" if finance_filter else base
    return f"{query} sourcelang:eng"


def all_tickers() -> list[str]:
    """Flat list of all tickers across every sector."""
    return [t for members in SECTORS.values() for t, _ in members]


def ticker_to_sector() -> dict[str, str]:
    """Map each ticker to its sector name."""
    return {t: sector for sector, members in SECTORS.items() for t, _ in members}


def ticker_to_keyword() -> dict[str, str]:
    """Map each ticker to its Google Trends search keyword."""
    return {t: kw for members in SECTORS.values() for t, kw in members}


if __name__ == "__main__":
    print(f"{len(SECTORS)} sectors, {len(all_tickers())} tickers total")
