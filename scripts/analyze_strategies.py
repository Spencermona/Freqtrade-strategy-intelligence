from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHORT_TIMEFRAME_DIR = PROJECT_ROOT / "short_timeframe_strategies"
RESULTS_DIR = PROJECT_ROOT / "results"
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "app_config.json"
OUTPUT_CSV = RESULTS_DIR / "comprehensive_strategy_ranking.csv"
SUMMARY_CSV = RESULTS_DIR / "strategy_summary_report.csv"

DEFAULT_MODEL = "gpt-4o"
DEFAULT_SLEEP_SECONDS = 2.0
DEFAULT_EN_PROMPT = """[Role]
- Act as a professional Freqtrade strategy analyst. Judge only from the strategy source code.

[Score Focus]
- Technical indicator quality, entry logic, and exit logic
- Risk management, code quality, and market adaptability
- Backtesting robustness, live-trading practicality, risk-adjusted return potential, and innovation edge

[Penalty Rules]
- Strictly penalize missing sell logic, unrealistic stoploss, and overfitting risk
- Strictly penalize excessive parameters, fragile code, and conflicting signal conditions

[Output Style]
- Strengths, weaknesses, and recommendations should be 1-2 sentences each
- Be specific and actionable; avoid generic praise
- Prefer concrete source-code evidence: indicators, risk controls, exit logic, or code issues

[Final Decision]
- Explicitly state whether the strategy is suitable for 1m/3m/5m short-timeframe trading and live deployment."""
DEFAULT_ZH_PROMPT = "重点关注实盘交易风险、稳健性、可维护性，以及策略是否适合短周期交易。"

TIMEFRAME_FOLDERS = {
    "1m": SHORT_TIMEFRAME_DIR / "1m_strategies",
    "3m": SHORT_TIMEFRAME_DIR / "3m_strategies",
    "5m": SHORT_TIMEFRAME_DIR / "5m_strategies",
}

RESULT_COLUMNS = [
    "technical_indicators_score",
    "entry_logic_score",
    "exit_strategy_score",
    "risk_management_score",
    "code_quality_score",
    "market_adaptability_score",
    "backtesting_robustness_score",
    "practical_implementation_score",
    "risk_adjusted_returns_score",
    "innovation_edge_score",
    "overall_score",
    "strengths",
    "weaknesses",
    "recommendations",
    "risk_assessment",
    "complexity_level",
    "market_conditions",
    "estimated_sharpe_ratio",
    "max_drawdown_estimate",
    "strategy_name",
    "timeframe",
    "file_path",
]


def read_strategy_code(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def load_app_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_api_key(config: dict) -> str | None:
    return config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")


def resolve_model(args: argparse.Namespace, config: dict) -> str:
    return args.model or config.get("model") or DEFAULT_MODEL


def analyze_strategy(
    client: OpenAI,
    model: str,
    strategy_name: str,
    strategy_code: str,
    timeframe: str,
    custom_prompt: str = "",
    language: str = "en",
) -> dict:
    custom_prompt_section = ""
    if custom_prompt.strip():
        custom_prompt_section = f"""

Additional client analysis preferences:
{custom_prompt.strip()}
"""

    if language == "zh":
        language_instruction = """
Language instruction:
- Use Simplified Chinese for strengths, weaknesses, recommendations, market_conditions, and any other free-text explanation.
- Keep JSON keys exactly as specified.
- Keep enum fields risk_assessment and complexity_level as low/medium/high and beginner/intermediate/advanced so downstream scoring remains stable.
"""
    else:
        language_instruction = """
Language instruction:
- Use English for strengths, weaknesses, recommendations, market_conditions, and any other free-text explanation.
- Keep JSON keys and enum values exactly as specified.
"""

    prompt = f"""
You are a professional Freqtrade strategy analyst. Analyze this strategy comprehensively.

Strategy name: {strategy_name}
Timeframe: {timeframe}

Return only valid JSON with this exact structure:
{{
  "technical_indicators_score": <0-10>,
  "entry_logic_score": <0-10>,
  "exit_strategy_score": <0-10>,
  "risk_management_score": <0-10>,
  "code_quality_score": <0-10>,
  "market_adaptability_score": <0-10>,
  "backtesting_robustness_score": <0-10>,
  "practical_implementation_score": <0-10>,
  "risk_adjusted_returns_score": <0-10>,
  "innovation_edge_score": <0-10>,
  "overall_score": <0-100>,
  "strengths": "1-2 concise, concrete sentences about the strongest practical advantages",
  "weaknesses": "1-2 concise, concrete sentences about the most important risks or flaws",
  "recommendations": "1-2 concise, actionable sentences about what to test or improve next",
  "risk_assessment": "low/medium/high",
  "complexity_level": "beginner/intermediate/advanced",
  "market_conditions": "trending/ranging/volatile/all",
  "estimated_sharpe_ratio": "range or unknown",
  "max_drawdown_estimate": "range or unknown"
}}

Scoring guidance:
- Judge strategy logic from source code, not marketing claims.
- Penalize missing sell logic, unrealistic stoploss, overfitting risk, and fragile code.
- Keep scores internally consistent. overall_score should reflect the ten category scores.
- Keep strengths, weaknesses, and recommendations readable in a UI card: concise, specific, and practical.
- Avoid generic filler. Mention concrete strategy features, risk controls, or code issues when visible in the source.
- Do not exceed two sentences for strengths, weaknesses, or recommendations.
- Return JSON only, with no markdown fence.
{language_instruction}
{custom_prompt_section}

```python
{strategy_code}
```
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a strict quantitative trading strategy reviewer."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    parsed = parse_json_object(content)
    if parsed is None:
        raise ValueError(f"Model did not return valid JSON for {strategy_name}")
    return normalize_result(parsed)


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


def normalize_result(result: dict) -> dict:
    normalized = {}
    score_columns = [col for col in RESULT_COLUMNS if col.endswith("_score")]
    for column in score_columns:
        value = result.get(column, 0)
        try:
            normalized[column] = float(value)
        except (TypeError, ValueError):
            normalized[column] = 0.0

    normalized["overall_score"] = max(0.0, min(100.0, normalized.get("overall_score", 0.0)))
    for column in RESULT_COLUMNS:
        if column in normalized:
            continue
        value = result.get(column, "")
        normalized[column] = "" if value is None else str(value)
    return normalized


def iter_strategy_files(limit: int | None = None) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for timeframe, folder in TIMEFRAME_FOLDERS.items():
        if not folder.exists():
            print(f"Skipping missing folder: {folder}")
            continue
        for path in sorted(folder.glob("*.py")):
            files.append((timeframe, path))

    return files[:limit] if limit else files


def analyze_all(args: argparse.Namespace) -> pd.DataFrame:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_app_config(args.config)
    api_key = resolve_api_key(config)
    if not api_key:
        raise RuntimeError("OpenAI API key is required. Set OPENAI_API_KEY or save it in config/app_config.json.")

    client = OpenAI(api_key=api_key)
    model = resolve_model(args, config)
    custom_prompt = config.get("analysis_prompt", "")
    language = config.get("language", "en")
    if language == "zh" and custom_prompt == DEFAULT_EN_PROMPT:
        custom_prompt = DEFAULT_ZH_PROMPT
    rows = []
    files = iter_strategy_files(args.limit)
    if not files:
        raise FileNotFoundError(f"No strategy files found under {SHORT_TIMEFRAME_DIR}")

    for timeframe, file_path in tqdm(files, desc="Analyzing strategies"):
        strategy_name = file_path.stem
        try:
            analysis = analyze_strategy(client, model, strategy_name, read_strategy_code(file_path), timeframe, custom_prompt, language)
            analysis["strategy_name"] = strategy_name
            analysis["timeframe"] = timeframe
            analysis["file_path"] = str(file_path.relative_to(PROJECT_ROOT))
            rows.append(analysis)
        except Exception as exc:
            print(f"Failed to analyze {strategy_name}: {exc}")
        time.sleep(args.sleep)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No strategies were successfully analyzed.")

    for column in RESULT_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df = df[RESULT_COLUMNS].sort_values("overall_score", ascending=False).reset_index(drop=True)
    return df


def save_results(df: pd.DataFrame) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    summary_columns = [
        "strategy_name",
        "timeframe",
        "overall_score",
        "risk_assessment",
        "complexity_level",
        "strengths",
        "weaknesses",
        "recommendations",
        "file_path",
    ]
    df[summary_columns].to_csv(SUMMARY_CSV, index=False, encoding="utf-8-sig")

    print(f"Saved comprehensive ranking: {OUTPUT_CSV}")
    print(f"Saved summary report:        {SUMMARY_CSV}")
    print(f"Analyzed strategies:         {len(df)}")
    print(f"Average score:               {df['overall_score'].mean():.2f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze classified Freqtrade strategies and write CSV results.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--limit", type=int, default=None, help="Limit number of strategies for a test run.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to local UI configuration JSON.")
    return parser


if __name__ == "__main__":
    save_results(analyze_all(build_parser().parse_args()))
