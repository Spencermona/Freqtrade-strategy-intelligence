from __future__ import annotations

import argparse
from pathlib import Path
import warnings

import matplotlib
import numpy as np
import pandas as pd


matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
INPUT_CSV = RESULTS_DIR / "comprehensive_strategy_ranking.csv"

OUTPUT_FILES = {
    "zh": RESULTS_DIR / "Freqtrade策略分析仪表板.png",
    "en": RESULTS_DIR / "freqtrade_strategy_dashboard.png",
}

TEXT = {
    "zh": {
        "title": "Freqtrade 策略综合分析仪表板",
        "score_dist": "总体评分分布",
        "score": "评分",
        "strategy_count": "策略数量",
        "mean": "平均",
        "pass": "及格线",
        "avg_by_tf": "按周期平均评分",
        "avg_score": "平均评分",
        "risk_mix": "风险等级分布",
        "complexity_mix": "复杂度分布",
        "category_avg": "评分维度平均分",
        "score_band": "评分区间分布",
        "top20": "Top 20 策略排名",
        "indicator_vs_risk": "指标质量 vs 风险管理",
        "indicator_quality": "指标质量",
        "risk_management": "风险管理",
        "drawdown_dist": "最大回撤预期分布",
        "max_drawdown": "最大回撤 (%)",
        "saved": "仪表板已保存",
        "summary": "Freqtrade 策略综合分析统计摘要",
        "total": "总策略数",
        "average": "平均评分",
        "highest": "最高评分",
        "lowest": "最低评分",
        "low": "低",
        "medium": "中",
        "high": "高",
        "beginner": "初级",
        "intermediate": "中级",
        "advanced": "高级",
    },
    "en": {
        "title": "Freqtrade Strategy Intelligence Dashboard",
        "score_dist": "Overall Score Distribution",
        "score": "Score",
        "strategy_count": "Strategy Count",
        "mean": "Mean",
        "pass": "Pass",
        "avg_by_tf": "Average Score by Timeframe",
        "avg_score": "Average Score",
        "risk_mix": "Risk Level Mix",
        "complexity_mix": "Complexity Mix",
        "category_avg": "Category Score Averages",
        "score_band": "Score Band Distribution",
        "top20": "Top 20 Strategy Ranking",
        "indicator_vs_risk": "Indicator Quality vs Risk Management",
        "indicator_quality": "Indicator Quality",
        "risk_management": "Risk Management",
        "drawdown_dist": "Estimated Drawdown Distribution",
        "max_drawdown": "Max Drawdown (%)",
        "saved": "Dashboard saved",
        "summary": "Freqtrade Strategy Analysis Summary",
        "total": "Total strategies",
        "average": "Average score",
        "highest": "Highest score",
        "lowest": "Lowest score",
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "beginner": "Beginner",
        "intermediate": "Intermediate",
        "advanced": "Advanced",
    },
}

CATEGORY_LABELS = {
    "zh": {
        "technical_indicators_score": "技术指标",
        "entry_logic_score": "入场逻辑",
        "exit_strategy_score": "出场策略",
        "risk_management_score": "风险管理",
        "code_quality_score": "代码质量",
        "market_adaptability_score": "市场适应性",
        "backtesting_robustness_score": "回测稳健性",
        "practical_implementation_score": "实盘可用性",
        "risk_adjusted_returns_score": "风险调整收益",
        "innovation_edge_score": "创新优势",
    },
    "en": {
        "technical_indicators_score": "Technical Indicators",
        "entry_logic_score": "Entry Logic",
        "exit_strategy_score": "Exit Strategy",
        "risk_management_score": "Risk Management",
        "code_quality_score": "Code Quality",
        "market_adaptability_score": "Market Adaptability",
        "backtesting_robustness_score": "Backtest Robustness",
        "practical_implementation_score": "Practicality",
        "risk_adjusted_returns_score": "Risk-Adjusted Return",
        "innovation_edge_score": "Innovation Edge",
    },
}

warnings.filterwarnings("ignore", message="Glyph .* missing from font")


def configure_fonts() -> None:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    preferred_fonts = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    selected_fonts = [font for font in preferred_fonts if font in available_fonts]
    plt.rcParams["font.sans-serif"] = selected_fonts or ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def extract_max_drawdown(value: object) -> int:
    if pd.isna(value) or value == "unknown":
        return 20
    try:
        return int(str(value).split("-")[0].replace("%", ""))
    except ValueError:
        return 20


def localized_value(lang: str, value: str) -> str:
    key = str(value).lower()
    return TEXT[lang].get(key, str(value))


def build_dashboard(df: pd.DataFrame, lang: str) -> Path:
    labels = TEXT[lang]
    output_png = OUTPUT_FILES[lang]
    RESULTS_DIR.mkdir(exist_ok=True)

    fig = plt.figure(figsize=(22, 15))
    fig.suptitle(labels["title"], fontsize=21, fontweight="bold", y=0.985)

    ax1 = plt.subplot(3, 3, 1)
    ax1.hist(df["overall_score"], bins=20, color="steelblue", edgecolor="black", alpha=0.72)
    ax1.set_title(labels["score_dist"], fontsize=12, fontweight="bold")
    ax1.set_xlabel(f"{labels['score']} (0-100)")
    ax1.set_ylabel(labels["strategy_count"])
    ax1.axvline(df["overall_score"].mean(), color="red", linestyle="--", linewidth=2, label=f"{labels['mean']}: {df['overall_score'].mean():.1f}")
    ax1.axvline(60, color="green", linestyle="--", linewidth=2, label=f"{labels['pass']}: 60")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2 = plt.subplot(3, 3, 2)
    timeframe_scores = df.groupby("timeframe")["overall_score"].agg(["mean", "count"])
    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#A78BFA"]
    ax2.bar(timeframe_scores.index, timeframe_scores["mean"], color=colors[: len(timeframe_scores)], edgecolor="black", linewidth=1.4)
    ax2.set_title(labels["avg_by_tf"], fontsize=12, fontweight="bold")
    ax2.set_ylabel(labels["avg_score"])
    for i, (_, row) in enumerate(timeframe_scores.iterrows()):
        ax2.text(i, row["mean"] + 1, f"{row['mean']:.1f}\n(n={int(row['count'])})", ha="center", va="bottom", fontsize=9)
    ax2.set_ylim(0, max(80, timeframe_scores["mean"].max() + 10))
    ax2.grid(True, alpha=0.3, axis="y")

    ax3 = plt.subplot(3, 3, 3)
    risk_counts = df["risk_assessment"].value_counts()
    risk_labels = [localized_value(lang, value) for value in risk_counts.index]
    colors_risk = {"low": "#00AA00", "medium": "#FFA500", "high": "#FF0000"}
    risk_colors = [colors_risk.get(str(value).lower(), "#808080") for value in risk_counts.index]
    _, _, autotexts = ax3.pie(risk_counts.values, labels=risk_labels, autopct="%1.1f%%", colors=risk_colors, startangle=90, textprops={"fontsize": 9})
    ax3.set_title(labels["risk_mix"], fontsize=12, fontweight="bold")
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontweight("bold")

    ax4 = plt.subplot(3, 3, 4)
    complexity_order = ["beginner", "intermediate", "advanced"]
    complexity_counts = df["complexity_level"].value_counts()
    complexity_data = [complexity_counts.get(level, 0) for level in complexity_order]
    complexity_labels = [localized_value(lang, level) for level in complexity_order]
    bars = ax4.bar(complexity_labels, complexity_data, color=["#90EE90", "#FFD700", "#FF6347"], edgecolor="black", linewidth=1.4)
    ax4.set_title(labels["complexity_mix"], fontsize=12, fontweight="bold")
    ax4.set_ylabel(labels["strategy_count"])
    for bar in bars:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width() / 2, height, f"{int(height)}\n({height / len(df) * 100:.1f}%)", ha="center", va="bottom", fontsize=9)
    ax4.grid(True, alpha=0.3, axis="y")

    ax5 = plt.subplot(3, 3, 5)
    category_cols = [col for col in df.columns if col.endswith("_score") and col != "overall_score"]
    category_means = df[category_cols].mean().sort_values(ascending=False)
    category_names = [CATEGORY_LABELS[lang].get(col, col.replace("_score", "").replace("_", " ").title()) for col in category_means.index]
    ax5.barh(range(len(category_means)), category_means.values, color=plt.cm.viridis(np.linspace(0.3, 0.9, len(category_means))), edgecolor="black", linewidth=1)
    ax5.set_yticks(range(len(category_means)))
    ax5.set_yticklabels(category_names, fontsize=8)
    ax5.set_xlabel(f"{labels['avg_score']} (0-10)")
    ax5.set_title(labels["category_avg"], fontsize=12, fontweight="bold")
    ax5.set_xlim(0, 10)
    for i, value in enumerate(category_means.values):
        ax5.text(value + 0.15, i, f"{value:.2f}", va="center", fontsize=8)
    ax5.grid(True, alpha=0.3, axis="x")

    ax6 = plt.subplot(3, 3, 6)
    score_ranges = pd.cut(df["overall_score"], bins=[0, 40, 50, 60, 70, 80, 100], labels=["<40", "40-50", "50-60", "60-70", "70-80", "80-100"])
    score_dist = score_ranges.value_counts().sort_index()
    ax6.bar(range(len(score_dist)), score_dist.values, color=["#FF4444", "#FF8844", "#FFBB44", "#BBFF44", "#44FF44", "#44FF99"], edgecolor="black", linewidth=1.4)
    ax6.set_xticks(range(len(score_dist)))
    ax6.set_xticklabels(score_dist.index, fontsize=9)
    ax6.set_ylabel(labels["strategy_count"])
    ax6.set_title(labels["score_band"], fontsize=12, fontweight="bold")
    for i, value in enumerate(score_dist.values):
        ax6.text(i, value + 2, f"{value}\n({value / len(df) * 100:.1f}%)", ha="center", va="bottom", fontsize=8)
    ax6.grid(True, alpha=0.3, axis="y")

    ax7 = plt.subplot(3, 3, 7)
    top20 = df.nlargest(20, "overall_score")[["strategy_name", "overall_score"]].reset_index(drop=True)
    ax7.barh(range(len(top20)), top20["overall_score"].values, color=plt.cm.RdYlGn(np.linspace(0.3, 0.9, len(top20))), edgecolor="black", linewidth=0.8)
    ax7.set_yticks(range(len(top20)))
    ax7.set_yticklabels([f"{i + 1}. {name[:20]}" for i, name in enumerate(top20["strategy_name"])], fontsize=8)
    ax7.set_xlabel(labels["score"])
    ax7.set_title(labels["top20"], fontsize=12, fontweight="bold")
    ax7.set_xlim(max(0, top20["overall_score"].min() - 5), min(100, top20["overall_score"].max() + 5))
    ax7.invert_yaxis()
    for i, value in enumerate(top20["overall_score"].values):
        ax7.text(value + 0.2, i, f"{value:.0f}", va="center", fontsize=8)
    ax7.grid(True, alpha=0.3, axis="x")

    ax8 = plt.subplot(3, 3, 8)
    scatter = ax8.scatter(df["technical_indicators_score"], df["risk_management_score"], c=df["overall_score"], s=100, alpha=0.65, cmap="RdYlGn", edgecolor="black", linewidth=0.5)
    ax8.set_xlabel(labels["indicator_quality"])
    ax8.set_ylabel(labels["risk_management"])
    ax8.set_title(labels["indicator_vs_risk"], fontsize=12, fontweight="bold")
    ax8.grid(True, alpha=0.3)
    plt.colorbar(scatter, ax=ax8).set_label(labels["score"])

    ax9 = plt.subplot(3, 3, 9)
    df = df.copy()
    df["max_dd_value"] = df["max_drawdown_estimate"].apply(extract_max_drawdown)
    ax9.hist(df["max_dd_value"], bins=15, color="coral", edgecolor="black", alpha=0.72)
    ax9.set_xlabel(labels["max_drawdown"])
    ax9.set_ylabel(labels["strategy_count"])
    ax9.set_title(labels["drawdown_dist"], fontsize=12, fontweight="bold")
    ax9.axvline(df["max_dd_value"].mean(), color="red", linestyle="--", linewidth=2, label=f"{labels['mean']}: {df['max_dd_value'].mean():.1f}%")
    ax9.legend(fontsize=8)
    ax9.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0, 1, 0.965])
    plt.savefig(output_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_png


def print_summary(df: pd.DataFrame, lang: str, output_png: Path) -> None:
    labels = TEXT[lang]
    print(f"{labels['saved']}: {output_png}")
    print("\n" + "=" * 72)
    print(labels["summary"])
    print("=" * 72)
    print(f"{labels['total']}: {len(df)}")
    print(f"{labels['average']}: {df['overall_score'].mean():.2f}/100")
    print(f"{labels['highest']}: {df['overall_score'].max()}/100 ({df.loc[df['overall_score'].idxmax(), 'strategy_name']})")
    print(f"{labels['lowest']}: {df['overall_score'].min()}/100 ({df.loc[df['overall_score'].idxmin(), 'strategy_name']})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a localized Freqtrade strategy dashboard.")
    parser.add_argument("--language", choices=["zh", "en"], default="en")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_fonts()
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)
    output_png = build_dashboard(df, args.language)
    print_summary(df, args.language, output_png)


if __name__ == "__main__":
    main()
