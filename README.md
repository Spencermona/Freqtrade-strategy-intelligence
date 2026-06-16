# Freqtrade Strategy Intelligence

Local Docker-based analysis console for screening, scoring, and visualizing Freqtrade strategy files.

The app can fetch public Freqtrade strategies, classify short-timeframe strategies, analyze them with an OpenAI model, and generate ranking, summary, dashboard, and Excel reports.

## What You Need

- Docker Desktop
- An OpenAI API key
- A terminal such as Windows Terminal, PowerShell, Terminal, or VS Code Terminal

VS Code is optional. You do not need to install Python manually when using Docker.

## Quick Start With Docker

Clone the repo:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

Start the app:

```bash
docker compose up --build
```

Open the local web console:

```text
http://localhost:7860
```

## Web Workflow

1. Choose the interface language.
2. Enter your OpenAI API key.
3. Optionally adjust the analysis prompt framework.
4. Click `Save Configuration`.
5. Run the workflow:

```text
Step 1: Fetch and classify strategies
Step 2: Analyze and score strategies
Step 3: Generate dashboard and Excel report
```

Step 1 and Step 2 use the OpenAI API and may incur API cost. Step 3 only regenerates reports from existing analysis data.

## Outputs

Generated files are written to `results/`.

Typical outputs include:

| File | Purpose |
| --- | --- |
| `comprehensive_strategy_ranking.csv` | Full internal ranking data |
| `strategy_summary_report.csv` | Compact summary data |
| `freqtrade_strategy_dashboard.png` | English dashboard image |
| `freqtrade_strategy_report.xlsx` | English Excel report |
| `Freqtrade策略分析仪表板.png` | Chinese dashboard image |
| `Freqtrade策略评分汇总表.xlsx` | Chinese Excel report |

The web UI also provides visual ranking and summary previews, plus direct downloads for selected strategy files.

## Local Files

The Docker Compose setup mounts these folders:

| Folder | Purpose |
| --- | --- |
| `config/` | Local app configuration |
| `results/` | Generated report files |
| `Strategies/` | Downloaded raw strategy files |
| `short_timeframe_strategies/` | Classified 1m, 3m, and 5m strategies |
| `strategies_too_large/` | Strategy files skipped because they are too large |
| `strategies_error/` | Strategy files that failed parsing |

These folders are local working data and are ignored by Git.

## API Key Safety

Your API key is saved locally in:

```text
config/app_config.json
```

This file is ignored by Git and should not be committed.

The repository only includes:

```text
config/app_config.example.json
```

## Command Line Usage

You can also run scripts directly if you have a Python environment:

```bash
python scripts/prepare_strategies.py --reset --download
python scripts/analyze_strategies.py
python scripts/生成统计图表.py --language en
python scripts/生成Excel汇总.py --language en
```

For most users, the Docker web console is recommended.

## Development Notes

Notebook files are not required for Docker usage and are ignored by Git. They can be kept locally as private experiments or stored in a separate private archive repo.

## Disclaimer

This project provides strategy screening and analysis outputs only. It is not financial advice. Always review strategy code independently, run your own backtests, perform out-of-sample validation, and test carefully before live trading.
