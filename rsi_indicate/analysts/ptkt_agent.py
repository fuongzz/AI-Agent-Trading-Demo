"""
analysts/ptkt_agent.py — Tầng I: PTKT Agent
Nhiệm vụ: Tính toán toàn bộ chỉ báo kỹ thuật và trả về PTKTReport (JSON).
Agent này KHÔNG tranh luận, KHÔNG quyết định — chỉ phân tích kỹ thuật thuần túy.
Output sẽ được Tầng II (Debate) đọc.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agent import run_agent_lite


def run(symbol: str) -> dict:
    """
    Chạy PTKT Agent cho một mã cổ phiếu.
    Trả về PTKTReport — dict JSON chuẩn với signals + recommendation.
    """
    print("\n" + "="*60)
    print(f"[PTKT AGENT] Phân tích kỹ thuật: {symbol}")
    print("="*60)

    report = run_agent_lite(symbol)

    if not report or "raw" in report:
        print(f"[PTKT AGENT] Lỗi: Không lấy được báo cáo cho {symbol}")
        return {}

    print(f"\n[PTKT AGENT] Hoàn thành → Khuyến nghị sơ bộ: {report.get('recommendation', {}).get('action', 'N/A')}")
    return report
