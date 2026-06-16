from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRATEGIES_DIR = PROJECT_ROOT / "Strategies"
SHORT_TIMEFRAME_DIR = PROJECT_ROOT / "short_timeframe_strategies"
ERROR_DIR = PROJECT_ROOT / "strategies_error"
TOO_LARGE_DIR = PROJECT_ROOT / "strategies_too_large"
TEMP_EXTRACT_DIR = PROJECT_ROOT / "temp_extract"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "app_config.json"

DEFAULT_MODEL = "gpt-4o"
DEFAULT_MAX_FILE_LENGTH = 150_000
DEFAULT_SLEEP_SECONDS = 2.0
REPO_ZIP_URL = "https://github.com/davidzr/freqtrade-strategies/archive/refs/heads/main.zip"


def require_workspace_path(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"Refusing to operate outside project root: {resolved}")
    return resolved


def clear_directory(path: Path) -> None:
    path = require_workspace_path(path)
    if not path.exists():
        return

    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def download_and_extract_strategies(save_dir: Path) -> None:
    save_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading strategy repository: {REPO_ZIP_URL}")
    response = requests.get(REPO_ZIP_URL, timeout=120)
    response.raise_for_status()

    if TEMP_EXTRACT_DIR.exists():
        shutil.rmtree(TEMP_EXTRACT_DIR)
    TEMP_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            zip_ref.extractall(TEMP_EXTRACT_DIR)

        extracted = TEMP_EXTRACT_DIR / "freqtrade-strategies-main" / "strategies"
        if not extracted.exists():
            raise FileNotFoundError(f"Cannot find extracted strategies folder: {extracted}")

        copied = 0
        for source in extracted.rglob("*.py"):
            shutil.copy2(source, save_dir / source.name)
            copied += 1
        print(f"Copied {copied} strategy files into {save_dir}")
    finally:
        if TEMP_EXTRACT_DIR.exists():
            shutil.rmtree(TEMP_EXTRACT_DIR)


def load_strategies(folder: Path) -> dict[Path, str]:
    strategies: dict[Path, str] = {}
    for file_path in sorted(folder.glob("*.py")):
        try:
            strategies[file_path] = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            strategies[file_path] = file_path.read_text(encoding="latin-1")
    return strategies


def parse_strategy(client: OpenAI, model: str, strategy_code: str) -> dict | None:
    prompt = f"""
You are a professional Freqtrade strategy parser.
Read this Python strategy source and return only valid JSON with this structure:

{{
  "buy_conditions": [],
  "sell_conditions": [],
  "indicators": [],
  "timeframe": "",
  "market_type": "",
  "max_drawdown": "",
  "preferred_pairs": [],
  "strategy_style": ""
}}

Rules:
- Return JSON only, with no markdown fence.
- If a field cannot be determined, use an empty string or empty list.

```python
{strategy_code}
```
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You extract structured metadata from Freqtrade strategy code."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    return parse_json_object(content)


def parse_json_object(content: str) -> dict | None:
    content = content.strip()
    if content.startswith("```"):
        start = content.find("{")
        end = content.rfind("}")
        content = content[start : end + 1] if start != -1 and end != -1 else content

    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def load_app_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_api_key(config: dict) -> str | None:
    return config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")


def resolve_model(args: argparse.Namespace, config: dict) -> str:
    return args.model or config.get("model") or DEFAULT_MODEL


def copy_short_timeframe_strategies(parsed_results: dict[Path, dict], base_dir: Path) -> None:
    timeframes = {"1m", "3m", "5m"}
    for timeframe in timeframes:
        (base_dir / f"{timeframe}_strategies").mkdir(parents=True, exist_ok=True)

    copied = {timeframe: 0 for timeframe in timeframes}
    for source_path, summary in parsed_results.items():
        timeframe = str(summary.get("timeframe", "")).lower().strip()
        if timeframe not in timeframes:
            continue

        target = base_dir / f"{timeframe}_strategies" / source_path.name
        shutil.copy2(source_path, target)
        copied[timeframe] += 1

    for timeframe in sorted(copied):
        print(f"{timeframe}: copied {copied[timeframe]} strategies")


def prepare_strategies(args: argparse.Namespace) -> None:
    if args.reset:
        for folder in (STRATEGIES_DIR, SHORT_TIMEFRAME_DIR, ERROR_DIR, TOO_LARGE_DIR):
            clear_directory(folder)

    STRATEGIES_DIR.mkdir(exist_ok=True)
    SHORT_TIMEFRAME_DIR.mkdir(exist_ok=True)
    ERROR_DIR.mkdir(exist_ok=True)
    TOO_LARGE_DIR.mkdir(exist_ok=True)

    if args.download or (args.download_if_empty and not any(STRATEGIES_DIR.glob("*.py"))):
        download_and_extract_strategies(STRATEGIES_DIR)

    strategies = load_strategies(STRATEGIES_DIR)
    if args.limit:
        strategies = dict(list(strategies.items())[: args.limit])

    if not strategies:
        print(f"No strategy files found in {STRATEGIES_DIR}")
        return

    load_dotenv(PROJECT_ROOT / ".env")
    config = load_app_config()
    api_key = resolve_api_key(config)
    if not api_key:
        raise RuntimeError("OpenAI API key is required. Save it in the web UI or set OPENAI_API_KEY.")

    client = OpenAI(api_key=api_key)
    model = resolve_model(args, config)
    parsed_results: dict[Path, dict] = {}
    count_error = 0
    count_too_large = 0

    for file_path, code in tqdm(strategies.items(), desc="Parsing strategies"):
        if len(code) > args.max_file_length:
            shutil.move(str(file_path), TOO_LARGE_DIR / file_path.name)
            count_too_large += 1
            continue

        try:
            parsed = parse_strategy(client, model, code)
        except Exception as exc:
            print(f"OpenAI parsing failed for {file_path.name}: {exc}")
            parsed = None

        if parsed:
            parsed_results[file_path] = parsed
        else:
            shutil.move(str(file_path), ERROR_DIR / file_path.name)
            count_error += 1

        time.sleep(args.sleep)

    copy_short_timeframe_strategies(parsed_results, SHORT_TIMEFRAME_DIR)
    print("\nPreparation complete")
    print(f"Parsed: {len(parsed_results)}")
    print(f"Too large: {count_too_large}")
    print(f"Failed: {count_error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download, parse, and classify Freqtrade strategies.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--limit", type=int, default=None, help="Limit number of strategies for a test run.")
    parser.add_argument("--max-file-length", type=int, default=DEFAULT_MAX_FILE_LENGTH)
    parser.add_argument("--download", action="store_true", help="Download strategies even if Strategies/ is not empty.")
    parser.add_argument("--download-if-empty", action="store_true", default=True)
    parser.add_argument("--reset", action="store_true", help="Clear strategy folders before processing.")
    return parser


if __name__ == "__main__":
    prepare_strategies(build_parser().parse_args())
