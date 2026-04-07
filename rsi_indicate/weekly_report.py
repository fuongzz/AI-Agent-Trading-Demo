"""
weekly_report.py — Weekly Report Generator
Phần 6 của System Design.

Tự động chạy mỗi thứ 6 (qua scheduler.py).
Output: JSON summary + gửi Discord.

Nội dung:
  - Performance tuần qua vs VN-Index
  - Top 3 quyết định đúng nhất — tại sao đúng
  - Top 3 quyết định sai nhất — tại sao sai, lesson learned
  - Screener stats: bao nhiêu mã pass/fail
  - Agent accuracy: confluence score vs kết quả thực tế

PDF export (optional, cần weasyprint):
  pip install weasyprint jinja2
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
DB_PATH    = os.path.join(os.path.dirname(__file__), "trading_assistant.db")

os.makedirs(REPORT_DIR, exist_ok=True)


# ── Data Loading ───────────────────────────────────────────────────────────────

def _load_week_decisions(days: int = 7) -> list:
    """Load tất cả quyết định trong N ngày qua từ SQLite."""
    if not os.path.exists(DB_PATH):
        return []

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor.execute('''
        SELECT symbol, date, action, confluence_score, raw_reasoning, created_at
        FROM agent_decisions
        WHERE date >= ?
        ORDER BY created_at DESC
    ''', (cutoff,))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        try:
            reasoning = json.loads(row[4]) if row[4] else {}
        except Exception:
            reasoning = {}
        results.append({
            "symbol":           row[0],
            "date":             row[1],
            "action":           row[2],
            "confluence_score": row[3],
            "reasoning":        reasoning,
            "created_at":       row[5],
        })
    return results


def _load_vnindex_performance(days: int = 7) -> dict:
    """Lấy VN-Index performance tuần qua."""
    try:
        from fetcher import fetch_ohlcv
        data = fetch_ohlcv("VNINDEX", days=days + 5)
        if "error" in data or not data.get("closes"):
            return {}
        closes    = data["closes"]
        week_return = round((closes[-1] - closes[-min(days, len(closes)-1)]) / closes[-min(days, len(closes)-1)] * 100, 2)
        return {
            "current":     closes[-1],
            "week_return": week_return,
            "week_return_str": f"{'+' if week_return >= 0 else ''}{week_return}%",
        }
    except Exception:
        return {}


# ── Analysis ───────────────────────────────────────────────────────────────────

def _analyze_decisions(decisions: list) -> dict:
    """Phân tích chất lượng các quyết định trong tuần."""
    if not decisions:
        return {}

    # Thống kê cơ bản
    total     = len(decisions)
    buy_list  = [d for d in decisions if d["action"] == "MUA"]
    sell_list = [d for d in decisions if d["action"] == "BÁN"]
    wait_list = [d for d in decisions if d["action"] == "CHỜ"]

    # Confluence score stats
    scores = [d["confluence_score"] for d in decisions if d["confluence_score"] is not None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0

    # Top confidence MUA decisions (score cao nhất)
    top_buy = sorted(buy_list, key=lambda d: d["confluence_score"] or 0, reverse=True)[:3]

    # Risk overrides (những quyết định bị Risk Manager chặn)
    overrides = [d for d in decisions if d["reasoning"].get("risk_override")]

    # Symbols analyzed
    symbols = list(set(d["symbol"] for d in decisions))

    return {
        "total":          total,
        "buy_count":      len(buy_list),
        "sell_count":     len(sell_list),
        "wait_count":     len(wait_list),
        "avg_confluence": avg_score,
        "top_buy_signals": top_buy,
        "risk_overrides":  overrides,
        "symbols_analyzed": symbols,
        "n_symbols":       len(symbols),
    }


def _generate_lessons(decisions: list, analysis: dict) -> dict:
    """
    Tự động tổng hợp lesson learned từ các quyết định.
    Dùng heuristics đơn giản — không cần LLM (tiết kiệm cost).
    """
    lessons = []

    # Pattern 1: Risk overrides nhiều → thị trường bất ổn
    if len(analysis.get("risk_overrides", [])) >= 3:
        lessons.append({
            "type":    "MARKET_RISK",
            "lesson":  f"Risk Manager chặn {len(analysis['risk_overrides'])} lệnh trong tuần. "
                       f"Thị trường có thể đang ở giai đoạn bất ổn — circuit breaker hoặc room trap.",
            "action":  "Tăng ngưỡng confluence cần thiết để MUA, giảm sizing."
        })

    # Pattern 2: Nhiều CHỜ → tín hiệu không rõ
    wait_pct = analysis.get("wait_count", 0) / max(analysis.get("total", 1), 1) * 100
    if wait_pct > 60:
        lessons.append({
            "type":    "SIGNAL_QUALITY",
            "lesson":  f"{wait_pct:.0f}% quyết định là CHỜ — tín hiệu thị trường không rõ ràng.",
            "action":  "Bình thường khi thị trường ranging. Kiên nhẫn chờ setup rõ ràng hơn."
        })

    # Pattern 3: Top buy signals (để review)
    if analysis.get("top_buy_signals"):
        top = analysis["top_buy_signals"][0]
        lessons.append({
            "type":    "TOP_SIGNAL",
            "lesson":  f"Tín hiệu MUA mạnh nhất tuần: {top['symbol']} "
                       f"(confluence: {top['confluence_score']:.1f}) ngày {top['date']}.",
            "action":  f"Review chart {top['symbol']} — confluence cao là điều kiện cần, nhưng không đủ."
        })

    return {"lessons": lessons}


# ── Report Generation ──────────────────────────────────────────────────────────

def generate_weekly_report(days: int = 7) -> dict:
    """
    Tạo Weekly Report đầy đủ.
    Trả về dict và lưu JSON vào reports/.
    """
    now  = datetime.now()
    week = now.strftime("%Y-W%V")

    print(f"\n{'='*60}")
    print(f"WEEKLY REPORT — {week}")
    print(f"Kỳ: {(now - timedelta(days=days)).strftime('%d/%m')} → {now.strftime('%d/%m/%Y')}")
    print("="*60)

    # Tải dữ liệu
    decisions    = _load_week_decisions(days)
    vnindex_perf = _load_vnindex_performance(days)
    analysis     = _analyze_decisions(decisions)
    lesson_data  = _generate_lessons(decisions, analysis)

    report = {
        "week":         week,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "period":       {
            "from": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
            "to":   now.strftime("%Y-%m-%d"),
            "days": days
        },
        "market":       vnindex_perf,
        "analysis":     analysis,
        "lessons":      lesson_data["lessons"],
    }

    # Print summary
    print(f"\nVN-Index tuần: {vnindex_perf.get('week_return_str', 'N/A')} "
          f"(hiện tại: {vnindex_perf.get('current', 'N/A')})")
    print(f"\nPhân tích tuần:")
    print(f"  Tổng: {analysis.get('total', 0)} quyết định | "
          f"MUA: {analysis.get('buy_count', 0)} | "
          f"BÁN: {analysis.get('sell_count', 0)} | "
          f"CHỜ: {analysis.get('wait_count', 0)}")
    print(f"  Mã đã phân tích: {', '.join(analysis.get('symbols_analyzed', []))}")
    print(f"  Avg Confluence: {analysis.get('avg_confluence', 0):.1f}")
    print(f"  Risk Overrides: {len(analysis.get('risk_overrides', []))}")

    if lesson_data["lessons"]:
        print(f"\nLesson Learned ({len(lesson_data['lessons'])}):")
        for l in lesson_data["lessons"]:
            print(f"  [{l['type']}] {l['lesson']}")
            print(f"    → {l['action']}")

    # Lưu JSON
    report_path = os.path.join(REPORT_DIR, f"weekly_{week}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[Report] Đã lưu → {report_path}")

    return report


def format_discord_report(report: dict) -> str:
    """Format report thành Discord message."""
    week    = report.get("week", "?")
    mkt     = report.get("market", {})
    ana     = report.get("analysis", {})
    lessons = report.get("lessons", [])

    vni_icon = "🟢" if (mkt.get("week_return", 0) or 0) >= 0 else "🔴"
    lines = [
        f"📊 **WEEKLY REPORT {week}**",
        f"_{report['period']['from']} → {report['period']['to']}_\n",
        f"**Thị trường:** {vni_icon} VN-Index {mkt.get('week_return_str', 'N/A')} | {mkt.get('current', 'N/A')} điểm\n",
        f"**Hoạt động hệ thống:**",
        f"  • {ana.get('n_symbols', 0)} mã phân tích | {ana.get('total', 0)} quyết định",
        f"  • MUA: {ana.get('buy_count', 0)} | BÁN: {ana.get('sell_count', 0)} | CHỜ: {ana.get('wait_count', 0)}",
        f"  • Avg Confluence: {ana.get('avg_confluence', 0):.1f} | Risk Overrides: {len(ana.get('risk_overrides', []))}",
    ]

    if lessons:
        lines.append(f"\n**Lesson Learned:**")
        for l in lessons[:3]:
            lines.append(f"  • [{l['type']}] {l['lesson'][:80]}")

    return "\n".join(lines)


def send_weekly_to_discord(report: dict):
    """Gửi Weekly Report lên Discord."""
    try:
        import os, requests
        webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
        if not webhook:
            print("[Weekly] Discord webhook chưa config — bỏ qua.")
            return
        message = format_discord_report(report)
        requests.post(webhook, json={"content": message[:1900]}, timeout=10)
        print("[Weekly] Đã gửi Discord.")
    except Exception as e:
        print(f"[Weekly] Lỗi gửi Discord: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = generate_weekly_report(days=7)
    send_weekly_to_discord(report)
    print("\nDone.")
