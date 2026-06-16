from __future__ import annotations

import csv
import html
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "app_config.json"
RESULTS_DIR = PROJECT_ROOT / "results"
PYTHON = os.environ.get("PYTHON_EXECUTABLE", sys.executable)
STRATEGY_DOWNLOAD_ROOTS = [
    PROJECT_ROOT / "short_timeframe_strategies",
    PROJECT_ROOT / "Strategies",
]

DEFAULT_CONFIG = {
    "language": "",
    "openai_api_key": "",
    "model": "gpt-4o",
    "analysis_prompt": "Focus on practical live-trading risk, robustness, maintainability, and whether the strategy is suitable for short-timeframe trading.",
}
ZH_DEFAULT_PROMPT = "重点关注实盘交易风险、稳健性、可维护性，以及策略是否适合短周期交易。"

RUN_STATE = {
    "status": "idle",
    "step": "",
    "command": "",
    "output": "",
    "started_at": "",
    "finished_at": "",
    "cancel_requested": False,
}
STATE_LOCK = threading.Lock()
PROCESS_LOCK = threading.Lock()
CURRENT_PROCESS: subprocess.Popen | None = None

OUTPUTS = {
    "zh": {
        "dashboard": "Freqtrade策略分析仪表板.png",
        "excel": "Freqtrade策略评分汇总表.xlsx",
    },
    "en": {
        "dashboard": "freqtrade_strategy_dashboard.png",
        "excel": "freqtrade_strategy_report.xlsx",
    },
}

TEXT = {
    "zh": {
        "choose_title": "选择界面语言",
        "choose_subtitle": "请选择这个本地控制台的语言。之后也可以在右上角切换。",
        "choose_zh": "中文",
        "choose_en": "English",
        "app_title": "Freqtrade 策略分析控制台",
        "app_subtitle": "面向 Freqtrade 策略的本地分析工具：配置 API、运行三步流程，并生成排名、摘要、仪表板和 Excel 报告。",
        "switch": "English",
        "configuration": "配置",
        "saved_local": "配置保存在本地 config/app_config.json",
        "api_key": "OpenAI API Key",
        "api_hint": "第 1 步和第 2 步会使用。该文件只应保存在本地，不要提交到 GitHub。",
        "model": "模型",
        "custom_prompt": "自定义分析偏好",
        "prompt_hint": "这段内容会追加到第 2 步的固定评分格式中，用来调整评估重点，同时尽量不破坏输出结构。",
        "save": "保存配置",
        "saved": "配置已保存。",
        "run_status": "运行状态",
        "current_step": "当前步骤",
        "started": "开始时间",
        "finished": "结束时间",
        "command": "命令",
        "idle": "空闲",
        "running": "运行中",
        "success": "成功",
        "failed": "失败",
        "stopped": "已终止",
        "no_active_run": "暂无任务",
        "logs_placeholder": "运行后日志会显示在这里。",
        "stop": "终止当前任务",
        "workflow": "三步工作流",
        "run_one": "一次运行一个步骤",
        "step1_title": "拉取并分类策略",
        "step1_desc": "下载 Freqtrade 策略文件，解析元信息，并把短周期策略分类到 1m、3m、5m 文件夹。",
        "step2_title": "分析与评分",
        "step2_desc": "读取已分类策略，使用配置里的分析偏好，生成排名数据和摘要数据。",
        "step3_title": "生成仪表板和 Excel",
        "step3_desc": "根据当前语言，使用现有分析数据重新生成仪表板图片和 Excel 工作簿。",
        "uses_api": "会调用 API",
        "no_api": "不调用 API",
        "api_cost": "可能产生 OpenAI API 费用",
        "limit": "测试数量（可选）",
        "limit_placeholder": "留空表示全量运行",
        "run_step1": "运行第 1 步",
        "run_step2": "运行第 2 步",
        "run_step3": "运行第 3 步",
        "confirm_step1": "第 1 步会重新拉取并重置策略分类目录，而且会调用 OpenAI API。确定继续？",
        "confirm_step2": "第 2 步会调用 OpenAI API 分析策略，可能耗时并产生费用。确定继续？",
        "confirm_step3": "第 3 步只会用现有分析数据重新生成仪表板和 Excel，不调用 API。确定继续？",
        "confirm_stop": "确定要终止当前任务？",
        "already_running": "已有任务正在运行。",
        "step1_started": "第 1 步已开始。",
        "step2_started": "第 2 步已开始。",
        "step3_started": "第 3 步已开始。",
        "stop_sent": "已发送终止请求。",
        "results": "输出结果",
        "stored": "文件保存在 results/",
        "ranking": "策略排名",
        "summary": "策略摘要",
        "ranking_desc": "可视化策略榜单",
        "summary_desc": "可视化摘要预览",
        "dashboard": "仪表板图片",
        "excel": "Excel 报告",
        "show": "查看",
        "download": "下载",
        "pending": "未生成",
        "preview": "预览",
        "preview_hint": "点击上方卡片查看排名、摘要或仪表板。Excel 保持下载。",
        "not_generated": "尚未生成",
        "score": "评分",
        "risk": "风险",
        "complexity": "复杂度",
        "timeframe": "周期",
        "strengths": "优势",
        "weaknesses": "不足",
        "recommendations": "建议",
        "top_ranking": "Top 策略排名",
        "summary_overview": "分析摘要",
        "total": "策略总数",
        "average": "平均分",
        "pass_rate": "及格率",
        "best": "最高分",
        "risk_mix": "风险分布",
        "complexity_mix": "复杂度分布",
        "low": "低",
        "medium": "中",
        "high": "高",
        "beginner": "初级",
        "intermediate": "中级",
        "advanced": "高级",
    },
    "en": {
        "choose_title": "Choose Interface Language",
        "choose_subtitle": "Choose the language for this local console. You can switch later in the top-right corner.",
        "choose_zh": "中文",
        "choose_en": "English",
        "app_title": "Freqtrade Strategy Intelligence Console",
        "app_subtitle": "A local analysis console for Freqtrade strategies: configure API access, run the three-step workflow, and generate ranking, summary, dashboard, and Excel reports.",
        "switch": "中文",
        "configuration": "Configuration",
        "saved_local": "Saved locally in config/app_config.json",
        "api_key": "OpenAI API Key",
        "api_hint": "Used by Step 1 and Step 2. Keep this file local and do not commit it to GitHub.",
        "model": "Model",
        "custom_prompt": "Custom Analysis Prompt",
        "prompt_hint": "This is appended to the locked scoring format in Step 2, allowing users to adjust evaluation focus without breaking the output schema.",
        "save": "Save Configuration",
        "saved": "Configuration saved.",
        "run_status": "Run Status",
        "current_step": "Current step",
        "started": "Started",
        "finished": "Finished",
        "command": "Command",
        "idle": "Idle",
        "running": "Running",
        "success": "Success",
        "failed": "Failed",
        "stopped": "Stopped",
        "no_active_run": "No active run",
        "logs_placeholder": "Logs will appear here after a run.",
        "stop": "Stop Current Run",
        "workflow": "Three-Step Workflow",
        "run_one": "Run one step at a time",
        "step1_title": "Fetch and Classify Strategies",
        "step1_desc": "Download Freqtrade strategy files, parse metadata, and classify short-timeframe strategies into 1m, 3m, and 5m folders.",
        "step2_title": "Analyze and Score",
        "step2_desc": "Read classified strategies, apply your configured analysis preferences, and write ranking and summary data.",
        "step3_title": "Generate Dashboard and Excel",
        "step3_desc": "Regenerate the dashboard image and Excel workbook from current analysis data in the selected language.",
        "uses_api": "Uses API",
        "no_api": "No API call",
        "api_cost": "May incur OpenAI API cost",
        "limit": "Test limit (optional)",
        "limit_placeholder": "Leave empty for full run",
        "run_step1": "Run Step 1",
        "run_step2": "Run Step 2",
        "run_step3": "Run Step 3",
        "confirm_step1": "Step 1 will fetch strategies, reset classification folders, and call OpenAI API. Continue?",
        "confirm_step2": "Step 2 will call OpenAI API to analyze strategies. It may take time and incur cost. Continue?",
        "confirm_step3": "Step 3 only regenerates dashboard and Excel from existing analysis data. No API call. Continue?",
        "confirm_stop": "Stop the current run?",
        "already_running": "Another step is already running.",
        "step1_started": "Step 1 started.",
        "step2_started": "Step 2 started.",
        "step3_started": "Step 3 started.",
        "stop_sent": "Stop request sent.",
        "results": "Results",
        "stored": "Files are stored in results/",
        "ranking": "Strategy Ranking",
        "summary": "Strategy Summary",
        "ranking_desc": "Visual ranking preview",
        "summary_desc": "Visual summary preview",
        "dashboard": "Dashboard PNG",
        "excel": "Excel Report",
        "show": "Show",
        "download": "Download",
        "pending": "Pending",
        "preview": "Preview",
        "preview_hint": "Click a card above to preview ranking, summary, or dashboard. Excel remains download-only.",
        "not_generated": "Not generated yet",
        "score": "Score",
        "risk": "Risk",
        "complexity": "Complexity",
        "timeframe": "Timeframe",
        "strengths": "Strengths",
        "weaknesses": "Weaknesses",
        "recommendations": "Recommendations",
        "top_ranking": "Top Strategy Ranking",
        "summary_overview": "Analysis Summary",
        "total": "Total Strategies",
        "average": "Average Score",
        "pass_rate": "Pass Rate",
        "best": "Best Score",
        "risk_mix": "Risk Mix",
        "complexity_mix": "Complexity Mix",
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "beginner": "Beginner",
        "intermediate": "Intermediate",
        "advanced": "Advanced",
    },
}

TEXT["zh"].update(
    {
        "download_strategy": "\u4e0b\u8f7d\u7b56\u7565",
        "prompt_template": "\u63d0\u793a\u8bcd\u6a21\u677f",
        "use_template": "\u4f7f\u7528\u6a21\u677f",
        "prompt_template_text": "\u8bf7\u4ee5\u4e13\u4e1a Freqtrade \u7b56\u7565\u5206\u6790\u5e08\u7684\u89d2\u5ea6\u8bc4\u4f30\u7b56\u7565\u6e90\u7801\u3002\u8bc4\u5206\u65f6\u4f18\u5148\u8003\u8651\uff1a\u6280\u672f\u6307\u6807\u8d28\u91cf\u3001\u5165\u573a\u903b\u8f91\u3001\u51fa\u573a\u903b\u8f91\u3001\u98ce\u9669\u7ba1\u7406\u3001\u4ee3\u7801\u8d28\u91cf\u3001\u5e02\u573a\u9002\u5e94\u6027\u3001\u56de\u6d4b\u7a33\u5065\u6027\u3001\u5b9e\u76d8\u53ef\u6267\u884c\u6027\u3001\u98ce\u9669\u8c03\u6574\u6536\u76ca\u548c\u7b56\u7565\u521b\u65b0\u6027\u3002\u8bf7\u4e25\u683c\u60e9\u7f5a\u7f3a\u5c11\u5356\u51fa\u903b\u8f91\u3001\u4e0d\u73b0\u5b9e\u7684\u6b62\u635f\u3001\u8fc7\u62df\u5408\u98ce\u9669\u3001\u8fc7\u591a\u53c2\u6570\u548c\u8106\u5f31\u4ee3\u7801\u3002\u4f18\u52bf\u3001\u4e0d\u8db3\u548c\u5efa\u8bae\u8981\u9002\u5408\u663e\u793a\u5728\u524d\u7aef\u5361\u7247\u4e2d\uff1a\u6bcf\u9879 1-2 \u53e5\uff0c\u5177\u4f53\u3001\u53ef\u6267\u884c\uff0c\u4e0d\u8981\u7a7a\u6cdb\u8d5e\u7f8e\u3002\u7279\u522b\u8bf4\u660e\u8fd9\u4e2a\u7b56\u7565\u662f\u5426\u9002\u5408 1m/3m/5m \u77ed\u5468\u671f\u4ea4\u6613\u548c\u5b9e\u76d8\u90e8\u7f72\u3002",
        "legacy_language_notice": "\u91cd\u65b0\u8fd0\u884c\u7b2c 2 \u6b65\u540e\u5c06\u663e\u793a\u4e2d\u6587\u5206\u6790\u5185\u5bb9\u3002",
    }
)
TEXT["en"].update(
    {
        "download_strategy": "Download Strategy",
        "prompt_template": "Prompt Template",
        "use_template": "Use Template",
        "prompt_template_text": "Evaluate the strategy source code as a professional Freqtrade strategy analyst. Prioritize technical indicator quality, entry logic, exit logic, risk management, code quality, market adaptability, backtesting robustness, practical live-trading implementation, risk-adjusted return potential, and innovation edge. Penalize missing sell logic, unrealistic stoploss settings, overfitting risk, excessive parameters, and fragile code. Strengths, weaknesses, and recommendations must be suitable for frontend cards: 1-2 sentences each, specific, actionable, and not generic praise. Explicitly comment on whether the strategy is suitable for 1m/3m/5m short-timeframe trading and live deployment.",
        "legacy_language_notice": "Rerun Step 2 to regenerate this analysis in English.",
    }
)


def prompt_framework(lang: str) -> list[tuple[str, list[str]]]:
    if lang == "zh":
        return [
            (
                "\u89d2\u8272",
                ["\u4f60\u662f\u4e13\u4e1a\u7684 Freqtrade \u7b56\u7565\u5206\u6790\u5e08\uff0c\u53ea\u6839\u636e\u7b56\u7565\u6e90\u7801\u8fdb\u884c\u5224\u65ad\u3002"],
            ),
            (
                "\u8bc4\u5206\u91cd\u70b9",
                [
                    "\u6280\u672f\u6307\u6807\u8d28\u91cf\u3001\u5165\u573a\u903b\u8f91\u3001\u51fa\u573a\u903b\u8f91",
                    "\u98ce\u9669\u7ba1\u7406\u3001\u4ee3\u7801\u8d28\u91cf\u3001\u5e02\u573a\u9002\u5e94\u6027",
                    "\u56de\u6d4b\u7a33\u5065\u6027\u3001\u5b9e\u76d8\u53ef\u6267\u884c\u6027\u3001\u98ce\u9669\u8c03\u6574\u6536\u76ca\u3001\u521b\u65b0\u6027",
                ],
            ),
            (
                "\u6263\u5206\u89c4\u5219",
                [
                    "\u4e25\u683c\u60e9\u7f5a\u7f3a\u5c11\u5356\u51fa\u903b\u8f91\u3001\u4e0d\u73b0\u5b9e\u6b62\u635f\u3001\u8fc7\u62df\u5408\u98ce\u9669",
                    "\u4e25\u683c\u60e9\u7f5a\u8fc7\u591a\u53c2\u6570\u3001\u4ee3\u7801\u8106\u5f31\u3001\u4fe1\u53f7\u6761\u4ef6\u76f8\u4e92\u51b2\u7a81",
                ],
            ),
            (
                "\u8f93\u51fa\u98ce\u683c",
                [
                    "\u4f18\u52bf\u3001\u4e0d\u8db3\u3001\u5efa\u8bae\u6bcf\u9879 1-2 \u53e5",
                    "\u5fc5\u987b\u5177\u4f53\u3001\u53ef\u6267\u884c\uff0c\u4e0d\u8981\u7a7a\u6cdb\u8d5e\u7f8e",
                    "\u4f18\u5148\u63d0\u5230\u6e90\u7801\u91cc\u770b\u5f97\u89c1\u7684\u6307\u6807\u3001\u98ce\u63a7\u3001\u51fa\u573a\u6216\u4ee3\u7801\u95ee\u9898",
                ],
            ),
            (
                "\u6700\u7ec8\u5224\u65ad",
                ["\u660e\u786e\u8bf4\u660e\u8be5\u7b56\u7565\u662f\u5426\u9002\u5408 1m/3m/5m \u77ed\u5468\u671f\u4ea4\u6613\u548c\u5b9e\u76d8\u90e8\u7f72\u3002"],
            ),
        ]
    return [
        ("Role", ["Act as a professional Freqtrade strategy analyst. Judge only from the strategy source code."]),
        (
            "Score Focus",
            [
                "Technical indicator quality, entry logic, and exit logic",
                "Risk management, code quality, and market adaptability",
                "Backtesting robustness, live-trading practicality, risk-adjusted return potential, and innovation edge",
            ],
        ),
        (
            "Penalty Rules",
            [
                "Strictly penalize missing sell logic, unrealistic stoploss, and overfitting risk",
                "Strictly penalize excessive parameters, fragile code, and conflicting signal conditions",
            ],
        ),
        (
            "Output Style",
            [
                "Strengths, weaknesses, and recommendations should be 1-2 sentences each",
                "Be specific and actionable; avoid generic praise",
                "Prefer concrete source-code evidence: indicators, risk controls, exit logic, or code issues",
            ],
        ),
        ("Final Decision", ["Explicitly state whether the strategy is suitable for 1m/3m/5m short-timeframe trading and live deployment."]),
    ]


def prompt_template_text(lang: str) -> str:
    blocks = []
    for title, bullets in prompt_framework(lang):
        bullet_lines = "\n".join(f"- {bullet}" for bullet in bullets)
        blocks.append(f"[{title}]\n{bullet_lines}")
    return "\n\n".join(blocks)


def prompt_template_html(lang: str) -> str:
    cards = []
    for title, bullets in prompt_framework(lang):
        items = "".join(f"<li>{html.escape(bullet)}</li>" for bullet in bullets)
        cards.append(f"<article><h3>{html.escape(title)}</h3><ul>{items}</ul></article>")
    return "".join(cards)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return {**DEFAULT_CONFIG, **json.load(file)}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)


def t(lang: str, key: str) -> str:
    return TEXT.get(lang, TEXT["en"]).get(key, key)


def set_state(**updates: object) -> None:
    with STATE_LOCK:
        RUN_STATE.update(updates)


def append_output(text: str) -> None:
    with STATE_LOCK:
        RUN_STATE["output"] = (RUN_STATE["output"] + text)[-30000:]


def snapshot_state() -> dict:
    with STATE_LOCK:
        return RUN_STATE.copy()


def status_key(status: str) -> str:
    if status.startswith("failed"):
        return "failed"
    return status if status in {"idle", "running", "success", "stopped"} else "idle"


def terminate_current_process() -> bool:
    global CURRENT_PROCESS
    with PROCESS_LOCK:
        process = CURRENT_PROCESS
        if process and process.poll() is None:
            set_state(cancel_requested=True)
            process.terminate()
            return True
    return False


def run_sequence(step_name: str, commands: list[list[str]]) -> None:
    global CURRENT_PROCESS
    command_label = " && ".join(" ".join(command) for command in commands)
    set_state(
        status="running",
        step=step_name,
        command=command_label,
        output="",
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        finished_at="",
        cancel_requested=False,
    )
    env = os.environ.copy()
    env["MPLCONFIGDIR"] = str(PROJECT_ROOT / ".mpl-cache")
    env["PYTHONUNBUFFERED"] = "1"

    try:
        for command in commands:
            if snapshot_state().get("cancel_requested"):
                set_state(status="stopped", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                return
            append_output(f"\n$ {' '.join(command)}\n")
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            with PROCESS_LOCK:
                CURRENT_PROCESS = process
            assert process.stdout is not None
            for line in process.stdout:
                append_output(line)
            return_code = process.wait()
            with PROCESS_LOCK:
                CURRENT_PROCESS = None
            if snapshot_state().get("cancel_requested"):
                set_state(status="stopped", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                return
            if return_code != 0:
                set_state(status=f"failed ({return_code})", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                return
        set_state(status="success", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as exc:
        with PROCESS_LOCK:
            CURRENT_PROCESS = None
        append_output(str(exc))
        set_state(status="failed", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))


def start_sequence(step_name: str, commands: list[list[str]]) -> bool:
    if snapshot_state()["status"] == "running":
        return False
    thread = threading.Thread(target=run_sequence, args=(step_name, commands), daemon=True)
    thread.start()
    return True


def result_info(file_name: str, lang: str) -> tuple[bool, str]:
    path = RESULTS_DIR / file_name
    if not path.exists():
        return False, t(lang, "not_generated")
    size_kb = path.stat().st_size / 1024
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
    return True, f"{size_kb:.1f} KB · {stamp}"


def enc(file_name: str) -> str:
    return "".join(f"%{byte:02X}" for byte in file_name.encode("utf-8"))


def read_rows(file_name: str) -> list[dict[str, str]]:
    path = RESULTS_DIR / file_name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def short_text(value: str, limit: int = 170) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "..."


def contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def display_text(lang: str, value: str) -> str:
    value = short_text(value)
    if lang == "zh" and value and not contains_cjk(value):
        return "重新运行第 2 步后将显示中文分析内容。"
    return value


def label_value(lang: str, value: str) -> str:
    key = str(value or "").lower()
    return t(lang, key) if key in {"low", "medium", "high", "beginner", "intermediate", "advanced"} else str(value or "-")


def score_class(score: float) -> str:
    if score >= 70:
        return "good"
    if score >= 55:
        return "ok"
    return "weak"


def display_text(lang: str, value: str) -> str:
    value = " ".join(str(value or "").split())
    if lang == "zh" and value and not contains_cjk(value):
        return t(lang, "legacy_language_notice")
    return value


def strategy_download_href(row: dict[str, str]) -> str:
    file_path = (row.get("file_path") or "").replace("\\", "/").strip("/")
    if not file_path:
        return ""
    return f"/strategies/{enc(file_path)}"


def insight_block(lang: str, key: str, value: str) -> str:
    text = display_text(lang, value) or "-"
    return f"""
      <details class="insight" open>
        <summary>{html.escape(t(lang, key))}</summary>
        <p>{html.escape(text)}</p>
      </details>
    """


def file_card(lang: str, title_key: str, file_name: str, meta: str, exists: bool, view: str | None, download: bool = False) -> str:
    if not exists:
        action = f"<span>{html.escape(t(lang, 'pending'))}</span>"
    elif download:
        action = f'<a href="/results/{enc(file_name)}">{html.escape(t(lang, "download"))}</a>'
    else:
        action = f'<a href="/?view={view}#preview">{html.escape(t(lang, "show"))}</a>'
    if title_key == "ranking":
        file_label = t(lang, "ranking_desc")
    elif title_key == "summary":
        file_label = t(lang, "summary_desc")
    else:
        file_label = file_name
    return f"""
      <div class="file-card {'ready' if exists else 'pending'}">
        <strong>{html.escape(t(lang, title_key))}</strong>
        <small>{html.escape(file_label)}</small>
        <em>{html.escape(meta)}</em>
        {action}
      </div>
    """


def render_ranking(lang: str) -> str:
    rows = read_rows("comprehensive_strategy_ranking.csv")
    if not rows:
        return f"<p class='hint'>{html.escape(t(lang, 'not_generated'))}</p>"
    cards = []
    for index, row in enumerate(rows[:20], 1):
        score = float(row.get("overall_score") or 0)
        download_href = strategy_download_href(row)
        download_action = f'<a class="strategy-download" href="{download_href}">{html.escape(t(lang, "download_strategy"))}</a>' if download_href else ""
        cards.append(f"""
          <article class="rank-card">
            <div class="rank-number">#{index}</div>
            <div class="rank-main">
              <div class="card-head">
                <h3>{html.escape(row.get("strategy_name", "-"))}</h3>
                {download_action}
              </div>
              <div class="chips">
                <span>{html.escape(t(lang, "timeframe"))}: {html.escape(row.get("timeframe", "-"))}</span>
                <span>{html.escape(t(lang, "risk"))}: {html.escape(label_value(lang, row.get("risk_assessment", "-")))}</span>
                <span>{html.escape(t(lang, "complexity"))}: {html.escape(label_value(lang, row.get("complexity_level", "-")))}</span>
              </div>
              {insight_block(lang, "strengths", row.get("strengths", ""))}
              {insight_block(lang, "recommendations", row.get("recommendations", ""))}
            </div>
            <div class="score-badge {score_class(score)}">
              <strong>{score:.0f}</strong>
              <span>{html.escape(t(lang, "score"))}</span>
            </div>
          </article>
        """)
    return f"<div class='rank-list'>{''.join(cards)}</div>"


def distribution(rows: list[dict[str, str]], column: str, lang: str) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(column, "-") or "-"
        counts[value] = counts.get(value, 0) + 1
    total = max(len(rows), 1)
    bars = []
    for value, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        pct = count / total * 100
        bars.append(f"""
          <div class="dist-row">
            <span>{html.escape(label_value(lang, value))}</span>
            <div><i style="width:{pct:.1f}%"></i></div>
            <strong>{count}</strong>
          </div>
        """)
    return "".join(bars)


def render_summary(lang: str) -> str:
    rows = read_rows("comprehensive_strategy_ranking.csv")
    summaries = read_rows("strategy_summary_report.csv")
    if not rows:
        return f"<p class='hint'>{html.escape(t(lang, 'not_generated'))}</p>"
    scores = [float(row.get("overall_score") or 0) for row in rows]
    best_row = max(rows, key=lambda row: float(row.get("overall_score") or 0))
    ranking_by_name = {row.get("strategy_name", ""): row for row in rows}
    stat_cards = f"""
      <div class="summary-grid">
        <div><span>{html.escape(t(lang, "total"))}</span><strong>{len(rows)}</strong></div>
        <div><span>{html.escape(t(lang, "average"))}</span><strong>{sum(scores) / len(scores):.1f}</strong></div>
        <div><span>{html.escape(t(lang, "pass_rate"))}</span><strong>{sum(score >= 60 for score in scores) / len(scores) * 100:.1f}%</strong></div>
        <div><span>{html.escape(t(lang, "best"))}</span><strong>{html.escape(best_row.get("strategy_name", "-"))}</strong></div>
      </div>
    """
    highlights = []
    for row in summaries[:8]:
        source_row = {**ranking_by_name.get(row.get("strategy_name", ""), {}), **row}
        download_href = strategy_download_href(source_row)
        download_action = f'<a class="strategy-download" href="{download_href}">{html.escape(t(lang, "download_strategy"))}</a>' if download_href else ""
        highlights.append(f"""
          <article class="summary-card">
            <div class="card-head">
              <h3>{html.escape(row.get("strategy_name", "-"))}</h3>
              {download_action}
            </div>
            <div class="chips">
              <span>{html.escape(row.get("timeframe", "-"))}</span>
              <span>{html.escape(label_value(lang, row.get("risk_assessment", "-")))}</span>
              <span>{html.escape(row.get("overall_score", "-"))}</span>
            </div>
            {insight_block(lang, "strengths", row.get("strengths", ""))}
            {insight_block(lang, "weaknesses", row.get("weaknesses", ""))}
          </article>
        """)
    return f"""
      {stat_cards}
      <div class="summary-columns">
        <section>
          <h3>{html.escape(t(lang, "risk_mix"))}</h3>
          {distribution(rows, "risk_assessment", lang)}
        </section>
        <section>
          <h3>{html.escape(t(lang, "complexity_mix"))}</h3>
          {distribution(rows, "complexity_level", lang)}
        </section>
      </div>
      <div class="summary-list">{''.join(highlights)}</div>
    """


def render_preview(lang: str, view: str) -> str:
    if view == "ranking":
        title = t(lang, "top_ranking")
        content = render_ranking(lang)
    elif view == "summary":
        title = t(lang, "summary_overview")
        content = render_summary(lang)
    else:
        title = t(lang, "dashboard")
        dashboard = OUTPUTS[lang]["dashboard"]
        if (RESULTS_DIR / dashboard).exists():
            content = f'<a class="preview" href="/results/{enc(dashboard)}" target="_blank"><img src="/results/{enc(dashboard)}" alt="{html.escape(title)}"></a>'
        else:
            content = f"<p class='hint'>{html.escape(t(lang, 'preview_hint'))}</p>"
    return f"""
      <div class="preview-panel" id="preview">
        <div class="section-title">
          <h2>{html.escape(title)}</h2>
          <span>{html.escape(t(lang, "preview"))}</span>
        </div>
        {content}
      </div>
    """


def render_results(lang: str, view: str) -> str:
    dashboard = OUTPUTS[lang]["dashboard"]
    excel = OUTPUTS[lang]["excel"]
    dashboard_exists, dashboard_meta = result_info(dashboard, lang)
    excel_exists, excel_meta = result_info(excel, lang)
    ranking_exists, ranking_meta = result_info("comprehensive_strategy_ranking.csv", lang)
    summary_exists, summary_meta = result_info("strategy_summary_report.csv", lang)
    return f"""
    <section class="results-panel" id="results">
      <div class="section-title">
        <h2>{html.escape(t(lang, "results"))}</h2>
        <span>{html.escape(t(lang, "stored"))}</span>
      </div>
      <div class="file-grid">
        {file_card(lang, "ranking", "comprehensive_strategy_ranking.csv", ranking_meta, ranking_exists, "ranking")}
        {file_card(lang, "summary", "strategy_summary_report.csv", summary_meta, summary_exists, "summary")}
        {file_card(lang, "dashboard", dashboard, dashboard_meta, dashboard_exists, "dashboard")}
        {file_card(lang, "excel", excel, excel_meta, excel_exists, None, download=True)}
      </div>
      {render_preview(lang, view)}
    </section>
    """


def render_language_page() -> bytes:
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Freqtrade Strategy Intelligence</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: "Segoe UI", Arial, "Microsoft YaHei", sans-serif; background: #f3f5f8; color: #172033; }}
    .panel {{ width: min(560px, calc(100vw - 32px)); background: #fff; border: 1px solid #d9dee8; border-radius: 10px; padding: 28px; }}
    h1 {{ margin: 0; font-size: 24px; }}
    p {{ color: #647084; line-height: 1.5; }}
    form {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }}
    button {{ border: 0; border-radius: 7px; background: #1769aa; color: #fff; padding: 12px 18px; font-weight: 700; cursor: pointer; }}
    button.secondary {{ background: #44546a; }}
  </style>
</head>
<body>
  <div class="panel">
    <h1>{html.escape(TEXT["zh"]["choose_title"])} / {html.escape(TEXT["en"]["choose_title"])}</h1>
    <p>{html.escape(TEXT["zh"]["choose_subtitle"])}</p>
    <p>{html.escape(TEXT["en"]["choose_subtitle"])}</p>
    <form method="post" action="/set-language">
      <button name="language" value="zh" type="submit">{html.escape(TEXT["zh"]["choose_zh"])}</button>
      <button class="secondary" name="language" value="en" type="submit">{html.escape(TEXT["en"]["choose_en"])}</button>
    </form>
  </div>
</body>
</html>"""
    return body.encode("utf-8")


def render_page(message: str = "", query: dict | None = None) -> bytes:
    config = load_config()
    lang = config.get("language") or ""
    if lang not in TEXT:
        return render_language_page()

    query = query or {}
    view = query.get("view", ["dashboard"])[0]
    if view not in {"dashboard", "ranking", "summary"}:
        view = "dashboard"

    state = snapshot_state()
    state_key = status_key(str(state["status"]))
    api_key = html.escape(config.get("openai_api_key", ""))
    model = html.escape(config.get("model", "gpt-4o"))
    prompt_template = prompt_template_text(lang)
    prompt_template_cards = prompt_template_html(lang)
    prompt_template_attr = html.escape(prompt_template, quote=True)
    prompt_value = config.get("analysis_prompt", "")
    if (
        not prompt_value
        or prompt_value == DEFAULT_CONFIG["analysis_prompt"]
        or prompt_value == ZH_DEFAULT_PROMPT
        or prompt_value == t(lang, "prompt_template_text")
        or prompt_value.startswith("Evaluate the strategy source code as a professional Freqtrade strategy analyst.")
    ):
        prompt_value = prompt_template
    prompt = html.escape(prompt_value)
    output = html.escape(str(state["output"]))
    message_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    refresh_meta = '<meta http-equiv="refresh" content="2">' if state_key == "running" else ""
    disable_attr = "disabled" if state_key == "running" else ""
    stop_button = f"""
      <form method="post" action="/stop" onsubmit="return confirm('{html.escape(t(lang, "confirm_stop"))}')">
        <button class="danger" type="submit">{html.escape(t(lang, "stop"))}</button>
      </form>
    """ if state_key == "running" else ""
    next_lang = "en" if lang == "zh" else "zh"

    body = f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh_meta}
  <title>{html.escape(t(lang, "app_title"))}</title>
  <style>
    :root {{ --bg:#f3f5f8; --panel:#fff; --text:#172033; --muted:#647084; --line:#d9dee8; --accent:#1769aa; --accent-dark:#0f4f82; --ok:#0f766e; --warn:#a16207; --danger:#b42318; --soft:#eef6fc; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: Inter, "Segoe UI", Arial, "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--text); }}
    header {{ background:#fff; border-bottom:1px solid var(--line); padding:22px 32px; position: sticky; top:0; z-index: 5; }}
    .topbar {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }}
    h1 {{ margin:0; font-size:24px; letter-spacing:0; }}
    header p {{ margin:8px 0 0; color:var(--muted); max-width:980px; line-height:1.5; }}
    .lang-form button {{ background:#fff; color:var(--accent); border:1px solid var(--line); }}
    main {{ max-width:1380px; margin:0 auto; padding:24px; display:grid; grid-template-columns:minmax(0,1.25fr) minmax(380px,.75fr); gap:20px; }}
    section, aside {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:20px; }}
    .section-title {{ display:flex; justify-content:space-between; gap:12px; align-items:baseline; margin-bottom:14px; }}
    h2 {{ margin:0; font-size:16px; }} h3 {{ margin:0; }}
    .section-title span, .hint {{ color:var(--muted); font-size:13px; }}
    label {{ display:block; font-weight:650; margin:14px 0 8px; }}
    input, textarea {{ width:100%; border:1px solid var(--line); border-radius:6px; padding:10px 12px; font:inherit; color:var(--text); background:#fff; }}
    textarea {{ min-height:165px; resize:vertical; line-height:1.45; }}
    .prompt-template {{ margin-top:10px; border:1px dashed #b9c7d8; border-radius:8px; padding:12px; background:#f8fbff; }}
    .prompt-template strong {{ display:block; margin-bottom:6px; font-size:13px; }}
    .prompt-framework {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:10px; }}
    .prompt-framework article {{ border:1px solid #d8e2ef; border-radius:8px; background:#fff; padding:10px; }}
    .prompt-framework h3 {{ font-size:13px; margin:0 0 7px; color:#172033; }}
    .prompt-framework ul {{ margin:0; padding-left:18px; color:#465367; font-size:12.5px; line-height:1.45; }}
    .prompt-framework li + li {{ margin-top:4px; }}
    .prompt-template button {{ margin-top:10px; padding:7px 10px; font-size:12px; }}
    .notice {{ border:1px solid #9bd8d2; background:#ecfdfb; color:var(--ok); padding:10px 12px; border-radius:6px; margin-bottom:14px; }}
    button {{ border:0; border-radius:6px; background:var(--accent); color:white; padding:10px 14px; font-weight:650; cursor:pointer; }}
    button:hover {{ background:var(--accent-dark); }} button:disabled {{ cursor:not-allowed; opacity:.55; }} button.danger {{ background:var(--danger); }}
    .button-row {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }}
    .workflow {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
    .step-card {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:#fbfcfe; min-height:265px; display:flex; flex-direction:column; justify-content:space-between; }}
    .step-index {{ display:inline-flex; width:28px; height:28px; align-items:center; justify-content:center; border-radius:50%; background:var(--soft); color:var(--accent); font-weight:800; margin-bottom:10px; }}
    .step-card h3 {{ font-size:15px; margin-bottom:8px; }} .step-card p {{ margin:0 0 10px; color:var(--muted); font-size:13px; line-height:1.45; }}
    .badge {{ display:inline-block; border-radius:999px; background:#fff7ed; color:var(--warn); padding:4px 8px; font-size:12px; font-weight:650; margin:3px 0 8px; }} .safe {{ background:#ecfdf3; color:var(--ok); }}
    .status-box {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfcfe; margin-bottom:14px; }} .status-box.running {{ background:#eff6ff; border-color:#93c5fd; }} .status-box.success {{ background:#ecfdf3; border-color:#86efac; }} .status-box.failed {{ background:#fef3f2; border-color:#fda29b; }} .status-box.stopped {{ background:#fff7ed; border-color:#fdba74; }}
    .status-grid {{ display:grid; gap:8px; font-size:13px; }} .status-grid strong {{ display:block; color:var(--muted); font-size:12px; margin-bottom:2px; }}
    .progress {{ width:100%; height:10px; border-radius:999px; background:#e5e7eb; overflow:hidden; margin:12px 0; }} .progress span {{ display:block; height:100%; border-radius:inherit; background:var(--accent); }}
    .progress.running span {{ width:45%; animation:pulsebar 1.3s infinite alternate ease-in-out; }} .progress.success span {{ width:100%; background:var(--ok); }} .progress.failed span {{ width:100%; background:var(--danger); }} .progress.stopped span {{ width:100%; background:var(--warn); }}
    @keyframes pulsebar {{ from {{ transform:translateX(-35%); }} to {{ transform:translateX(140%); }} }}
    pre {{ white-space:pre-wrap; word-break:break-word; background:#101827; color:#e5e7eb; padding:12px; border-radius:6px; min-height:260px; max-height:520px; overflow:auto; font-size:12px; }}
    .file-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }} .file-card {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfe; min-height:128px; }} .file-card strong,.file-card small,.file-card em {{ display:block; }} .file-card small {{ color:var(--muted); margin-top:6px; word-break:break-word; }} .file-card em {{ color:var(--muted); font-style:normal; margin:8px 0; font-size:12px; }} .file-card a {{ color:var(--accent); font-weight:700; text-decoration:none; }}
    .preview-panel {{ margin-top:16px; border:1px solid var(--line); border-radius:8px; padding:14px; scroll-margin-top:105px; }} .preview img {{ display:block; width:100%; border:1px solid var(--line); border-radius:8px; background:#fff; }}
    .rank-list, .summary-list {{ display:grid; gap:10px; }} .rank-card {{ display:grid; grid-template-columns:52px minmax(0,1fr) 86px; gap:14px; align-items:start; border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfcfe; }} .rank-number {{ font-size:18px; font-weight:800; color:var(--accent); }} .rank-main h3 {{ font-size:16px; margin-bottom:0; }} .rank-main p, .summary-card p {{ margin:8px 0 0; color:#465367; line-height:1.55; font-size:13px; }}
    .card-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px; }}
    .strategy-download {{ flex:0 0 auto; color:var(--accent); border:1px solid #c9d8ea; background:#fff; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:700; text-decoration:none; }}
    .insight {{ margin-top:10px; border:1px solid #e1e7f0; border-radius:7px; background:#fff; padding:8px 10px; }}
    .insight summary {{ cursor:pointer; color:#172033; font-weight:750; font-size:13px; }}
    .insight p {{ margin:7px 0 0; white-space:normal; overflow-wrap:anywhere; }}
    .chips {{ display:flex; gap:6px; flex-wrap:wrap; }} .chips span {{ border:1px solid #d8e2ef; background:#fff; border-radius:999px; padding:3px 8px; color:#536178; font-size:12px; }}
    .score-badge {{ border-radius:8px; padding:10px 8px; text-align:center; color:#fff; }} .score-badge strong {{ display:block; font-size:24px; }} .score-badge span {{ font-size:12px; }} .score-badge.good {{ background:#0f766e; }} .score-badge.ok {{ background:#a16207; }} .score-badge.weak {{ background:#b42318; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:14px; }} .summary-grid div {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfcfe; }} .summary-grid span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:6px; }} .summary-grid strong {{ font-size:20px; word-break:break-word; }}
    .summary-columns {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-bottom:14px; }} .summary-columns section {{ padding:14px; }} .summary-columns h3 {{ font-size:14px; margin-bottom:12px; }}
    .dist-row {{ display:grid; grid-template-columns:90px minmax(0,1fr) 40px; gap:10px; align-items:center; margin:8px 0; font-size:13px; }} .dist-row div {{ height:9px; background:#edf2f7; border-radius:999px; overflow:hidden; }} .dist-row i {{ display:block; height:100%; background:var(--accent); border-radius:999px; }}
    .summary-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfcfe; }} .summary-card h3 {{ font-size:15px; margin-bottom:8px; }}
    .wide {{ grid-column:1 / -1; }} .pending {{ opacity:.65; }}
    @media (max-width:980px) {{ header {{ padding:20px 16px; position:static; }} main {{ grid-template-columns:1fr; padding:16px; }} .workflow,.file-grid,.summary-grid,.summary-columns {{ grid-template-columns:1fr; }} .topbar {{ display:block; }} .rank-card {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div>
        <h1>{html.escape(t(lang, "app_title"))}</h1>
        <p>{html.escape(t(lang, "app_subtitle"))}</p>
      </div>
      <form class="lang-form" method="post" action="/set-language"><button name="language" value="{next_lang}" type="submit">{html.escape(t(lang, "switch"))}</button></form>
    </div>
  </header>
  <main>
    <section>
      {message_html}
      <div class="section-title"><h2>{html.escape(t(lang, "configuration"))}</h2><span>{html.escape(t(lang, "saved_local"))}</span></div>
      <form method="post" action="/save">
        <label for="openai_api_key">{html.escape(t(lang, "api_key"))}</label>
        <input id="openai_api_key" name="openai_api_key" type="password" value="{api_key}" placeholder="sk-...">
        <div class="hint">{html.escape(t(lang, "api_hint"))}</div>
        <label for="model">{html.escape(t(lang, "model"))}</label>
        <input id="model" name="model" value="{model}">
        <label for="analysis_prompt">{html.escape(t(lang, "custom_prompt"))}</label>
        <textarea id="analysis_prompt" name="analysis_prompt">{prompt}</textarea>
        <div class="prompt-template">
          <strong>{html.escape(t(lang, "prompt_template"))}</strong>
          <div class="prompt-framework">{prompt_template_cards}</div>
          <button type="button" data-template="{prompt_template_attr}" onclick="document.getElementById('analysis_prompt').value = this.dataset.template">{html.escape(t(lang, "use_template"))}</button>
        </div>
        <div class="hint">{html.escape(t(lang, "prompt_hint"))}</div>
        <div class="button-row"><button type="submit" {disable_attr}>{html.escape(t(lang, "save"))}</button></div>
      </form>
    </section>
    <aside>
      <div class="section-title"><h2>{html.escape(t(lang, "run_status"))}</h2><span>{html.escape(t(lang, state_key))}</span></div>
      <div class="status-box {state_key}">
        <div class="progress {state_key}"><span></span></div>
        <div class="status-grid">
          <div><strong>{html.escape(t(lang, "current_step"))}</strong>{html.escape(str(state["step"]) or t(lang, "no_active_run"))}</div>
          <div><strong>{html.escape(t(lang, "started"))}</strong>{html.escape(str(state["started_at"]) or "-")}</div>
          <div><strong>{html.escape(t(lang, "finished"))}</strong>{html.escape(str(state["finished_at"]) or "-")}</div>
          <div><strong>{html.escape(t(lang, "command"))}</strong><span class="hint">{html.escape(str(state["command"]) or "-")}</span></div>
        </div>
      </div>
      {stop_button}
      <pre>{output or html.escape(t(lang, "logs_placeholder"))}</pre>
    </aside>
    <section class="wide">
      <div class="section-title"><h2>{html.escape(t(lang, "workflow"))}</h2><span>{html.escape(t(lang, "run_one"))}</span></div>
      <div class="workflow">
        <form class="step-card" method="post" action="/run-prepare" onsubmit="return confirm('{html.escape(t(lang, "confirm_step1"))}')">
          <div><span class="step-index">1</span><h3>{html.escape(t(lang, "step1_title"))}</h3><span class="badge">{html.escape(t(lang, "uses_api"))}</span><p>{html.escape(t(lang, "step1_desc"))}</p><p class="hint">{html.escape(t(lang, "api_cost"))}</p></div>
          <button type="submit" {disable_attr}>{html.escape(t(lang, "run_step1"))}</button>
        </form>
        <form class="step-card" method="post" action="/run-analyze" onsubmit="return confirm('{html.escape(t(lang, "confirm_step2"))}')">
          <div><span class="step-index">2</span><h3>{html.escape(t(lang, "step2_title"))}</h3><span class="badge">{html.escape(t(lang, "uses_api"))}</span><p>{html.escape(t(lang, "step2_desc"))}</p><p class="hint">{html.escape(t(lang, "api_cost"))}</p><label for="limit">{html.escape(t(lang, "limit"))}</label><input id="limit" name="limit" type="number" min="1" placeholder="{html.escape(t(lang, "limit_placeholder"))}"></div>
          <button type="submit" {disable_attr}>{html.escape(t(lang, "run_step2"))}</button>
        </form>
        <form class="step-card" method="post" action="/run-report" onsubmit="return confirm('{html.escape(t(lang, "confirm_step3"))}')">
          <div><span class="step-index">3</span><h3>{html.escape(t(lang, "step3_title"))}</h3><span class="badge safe">{html.escape(t(lang, "no_api"))}</span><p>{html.escape(t(lang, "step3_desc"))}</p></div>
          <button type="submit" {disable_attr}>{html.escape(t(lang, "run_step3"))}</button>
        </form>
      </div>
    </section>
    <div class="wide">{render_results(lang, view)}</div>
  </main>
</body>
</html>"""
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/results/"):
            self.serve_result_file(parsed.path.removeprefix("/results/"))
            return
        if parsed.path.startswith("/strategies/"):
            self.serve_strategy_file(parsed.path.removeprefix("/strategies/"))
            return
        self.respond(render_page(query=parse_qs(parsed.query)))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        fields = {key: values[0] for key, values in parse_qs(raw).items()}
        path = urlparse(self.path).path
        config = load_config()
        lang = config.get("language") if config.get("language") in TEXT else "en"

        if path == "/set-language":
            language = fields.get("language", "en")
            config["language"] = language if language in TEXT else "en"
            save_config(config)
            self.redirect("/")
            return
        if path == "/save":
            config.update({
                "openai_api_key": fields.get("openai_api_key", "").strip(),
                "model": fields.get("model", "gpt-4o").strip() or "gpt-4o",
                "analysis_prompt": fields.get("analysis_prompt", "").strip(),
            })
            save_config(config)
            self.respond(render_page(t(lang, "saved")))
            return
        if path == "/stop":
            if terminate_current_process():
                append_output("\nStop requested by user.\n")
            self.respond(render_page(t(lang, "stop_sent")))
            return
        if path == "/run-prepare":
            started = start_sequence(t(lang, "step1_title"), [[PYTHON, "-u", "scripts/prepare_strategies.py", "--reset", "--download"]])
            self.respond(render_page(t(lang, "step1_started") if started else t(lang, "already_running")))
            return
        if path == "/run-analyze":
            command = [PYTHON, "-u", "scripts/analyze_strategies.py"]
            limit = fields.get("limit", "").strip()
            if limit:
                command.extend(["--limit", limit])
            started = start_sequence(t(lang, "step2_title"), [command])
            self.respond(render_page(t(lang, "step2_started") if started else t(lang, "already_running")))
            return
        if path == "/run-report":
            started = start_sequence(
                t(lang, "step3_title"),
                [
                    [PYTHON, "-u", "scripts/生成统计图表.py", "--language", lang],
                    [PYTHON, "-u", "scripts/生成Excel汇总.py", "--language", lang],
                ],
            )
            self.respond(render_page(t(lang, "step3_started") if started else t(lang, "already_running")))
            return
        self.send_error(404)

    def respond(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, path: str) -> None:
        self.send_response(303)
        self.send_header("Location", path)
        self.end_headers()

    def serve_result_file(self, raw_name: str) -> None:
        file_name = unquote(raw_name)
        file_path = (RESULTS_DIR / file_name).resolve()
        if not file_path.is_relative_to(RESULTS_DIR.resolve()) or not file_path.exists():
            self.send_error(404)
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", guess_type(str(file_path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_strategy_file(self, raw_name: str) -> None:
        relative_name = unquote(raw_name).replace("\\", "/").strip("/")
        if not relative_name.endswith(".py") or ".." in Path(relative_name).parts:
            self.send_error(404)
            return

        file_path = (PROJECT_ROOT / relative_name).resolve()
        allowed = any(file_path.is_relative_to(root.resolve()) for root in STRATEGY_DOWNLOAD_ROOTS)
        if not allowed or not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return

        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/x-python; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "7860"))
    CONFIG_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Freqtrade Strategy Intelligence Console running at http://localhost:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
