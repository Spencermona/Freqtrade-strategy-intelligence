# Integration Handoff — Freqtrade Strategy Intelligence → Trading Web Platform

> **Purpose of this document.** This standalone project (`Strategy_analysis`) is being
> folded into a larger trading website (`trading-web-build`, a 3commas/tradersana-style
> platform). This file is a self-contained spec so the host project's AI/engineer can
> integrate it **without reading every script**. It describes what this project produces,
> the exact data contract, the product logic, and the integration tasks for the host.
>
> **Audience:** the host project's AI assistant + developer.
> **Owner:** Spencer. OpenAI cost is paid by the owner; end users never supply a key.

---

## 1. TL;DR — what this is now

Originally this was a local Docker app where each customer ran the analysis with **their
own** OpenAI key (abandoned: user login + key-secrecy made it unviable as a SaaS).

It is being repositioned as a **backend data pipeline** that the owner runs **once a week**.
It produces two things:

1. A **ranking dataset** that fuses live backtest performance with AI source-code analysis.
2. The **strategy `.py` source files** for download.

The host website is the **consumer**: it schedules the pipeline, ingests the outputs into
its own DB/storage, displays a free preview, and gates full data + downloads behind its
**existing** login system.

**Do NOT build separate auth/hosting/DB for this.** Reuse the host platform's. This project
contributes a pipeline + a data contract, nothing more.

---

## 2. Architecture: producer vs consumer

```
┌─ PRODUCER (this project — runs weekly in the host's CI/cron) ──────────────┐
│  Step 1  fetch_strat_ninja.py   scrape strat.ninja → metrics + source code │
│  Step 2  analyze (cached)       AI-score new/changed source only           │
│  Step 3  build_combined_ranking merge metrics + AI → trust-adjusted score  │
│  Secret needed: OPENAI_API_KEY  (host CI secret store — never client-side) │
└───────────────────────────┬───────────────────────────────────────────────┘
                            ↓ outputs: CSV/JSON + .py files
┌─ CONSUMER (host trading website — already has these) ──────────────────────┐
│  • Ingest combined ranking into host DB                                    │
│  • Upload strategy .py files into host object storage                      │
│  • Free preview (top rankings, partial fields) — public                    │
│  • Login/register wall on "download" + "full data"  ← lead capture          │
│  • Per-strategy detail view (AI strengths/weaknesses + backtest metrics)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The weekly update is meaningful because Step 1's backtest metrics change every week**
(markets move), while the AI analysis (Step 2) is cached by source hash and only re-runs
for new/changed strategies — so the recurring API cost is near zero.

---

## 3. Data sources

### 3.1 strat.ninja (live backtest performance + strategy discovery)
- `https://strat.ninja/ranking.php` — curated weekly leaderboard (~39 rows) with rich
  metrics: avg profit, total profit %, win %, drawdown %, Sharpe/Sortino/Calmar, Ninja Score.
- `https://strat.ninja/strats.php` — full universe (~7,200 rows) mapping **strategy name →
  GitHub source URL** + timeframe + scraped date + Ninja Score.
- `robots.txt` disallows only `/quant.php`; everything else is crawlable.
- Tables use `<th>` cells (not `<td>`); parser handles this. GitHub `blob` URLs are
  rewritten to `raw.githubusercontent.com` for direct download.
- **Reality check:** of the ~39 leaderboard strategies, ~20 have public GitHub source we
  can download + analyze. The rest are private/no-source — display backtest metrics only and
  label them "source not public" (AI trust factor = neutral; see §5).

### 3.2 OpenAI API (source-code trust analysis)
- Used in Step 2 to score each strategy's **source code** (overfit risk, real stop-loss,
  exit logic, code quality, etc.). Model configurable (`gpt-4o` default).
- This is the only paid dependency. Caching keeps weekly cost minimal.

---

## 4. The weekly pipeline (ordered)

Run from project root. Python: see §8 for the interpreter gotcha.

| Step | Command | Reads | Writes |
|---|---|---|---|
| 1. Fetch | `python scripts/fetch_strat_ninja.py` | strat.ninja (network) | `results/strat_ninja_ranking.csv`, `results/ninja_history.csv`, `strat_ninja_strategies/*.py` |
| 2. Analyze (cached) | `python scripts/analyze_strategies.py` *(needs caching update — see §7)* | `strat_ninja_strategies/*.py`, `config/app_config.json` | `results/comprehensive_strategy_ranking.csv`, `results/strategy_summary_report.csv` |
| 3. Merge | `python scripts/build_combined_ranking.py` *(to build — see §7)* | the two CSVs above + `ninja_history.csv` | `results/combined_ranking.csv` |

Steps 2–3 are the part still being finished (see §7, Build Status). Step 1 is **done and
verified**.

> Existing report generators `scripts/生成统计图表.py` (dashboard PNG) and
> `scripts/生成Excel汇总.py` (Excel) are **optional** in the website context — the host UI
> renders from the CSV/DB directly. Keep them only if you still want downloadable PNG/Excel.

---

## 5. Product logic — how the two data sources combine

This is the core value proposition and the part Spencer wants to get right. strat.ninja
already shows "what backtested well." Our differentiator: **use the AI source analysis as a
trust filter that adjusts the live ranking**, so an overfit strategy that backtests #1 gets
demoted.

**Proposed scoring (confirm exact weights with Spencer before shipping):**

```
trust_factor =
    if no public source:        1.0          # neutral; rank on backtest only, label "source not public"
    else map ai_overall_score (0-100) → multiplier in [0.5, 1.2]
    then hard penalty: if AI flags high overfit risk OR missing/unrealistic stop-loss,
         clamp trust_factor ≤ 0.5

trust_adjusted_score = ninja_score * trust_factor
```

Display ideas (host UI):
1. **Trust-adjusted ranking** = primary leaderboard.
2. **Two-axis view**: X = backtest performance (ninja_score), Y = AI code-quality. Top-right
   = "recommended"; bottom-right (good backtest + weak code) = "overfit risk" badge.
3. **Week-over-week delta**: from `ninja_history.csv`, show ▲/▼ on each strategy. This is what
   makes users return weekly.

---

## 6. Data contract (exact output schemas)

The host should ingest these. Column names are stable; treat them as the API.

### 6.1 `results/strat_ninja_ranking.csv` — live backtest leaderboard *(DONE)*
`strategy_name, avg_buys, avg_profit, avg_total_profit_pct, avg_win_pct,
avg_drawdown_pct, avg_time, timeframe, flag, stoploss, avg_sharpe, avg_sortino,
avg_calmar, ninja_score, hash, source_url, scraped, source_file`
- `source_url`: GitHub blob URL (empty if private/no source).
- `source_file`: local path to the downloaded `.py` under `strat_ninja_strategies/` (empty if not downloaded).
- `hash`: strat.ninja's own strategy identifier (stable key for dedup).

### 6.2 `results/ninja_history.csv` — weekly snapshots for deltas *(DONE)*
`date, strategy_name, ninja_score, avg_total_profit_pct`
- One block of rows appended per run (`date` = ISO run date). Compute ▲/▼ by diffing the two
  most recent distinct dates per `strategy_name`.

### 6.3 `results/comprehensive_strategy_ranking.csv` — AI analysis *(produced by existing script)*
`technical_indicators_score, entry_logic_score, exit_strategy_score, risk_management_score,
code_quality_score, market_adaptability_score, backtesting_robustness_score,
practical_implementation_score, risk_adjusted_returns_score, innovation_edge_score,
overall_score, strengths, weaknesses, recommendations, risk_assessment, complexity_level,
market_conditions, estimated_sharpe_ratio, max_drawdown_estimate, strategy_name, timeframe,
file_path`
- Scores are 0–10 except `overall_score` (0–100). `risk_assessment` ∈ {low,medium,high};
  `complexity_level` ∈ {beginner,intermediate,advanced}. `strengths/weaknesses/recommendations`
  are short UI-ready sentences. Join key: `strategy_name`.

### 6.4 `results/strategy_summary_report.csv` — compact AI summary *(produced by existing script)*
`strategy_name, timeframe, overall_score, risk_assessment, complexity_level, strengths,
weaknesses, recommendations, file_path`

### 6.5 `results/combined_ranking.csv` — the merged product table *(TO BUILD — see §7)*
Proposed = backtest metrics (§6.1) + AI fields (`overall_score`, `risk_assessment`,
`strengths`, `weaknesses`, `recommendations`) + computed `trust_factor`,
`trust_adjusted_score`, `ninja_score_delta`, `source_available` (bool). Join on `strategy_name`.

### 6.6 Strategy source files
`strat_ninja_strategies/<strategy_name>.py` — the downloadable artifacts. The host should
push these into its object storage and serve them **only to authenticated users**.

---

## 7. Build status (what's done vs TODO)

**DONE & verified**
- `scripts/fetch_strat_ninja.py` — scrapes both pages, downloads source, writes §6.1 + §6.2.
  Verified: parsed 39 leaderboard + 7,187 universe rows, downloaded real `.py` files.
- `.gitignore` fixed (was ignoring `.github/`, which would have blocked any Actions workflow).

**TODO (specs below; can be done by host AI or ported as-is)**
1. **Hash-cached analysis.** Update `scripts/analyze_strategies.py` (or a thin wrapper) to:
   read `.py` from `strat_ninja_strategies/`; keep a cache `results/analysis_cache.json`
   keyed by `sha256(source)`; only call OpenAI for new/changed hashes; reuse cached results
   otherwise. (The existing `analyze_strategy()` function is reusable as-is.)
2. **`scripts/build_combined_ranking.py`.** Implement the merge + scoring in §5/§6.5.
3. **Scheduling.** A weekly job (host CI cron or `.github/workflows/`) that runs Steps 1→2→3
   then ingests outputs into the host DB/storage. `OPENAI_API_KEY` must come from the CI
   secret store.

---

## 8. Environment & gotchas (read before running)

- **Python interpreter:** the committed `.venv` is broken (its path points to an old machine,
  `SpencerTY/anaconda3`). Use a clean interpreter / the host's environment. On the dev machine
  `.venv-run/Scripts/python.exe` works.
- **`requests` is broken in the dev venv** (no `.get`). `fetch_strat_ninja.py` deliberately
  uses stdlib `urllib` + an unverified SSL context to avoid this and CI cert issues. The host
  can switch to `requests`/`httpx` freely.
- **Dependencies:** `pandas, numpy, matplotlib, openpyxl, openai, python-dotenv, requests, tqdm`
  (see `requirements.txt`). The scraper itself needs no third-party deps.
- **OpenAI key resolution order:** `config/app_config.json` → `OPENAI_API_KEY` env var. In the
  host, drop the JSON config and use the env/secret only.
- **Legal:** the strategy source comes from public GitHub repos that strat.ninja links to.
  Spencer has confirmed redistribution of the referenced repo(s) is acceptable. The host
  should preserve `source_url` attribution on each strategy.
- **Files safe to ignore when porting:** `Freqtrade_strategy_choose.ipynb`, `ranking_analysis.ipynb`,
  `tans.ipynb`, `Dockerfile`, `docker-compose.yml`, `scripts/config_server.py` (the old local
  web UI — superseded by the host site). The valuable code is `scripts/fetch_strat_ninja.py`,
  `scripts/analyze_strategies.py`, and the data contract in §6.

---

## 9. Suggested integration checklist for the host

- [ ] Copy `scripts/fetch_strat_ninja.py` + `scripts/analyze_strategies.py` into the host repo (or a `services/strategy-intel/` module).
- [ ] Add `OPENAI_API_KEY` to the host's CI/secret store.
- [ ] Implement hash-cached analysis + `build_combined_ranking.py` (§7).
- [ ] Add a weekly job that runs the 3 steps and ingests outputs into the host DB + object storage.
- [ ] DB table for `combined_ranking` (schema §6.5) + a `ninja_history` table for deltas.
- [ ] Public preview page (top N, partial fields) + login-gated full table & `.py` downloads.
- [ ] Per-strategy detail page: AI strengths/weaknesses/recommendations + backtest metrics + week-over-week chart.
- [ ] Confirm the trust-score weights in §5 with Spencer.
