"""Fetch live Freqtrade backtest data from strat.ninja.

strat.ninja publishes two useful pages (robots.txt only disallows /quant.php):

* ranking.php -- the curated weekly leaderboard with rich backtest metrics
  (avg profit, win%, drawdown, Sharpe/Sortino/Calmar, Ninja Score). This is the
  part that changes every week as markets move.
* strats.php  -- the full strategy universe (~7k rows), each with a GitHub
  source link, timeframe, scraped date, and Ninja Score. We use this as a
  name -> source-code lookup so we can download and AI-analyze any strategy.

Outputs (under results/):
* strat_ninja_ranking.csv  -- this run's leaderboard with metrics + source url
* ninja_history.csv        -- appended weekly snapshot for week-over-week deltas

Downloaded strategy source is written to strat_ninja_strategies/ as <name>.py.
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import re
import ssl
import time
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
SOURCE_DIR = PROJECT_ROOT / "strat_ninja_strategies"
RANKING_CSV = RESULTS_DIR / "strat_ninja_ranking.csv"
HISTORY_CSV = RESULTS_DIR / "ninja_history.csv"

RANKING_URL = "https://strat.ninja/ranking.php"
STRATS_URL = "https://strat.ninja/strats.php"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# ranking.php column order (cell 0 is a blank icon cell).
RANKING_FIELDS = [
    "strategy_name",
    "avg_buys",
    "avg_profit",
    "avg_total_profit_pct",
    "avg_win_pct",
    "avg_drawdown_pct",
    "avg_time",
    "timeframe",
    "flag",
    "stoploss",
    "avg_sharpe",
    "avg_sortino",
    "avg_calmar",
    "ninja_score",
    "hash",
]

_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.S | re.I)
_HREF_RE = re.compile(r'href=["\']?([^"\'>\s]+)', re.I)


def make_ssl_context() -> ssl.SSLContext:
    # strat.ninja occasionally trips strict cert verification in CI; the data is
    # public and non-sensitive, so we tolerate an unverified chain here.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch(url: str, timeout: int = 90) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=make_ssl_context()) as response:
        return response.read().decode("utf-8", "replace")


def cell_text(cell_html: str) -> str:
    return html_lib.unescape(_TAG_RE.sub("", cell_html)).strip()


def cell_href(cell_html: str) -> str:
    match = _HREF_RE.search(cell_html)
    return match.group(1) if match else ""


def strategy_name_from_cell(cell_html: str) -> str:
    """Prefer the full name in the overview.php link over truncated cell text."""
    href = cell_href(cell_html)
    if "overview.php" in href:
        query = parse_qs(urlparse("https://x/" + href.lstrip("/")).query)
        name = query.get("strategy", [""])[0]
        if name:
            return name
    return cell_text(cell_html)


def parse_ranking(html: str) -> list[dict[str, str]]:
    rows = _ROW_RE.findall(html)
    leaderboard: list[dict[str, str]] = []
    for row in rows:
        cells = _CELL_RE.findall(row)
        if len(cells) < 16:
            continue
        # Skip the header row (cell[1] literally reads "Strategy").
        if cell_text(cells[1]).lower() == "strategy":
            continue
        name = strategy_name_from_cell(cells[1])
        if not name:
            continue
        values = [name] + [cell_text(c) for c in cells[2:16]]
        leaderboard.append(dict(zip(RANKING_FIELDS, values)))
    return leaderboard


def parse_strats(html: str) -> dict[str, dict[str, str]]:
    """Return {strategy_name: {source_url, timeframe, stoploss, flags, scraped, ninja_score}}."""
    rows = _ROW_RE.findall(html)
    universe: dict[str, dict[str, str]] = {}
    for row in rows:
        cells = _CELL_RE.findall(row)
        if len(cells) < 7:
            continue
        name = strategy_name_from_cell(cells[0])
        if not name or name.lower() == "strategy":
            continue
        universe[name] = {
            "source_url": cell_href(cells[4]),
            "timeframe": cell_text(cells[1]),
            "stoploss": cell_text(cells[2]),
            "flags": cell_text(cells[3]),
            "scraped": cell_text(cells[5]),
            "ninja_score": cell_text(cells[6]),
        }
    return universe


def github_blob_to_raw(url: str) -> str:
    """github.com/u/r/blob/<sha>/path -> raw.githubusercontent.com/u/r/<sha>/path"""
    if "github.com" not in url or "/blob/" not in url:
        return ""
    return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/", 1)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return f"{cleaned}.py"


def download_source(name: str, source_url: str, dest_dir: Path, timeout: int = 60) -> Path | None:
    raw_url = github_blob_to_raw(source_url)
    if not raw_url:
        return None
    try:
        code = fetch(raw_url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - network errors are expected per-file
        print(f"  ! source download failed for {name}: {exc}")
        return None
    if "<html" in code[:200].lower():
        print(f"  ! source for {name} did not look like raw python, skipping")
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / safe_filename(name)
    path.write_text(code, encoding="utf-8")
    return path


def write_ranking_csv(leaderboard: list[dict[str, str]], universe: dict[str, dict[str, str]]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    fieldnames = RANKING_FIELDS + ["source_url", "scraped", "source_file"]
    with RANKING_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in leaderboard:
            writer.writerow(row)
    print(f"Saved leaderboard: {RANKING_CSV} ({len(leaderboard)} strategies)")


def append_history(leaderboard: list[dict[str, str]], run_date: str) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    exists = HISTORY_CSV.exists()
    with HISTORY_CSV.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        if not exists:
            writer.writerow(["date", "strategy_name", "ninja_score", "avg_total_profit_pct"])
        for row in leaderboard:
            writer.writerow([
                run_date,
                row["strategy_name"],
                row.get("ninja_score", ""),
                row.get("avg_total_profit_pct", ""),
            ])
    print(f"Appended weekly snapshot to: {HISTORY_CSV}")


def run(args: argparse.Namespace) -> None:
    run_date = args.date or date.today().isoformat()

    print(f"Fetching leaderboard: {RANKING_URL}")
    leaderboard = parse_ranking(fetch(RANKING_URL))
    print(f"  parsed {len(leaderboard)} leaderboard rows")

    print(f"Fetching strategy universe: {STRATS_URL}")
    universe = parse_strats(fetch(STRATS_URL))
    print(f"  parsed {len(universe)} universe rows")

    # Attach source url from the universe lookup, download source code.
    download_count = 0
    for row in leaderboard:
        meta = universe.get(row["strategy_name"], {})
        row["source_url"] = meta.get("source_url", "")
        row["scraped"] = meta.get("scraped", "")
        row["source_file"] = ""

    targets = leaderboard if not args.max_download else leaderboard[: args.max_download]
    for row in targets:
        if not row["source_url"]:
            continue
        path = download_source(row["strategy_name"], row["source_url"], SOURCE_DIR)
        if path:
            row["source_file"] = str(path.relative_to(PROJECT_ROOT))
            download_count += 1
        time.sleep(args.sleep)
    print(f"Downloaded {download_count} strategy source files into {SOURCE_DIR}")

    write_ranking_csv(leaderboard, universe)
    append_history(leaderboard, run_date)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch live backtest data and strategy source from strat.ninja.")
    parser.add_argument("--max-download", type=int, default=None, help="Limit source downloads (for quick tests).")
    parser.add_argument("--sleep", type=float, default=0.5, help="Delay between source downloads.")
    parser.add_argument("--date", default=None, help="Override the snapshot date (YYYY-MM-DD).")
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
